"""
Social Media Signals service.

Monitors Twitter/X for SOS and disaster-related keywords via the
Recent Search API (v2).  Results are stored as ingested_events.

NOTE: Disabled by default — requires a paid Twitter/X API bearer token.
The rest of the platform works fully without this service.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import ingestion_config as cfg
from app.database import supabase_admin
from app.services.ingestion.mock_data_service import generate_mock_social_signals

logger = logging.getLogger("ingestion.social")


class SocialMediaService:
    """Polls Twitter/X v2 Recent Search for disaster-related keywords."""

    def __init__(self) -> None:
        self.bearer_token = cfg.TWITTER_BEARER_TOKEN
        self.keywords = cfg.SOCIAL_KEYWORDS
        self._last_since_id: Optional[str] = None

    async def poll(self) -> List[Dict[str, Any]]:
        """Search for recent tweets matching disaster keywords.
        Falls back to mock SOS data when no API token is configured."""
        if not self.bearer_token:
            logger.info("No TWITTER_BEARER_TOKEN – using mock social SOS data")
            events = generate_mock_social_signals()
            new_events = await self._deduplicate_and_store(events)
            logger.info("Mock social poll – %d signals ingested", len(new_events))
            return new_events

        try:
            tweets = await self._search_recent()
            events = self._tweets_to_events(tweets)
            new_events = await self._deduplicate_and_store(events)
            logger.info("Social poll complete – %d new signals ingested", len(new_events))
            return new_events
        except Exception:
            logger.warning("Twitter API failed – falling back to mock data")
            events = generate_mock_social_signals()
            new_events = await self._deduplicate_and_store(events)
            return new_events

    # ── internals ───────────────────────────────────────────────────

    async def _search_recent(self) -> List[Dict[str, Any]]:
        """Call Twitter v2 Recent Search endpoint."""
        query = " OR ".join(f'"{kw}"' for kw in self.keywords)
        query += " -is:retweet lang:en"

        url = "https://api.twitter.com/2/tweets/search/recent"
        params: Dict[str, Any] = {
            "query": query,
            "max_results": min(cfg.MAX_EVENTS_PER_POLL, 100),
            "tweet.fields": "created_at,geo,text,author_id,public_metrics",
            "expansions": "geo.place_id",
            "place.fields": "full_name,geo,country",
        }
        if self._last_since_id:
            params["since_id"] = self._last_since_id

        headers = {"Authorization": f"Bearer {self.bearer_token}"}

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code == 429:
                logger.warning("Twitter rate limit hit – will retry next cycle")
                return []
            resp.raise_for_status()

        data = resp.json()
        tweets = data.get("data", [])
        places = {p["id"]: p for p in (data.get("includes", {}).get("places", []))}

        # Enrich tweets with place info
        for tw in tweets:
            geo = tw.get("geo", {})
            place_id = geo.get("place_id")
            if place_id and place_id in places:
                tw["_place"] = places[place_id]

        # Track pagination
        meta = data.get("meta", {})
        newest_id = meta.get("newest_id")
        if newest_id:
            self._last_since_id = newest_id

        return tweets

    def _tweets_to_events(self, tweets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        for tw in tweets:
            text = tw.get("text", "")
            tweet_id = tw.get("id", "")

            # Attempt to extract coordinates
            lat, lon, location_name = self._extract_location(tw)

            # Estimate severity from keyword density
            severity = self._estimate_severity(text)

            events.append({
                "external_id": f"twitter-{tweet_id}",
                "event_type": "social_sos",
                "title": f"Social SOS: {text[:80]}{'...' if len(text) > 80 else ''}",
                "description": text,
                "severity": severity,
                "latitude": lat,
                "longitude": lon,
                "location_name": location_name,
                "raw_payload": {
                    "tweet_id": tweet_id,
                    "author_id": tw.get("author_id"),
                    "created_at": tw.get("created_at"),
                    "text": text,
                    "public_metrics": tw.get("public_metrics"),
                },
            })

        return events

    def _extract_location(self, tweet: Dict[str, Any]) -> tuple:
        """Best-effort coordinate + name extraction from tweet geo data."""
        geo = tweet.get("geo", {})
        coords = geo.get("coordinates", {}).get("coordinates")
        if coords and len(coords) == 2:
            return coords[1], coords[0], None  # GeoJSON is [lon, lat]

        place = tweet.get("_place", {})
        if place:
            bbox = place.get("geo", {}).get("bbox", [])
            if len(bbox) == 4:
                lat = (bbox[1] + bbox[3]) / 2
                lon = (bbox[0] + bbox[2]) / 2
                return lat, lon, place.get("full_name")

        return None, None, None

    @staticmethod
    def _estimate_severity(text: str) -> str:
        """Heuristic severity from tweet text."""
        text_lower = text.lower()
        critical_words = ["trapped", "dying", "urgent", "critical", "sos", "life threatening"]
        high_words = ["help needed", "rescue", "emergency", "injured", "flood", "earthquake"]

        critical_score = sum(1 for w in critical_words if w in text_lower)
        high_score = sum(1 for w in high_words if w in text_lower)

        if critical_score >= 2:
            return "critical"
        if critical_score >= 1 or high_score >= 2:
            return "high"
        if high_score >= 1:
            return "medium"
        return "low"

    async def _deduplicate_and_store(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items:
            return []

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
                    continue

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
            .eq("source_name", "social_media")
            .limit(1)
            .execute()
        )
        if resp.data:
            return resp.data[0]["id"]
        # Auto-create the source entry
        new_id = str(uuid4())
        supabase_admin.table("external_data_sources").insert({
            "id": new_id,
            "source_name": "social_media",
            "source_type": "api",
            "base_url": "https://api.twitter.com/2",
            "is_active": True,
            "poll_interval_s": 300,
        }).execute()
        return new_id
