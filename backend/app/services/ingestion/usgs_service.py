"""
USGS Earthquake feed service.

Subscribes to the USGS GeoJSON feed for real-time earthquake events
and stores them as ingested_events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import ingestion_config as cfg
from app.services.ingestion import memory_store
from app.services.ingestion.mock_data_service import generate_mock_earthquakes

logger = logging.getLogger("ingestion.usgs")

# Magnitude → our severity
_MAG_SEVERITY: list[tuple] = [
    (7.0, "critical"),
    (6.0, "high"),
    (5.0, "medium"),
    (0.0, "low"),
]


def _magnitude_to_severity(mag: float) -> str:
    for threshold, severity in _MAG_SEVERITY:
        if mag >= threshold:
            return severity
    return "low"


class USGSService:
    """Polls the USGS GeoJSON earthquake feed."""

    def __init__(self) -> None:
        self.feed_url = cfg.USGS_FEED_URL
        self.min_magnitude = cfg.USGS_MIN_MAGNITUDE

    async def poll(self) -> list[dict[str, Any]]:
        """Fetch USGS feed, filter by magnitude, deduplicate, and store.
        Falls back to realistic mock data if the API is unreachable."""
        try:
            data = await self._fetch_feed()
            features = data.get("features", [])
            events = self._parse_features(features)
            # If real API returned nothing, supplement with mock data
            if not events:
                logger.info("USGS returned 0 events – generating mock earthquakes")
                events = generate_mock_earthquakes()
            new_events = await self._deduplicate_and_store(events)
            logger.info("USGS poll complete – %d new earthquakes ingested", len(new_events))
            return new_events
        except Exception:
            logger.warning("USGS API unreachable – using mock earthquake data")
            events = generate_mock_earthquakes()
            new_events = await self._deduplicate_and_store(events)
            logger.info("Mock USGS poll – %d earthquakes ingested", len(new_events))
            return new_events

    # ── internals ───────────────────────────────────────────────────

    async def _fetch_feed(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(self.feed_url)
            resp.raise_for_status()
            return resp.json()

    def _parse_features(self, features: list[dict[str, Any]]) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [None, None, None])

            mag = props.get("mag", 0)
            if mag is None or mag < self.min_magnitude:
                continue

            lon, lat = coords[0], coords[1]
            depth_km = coords[2] if len(coords) > 2 else None
            event_time = props.get("time")

            parsed.append(
                {
                    "external_id": f"usgs-{feat.get('id', '')}",
                    "event_type": "earthquake",
                    "title": props.get("title", props.get("place", "Earthquake")),
                    "description": (f"M{mag} earthquake at {props.get('place', 'unknown')}. Depth: {depth_km} km."),
                    "severity": _magnitude_to_severity(mag),
                    "latitude": lat,
                    "longitude": lon,
                    "location_name": props.get("place"),
                    "raw_payload": {
                        "usgs_id": feat.get("id"),
                        "magnitude": mag,
                        "mag_type": props.get("magType"),
                        "depth_km": depth_km,
                        "place": props.get("place"),
                        "time": event_time,
                        "url": props.get("url"),
                        "tsunami": props.get("tsunami"),
                        "felt": props.get("felt"),
                        "alert": props.get("alert"),
                        "status": props.get("status"),
                        "type": props.get("type"),
                    },
                }
            )

        return parsed

    async def _deduplicate_and_store(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items:
            return []

        source_id = memory_store.get_source_id("usgs_earthquakes")

        rows = []
        for item in items:
            ext_id = item.get("external_id")
            if ext_id and memory_store.event_exists(ext_id):
                continue
            rows.append(
                {
                    "id": str(uuid4()),
                    "source_id": source_id,
                    **item,
                    "ingested_at": datetime.now(UTC).isoformat(),
                }
            )

        return memory_store.add_ingested_events(rows)

    @staticmethod
    def auto_create_disaster_payload(event: dict[str, Any]) -> dict[str, Any]:
        """Build a disaster-create payload from a USGS earthquake event."""
        raw = event.get("raw_payload", {})
        return {
            "type": "earthquake",
            "severity": event.get("severity", "medium"),
            "title": event.get("title", "Earthquake"),
            "description": event.get("description", ""),
            "status": "active",
            "start_date": datetime.now(UTC).isoformat(),
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
            "affected_population": None,
            "metadata": {
                "magnitude": raw.get("magnitude"),
                "depth_km": raw.get("depth_km"),
                "usgs_url": raw.get("url"),
            },
        }
