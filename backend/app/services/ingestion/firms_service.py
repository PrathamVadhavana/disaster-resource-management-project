"""
NASA FIRMS (Fire Information for Resource Management System) service.

Fetches active fire/hotspot data from the FIRMS API and stores them in
the satellite_observations table.  Results feed the spread predictor.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import ingestion_config as cfg
from app.database import supabase_admin
from app.services.ingestion.mock_data_service import generate_mock_fire_hotspots

logger = logging.getLogger("ingestion.firms")


class FIRMSService:
    """Polls NASA FIRMS CSV API for fire hotspot observations."""

    def __init__(self) -> None:
        self.api_key = cfg.FIRMS_API_KEY
        self.base_url = cfg.FIRMS_BASE_URL
        self.source = cfg.FIRMS_SOURCE

    async def poll(
        self,
        bbox: Optional[str] = None,
        days: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Fetch FIRMS hotspot data.  *bbox* is ``"west,south,east,north"``
        (e.g. ``"-125,25,-65,50"`` for CONUS).  Defaults to world.

        Returns list of stored satellite_observation rows.
        """
        if not self.api_key:
            logger.info("No FIRMS_API_KEY – using mock fire hotspot data")
            hotspots = generate_mock_fire_hotspots()
            stored = await self._store_observations(hotspots)
            logger.info("Mock FIRMS poll complete – %d hotspots stored", len(stored))
            return stored

        try:
            csv_text = await self._fetch_csv(bbox, days)
            hotspots = self._parse_csv(csv_text)
            stored = await self._store_observations(hotspots)
            logger.info("FIRMS poll complete – %d hotspots stored", len(stored))
            return stored
        except Exception:
            logger.exception("FIRMS poll failed")
            return []

    # ── internals ───────────────────────────────────────────────────

    async def _fetch_csv(self, bbox: Optional[str], days: int) -> str:
        # FIRMS CSV endpoint:
        # https://firms.modaps.eosdis.nasa.gov/api/area/csv/{API_KEY}/{SOURCE}/{BBOX}/{DAYS}
        parts = [self.base_url, self.api_key, self.source]
        if bbox:
            parts.append(bbox)
        else:
            parts.append("world")
        parts.append(str(days))
        url = "/".join(parts)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    def _parse_csv(self, csv_text: str) -> List[Dict[str, Any]]:
        reader = csv.DictReader(io.StringIO(csv_text))
        results: List[Dict[str, Any]] = []

        for row in reader:
            try:
                lat = float(row.get("latitude", 0))
                lon = float(row.get("longitude", 0))
                brightness = self._float_or_none(row.get("bright_ti4") or row.get("brightness"))
                frp = self._float_or_none(row.get("frp"))
                confidence = row.get("confidence", "").lower()
                satellite = row.get("satellite", "")
                instrument = row.get("instrument", "")
                acq_date = row.get("acq_date", "")
                acq_time = row.get("acq_time", "0000")
                daynight = row.get("daynight", "")

                # Build datetime from acq_date + acq_time
                try:
                    acq_dt = datetime.strptime(f"{acq_date} {acq_time}", "%Y-%m-%d %H%M").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    acq_dt = datetime.now(timezone.utc)

                results.append({
                    "id": str(uuid4()),
                    "source": "firms",
                    "external_id": f"firms-{lat}-{lon}-{acq_date}-{acq_time}",
                    "latitude": lat,
                    "longitude": lon,
                    "brightness": brightness,
                    "frp": frp,
                    "confidence": confidence if confidence in ("low", "nominal", "high") else None,
                    "satellite": satellite,
                    "instrument": instrument,
                    "acq_datetime": acq_dt.isoformat(),
                    "daynight": daynight,
                    "raw_payload": dict(row),
                })
            except Exception:
                logger.debug("Skipping unparseable FIRMS row: %s", row)

        return results

    async def _store_observations(self, observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Batch-insert into satellite_observations, skipping duplicates."""
        if not observations:
            return []

        # Upsert-like: filter out already-existing external_ids
        ext_ids = [o["external_id"] for o in observations if o.get("external_id")]
        existing_ids: set = set()
        if ext_ids:
            # Check in batches of 100
            for i in range(0, len(ext_ids), 100):
                batch = ext_ids[i : i + 100]
                resp = (
                    supabase_admin.table("satellite_observations")
                    .select("external_id")
                    .in_("external_id", batch)
                    .execute()
                )
                existing_ids.update(r["external_id"] for r in (resp.data or []))

        new_obs = [o for o in observations if o.get("external_id") not in existing_ids]
        if new_obs:
            # Insert in batches of 500
            for i in range(0, len(new_obs), 500):
                batch = new_obs[i : i + 500]
                supabase_admin.table("satellite_observations").insert(batch).execute()

        return new_obs

    @staticmethod
    def _float_or_none(val: Any) -> Optional[float]:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    async def hotspot_summary_for_area(
        lat: float, lon: float, radius_deg: float = 1.0
    ) -> Dict[str, Any]:
        """
        Summarise recent satellite observations near a coordinate.
        Useful as spread-predictor input.
        """
        resp = (
            supabase_admin.table("satellite_observations")
            .select("*")
            .gte("latitude", lat - radius_deg)
            .lte("latitude", lat + radius_deg)
            .gte("longitude", lon - radius_deg)
            .lte("longitude", lon + radius_deg)
            .order("acq_datetime", desc=True)
            .limit(100)
            .execute()
        )
        rows = resp.data or []
        return {
            "hotspot_count": len(rows),
            "avg_frp": (sum(r.get("frp", 0) or 0 for r in rows) / len(rows)) if rows else 0,
            "max_brightness": max((r.get("brightness", 0) or 0 for r in rows), default=0),
            "latest": rows[0] if rows else None,
        }
