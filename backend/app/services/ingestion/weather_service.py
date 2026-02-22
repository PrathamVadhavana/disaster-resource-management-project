"""
OpenWeatherMap integration service.

Fetches current weather + short-term forecast for tracked locations
and stores observations in the weather_observations table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import ingestion_config as cfg
from app.database import supabase_admin
from app.services.ingestion.mock_data_service import generate_mock_weather

logger = logging.getLogger("ingestion.weather")


class WeatherService:
    """Polls OpenWeatherMap for current weather conditions."""

    def __init__(self) -> None:
        self.api_key = cfg.OPENWEATHERMAP_API_KEY
        self.base_url = cfg.OPENWEATHERMAP_BASE_URL

    # ── public ──────────────────────────────────────────────────────

    async def poll(self, locations: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Fetch current weather for each tracked location.

        If *locations* is ``None``, the service queries the ``locations``
        table for every row that has non-null lat/lon.

        Returns a list of stored weather_observation rows.
        """
        if not self.api_key:
            logger.info("No OPENWEATHERMAP_API_KEY – using mock weather data")
            results = generate_mock_weather(locations)
            # Mock weather locations may not exist in DB — strip location_id
            # to avoid FK violations (weather_observations.location_id is nullable)
            for obs in results:
                obs["location_id"] = None
            if results:
                await self._store_observations(results)
            logger.info("Mock weather poll complete – %d observations stored", len(results))
            return results

        if locations is None:
            locations = await self._get_tracked_locations()

        results: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=15) as client:
            for loc in locations:
                try:
                    obs = await self._fetch_current(client, loc)
                    if obs:
                        results.append(obs)
                except Exception:
                    logger.exception("Weather fetch failed for %s", loc.get("name", loc.get("id")))

        if results:
            await self._store_observations(results)

        logger.info("Weather poll complete – %d observations stored", len(results))
        return results

    async def fetch_for_coordinates(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """One-off fetch for a specific coordinate pair."""
        if not self.api_key:
            # Return mock data for the coordinate
            mocks = generate_mock_weather([{"id": "adhoc", "latitude": lat, "longitude": lon}])
            return mocks[0] if mocks else None
        async with httpx.AsyncClient(timeout=15) as client:
            return await self._fetch_current(client, {"latitude": lat, "longitude": lon})

    # ── internals ───────────────────────────────────────────────────

    async def _get_tracked_locations(self) -> List[Dict[str, Any]]:
        resp = supabase_admin.table("locations").select("id, name, latitude, longitude").execute()
        return resp.data or []

    async def _fetch_current(self, client: httpx.AsyncClient, loc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if lat is None or lon is None:
            return None

        url = f"{self.base_url}/weather"
        params = {"lat": lat, "lon": lon, "appid": self.api_key, "units": "metric"}
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()

        main = data.get("main", {})
        wind = data.get("wind", {})
        weather_list = data.get("weather", [{}])

        return {
            "id": str(uuid4()),
            "location_id": loc.get("id"),
            "latitude": lat,
            "longitude": lon,
            "temperature_c": main.get("temp"),
            "humidity_pct": main.get("humidity"),
            "wind_speed_ms": wind.get("speed"),
            "wind_deg": wind.get("deg"),
            "pressure_hpa": main.get("pressure"),
            "precipitation_mm": data.get("rain", {}).get("1h", 0) or data.get("snow", {}).get("1h", 0),
            "visibility_m": data.get("visibility"),
            "weather_main": weather_list[0].get("main") if weather_list else None,
            "weather_desc": weather_list[0].get("description") if weather_list else None,
            "observed_at": datetime.fromtimestamp(data.get("dt", 0), tz=timezone.utc).isoformat(),
            "source": "openweathermap",
            "raw_payload": data,
        }

    async def _store_observations(self, observations: List[Dict[str, Any]]) -> None:
        supabase_admin.table("weather_observations").insert(observations).execute()

    # ── Utility: build prediction features from latest weather ──────

    @staticmethod
    async def latest_features_for_location(location_id: str) -> Dict[str, Any]:
        """
        Return the latest weather observation for a location as a dict
        formatted for PredictionInput.features.
        """
        resp = (
            supabase_admin
            .table("weather_observations")
            .select("*")
            .eq("location_id", location_id)
            .order("observed_at", desc=True)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return {}
        row = resp.data[0]
        return {
            "temperature": row.get("temperature_c", 25),
            "humidity": row.get("humidity_pct", 50),
            "wind_speed": row.get("wind_speed_ms", 5),
            "pressure": row.get("pressure_hpa", 1013),
            "precipitation": row.get("precipitation_mm", 0),
        }
