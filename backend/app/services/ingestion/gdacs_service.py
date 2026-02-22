"""
GDACS (Global Disaster Alert and Coordination System) RSS feed poller.

Polls the GDACS RSS feed for new disaster alerts and auto-creates disaster
records when Orange/Red alerts are detected.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import ingestion_config as cfg
from app.database import supabase_admin
from app.services.ingestion.mock_data_service import generate_mock_gdacs_events

logger = logging.getLogger("ingestion.gdacs")

# GDACS XML namespaces
GDACS_NS = {
    "gdacs": "http://www.gdacs.org",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# GDACS event type → our DisasterType mapping
_TYPE_MAP: Dict[str, str] = {
    "EQ": "earthquake",
    "TC": "hurricane",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
    "TS": "tsunami",
}

# GDACS alert level → our severity
_SEVERITY_MAP: Dict[str, str] = {
    "Red": "critical",
    "Orange": "high",
    "Green": "medium",
}


class GDACSService:
    """Polls the GDACS RSS feed for new disaster events."""

    def __init__(self) -> None:
        self.feed_url = cfg.GDACS_RSS_URL

    async def poll(self) -> List[Dict[str, Any]]:
        """
        Fetch the GDACS RSS feed, parse new alerts, and store as ingested_events.
        Falls back to mock data if the feed is unreachable.
        Returns list of newly stored event dicts.
        """
        try:
            xml_text = await self._fetch_feed()
            items = self._parse_feed(xml_text)
            if not items:
                logger.info("GDACS feed returned 0 items – generating mock events")
                items = generate_mock_gdacs_events()
            new_events = await self._deduplicate_and_store(items)
            logger.info("GDACS poll complete – %d new alerts ingested", len(new_events))
            return new_events
        except Exception:
            logger.warning("GDACS RSS unreachable – using mock disaster data")
            items = generate_mock_gdacs_events()
            new_events = await self._deduplicate_and_store(items)
            logger.info("Mock GDACS poll – %d events ingested", len(new_events))
            return new_events

    # ── internals ───────────────────────────────────────────────────

    async def _fetch_feed(self) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self.feed_url)
            resp.raise_for_status()
            return resp.text

    def _parse_feed(self, xml_text: str) -> List[Dict[str, Any]]:
        root = ET.fromstring(xml_text)
        items: List[Dict[str, Any]] = []

        for item in root.findall(".//item"):
            try:
                parsed = self._parse_item(item)
                if parsed:
                    items.append(parsed)
            except Exception:
                logger.exception("Failed to parse GDACS item")

        return items

    def _parse_item(self, item: ET.Element) -> Optional[Dict[str, Any]]:
        title = self._text(item, "title")
        description = self._text(item, "description")
        link = self._text(item, "link")
        pub_date = self._text(item, "pubDate")

        # GDACS-specific fields
        event_type = self._text(item, "gdacs:eventtype", GDACS_NS)
        alert_level = self._text(item, "gdacs:alertlevel", GDACS_NS)
        event_id = self._text(item, "gdacs:eventid", GDACS_NS)
        severity_value = self._text(item, "gdacs:severity", GDACS_NS)
        population = self._text(item, "gdacs:population", GDACS_NS)

        lat_text = self._text(item, "geo:lat", GDACS_NS)
        lon_text = self._text(item, "geo:long", GDACS_NS)

        lat = float(lat_text) if lat_text else None
        lon = float(lon_text) if lon_text else None

        external_id = f"gdacs-{event_type}-{event_id}" if event_id else None

        our_type = _TYPE_MAP.get(event_type or "", "other")
        our_severity = _SEVERITY_MAP.get(alert_level or "", "medium")

        return {
            "external_id": external_id,
            "event_type": "gdacs_alert",
            "title": title,
            "description": description,
            "severity": our_severity,
            "latitude": lat,
            "longitude": lon,
            "location_name": title,  # GDACS titles often include location
            "raw_payload": {
                "link": link,
                "pub_date": pub_date,
                "gdacs_event_type": event_type,
                "gdacs_alert_level": alert_level,
                "gdacs_event_id": event_id,
                "gdacs_severity": severity_value,
                "gdacs_population": population,
                "disaster_type_mapped": our_type,
            },
        }

    async def _deduplicate_and_store(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Insert only events whose external_id is not already present."""
        if not items:
            return []

        # Get source_id for GDACS
        source_id = await self._get_source_id()

        new_events: List[Dict[str, Any]] = []
        for item in items:
            ext_id = item.get("external_id")
            if ext_id:
                existing = (
                    supabase_admin.table("ingested_events")
                    .select("id")
                    .eq("external_id", ext_id)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue  # already ingested

            row = {
                "id": str(uuid4()),
                "source_id": source_id,
                **item,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            new_events.append(row)

        if new_events:
            supabase_admin.table("ingested_events").insert(new_events).execute()

        return new_events

    async def _get_source_id(self) -> str:
        resp = (
            supabase_admin.table("external_data_sources")
            .select("id")
            .eq("source_name", "gdacs")
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["id"]
        # Auto-create the source entry
        new_id = str(uuid4())
        supabase_admin.table("external_data_sources").insert({
            "id": new_id,
            "source_name": "gdacs",
            "source_type": "rss_feed",
            "base_url": "https://www.gdacs.org/xml/rss.xml",
            "is_active": True,
            "poll_interval_s": 900,
        }).execute()
        return new_id

    @staticmethod
    def auto_create_disaster_payload(event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a disaster-create payload from an ingested GDACS event.
        To be used by the orchestrator when auto-creating disaster records.
        """
        raw = event.get("raw_payload", {})
        return {
            "type": raw.get("disaster_type_mapped", "other"),
            "severity": event.get("severity", "medium"),
            "title": event.get("title", "GDACS Alert"),
            "description": event.get("description", ""),
            "status": "active",
            "start_date": datetime.now(timezone.utc).isoformat(),
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
        }

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _text(el: ET.Element, tag: str, ns: Optional[Dict[str, str]] = None) -> Optional[str]:
        child = el.find(tag, ns) if ns else el.find(tag)
        return child.text.strip() if child is not None and child.text else None
