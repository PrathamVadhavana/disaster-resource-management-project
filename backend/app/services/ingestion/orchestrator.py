"""
Ingestion Orchestrator — unified scheduler that coordinates all external feeds.

Runs as a collection of async background loops managed by FastAPI's lifespan.
Each feed runs on its own interval.  New events trigger batch predictions
and, when severity is critical, dispatch NGO notifications.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.core.config import ingestion_config as cfg
from app.database import supabase_admin
from app.services.ingestion.weather_service import WeatherService
from app.services.ingestion.gdacs_service import GDACSService
from app.services.ingestion.usgs_service import USGSService
from app.services.ingestion.firms_service import FIRMSService
from app.services.ingestion.social_service import SocialMediaService
from app.services.ingestion.alert_service import AlertNotificationService

logger = logging.getLogger("ingestion.orchestrator")


class IngestionOrchestrator:
    """
    Manages feed-polling loops and wires results into the prediction
    pipeline and notification system.
    """

    def __init__(self) -> None:
        self.weather = WeatherService()
        self.gdacs = GDACSService()
        self.usgs = USGSService()
        self.firms = FIRMSService()
        self.social = SocialMediaService()
        self.alerts = AlertNotificationService()

        self._tasks: List[asyncio.Task] = []
        self._running = False
        self._ml_service = None  # set after startup via set_ml_service()

    # ── lifecycle ───────────────────────────────────────────────────

    def set_ml_service(self, ml_service) -> None:
        """Inject the MLService singleton after models are loaded."""
        self._ml_service = ml_service

    async def start(self) -> None:
        """Launch all polling loops as asyncio tasks."""
        if not cfg.INGESTION_ENABLED:
            logger.info("Ingestion disabled via INGESTION_ENABLED=false")
            return

        self._running = True
        logger.info("Starting ingestion orchestrator …")

        self._tasks = [
            asyncio.create_task(self._loop("weather", self._poll_weather, cfg.WEATHER_POLL_INTERVAL_S)),
            asyncio.create_task(self._loop("gdacs", self._poll_gdacs, cfg.GDACS_POLL_INTERVAL_S)),
            asyncio.create_task(self._loop("usgs", self._poll_usgs, cfg.USGS_POLL_INTERVAL_S)),
            asyncio.create_task(self._loop("firms", self._poll_firms, cfg.FIRMS_POLL_INTERVAL_S)),
            asyncio.create_task(self._loop("social", self._poll_social, cfg.SOCIAL_POLL_INTERVAL_S)),
        ]

        logger.info("All feed loops started (mock fallback enabled for missing API keys)")

    async def stop(self) -> None:
        """Cancel all polling tasks gracefully."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Ingestion orchestrator stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── generic loop wrapper ────────────────────────────────────────

    async def _loop(self, name: str, poll_fn, interval_s: int) -> None:
        """Run *poll_fn* every *interval_s* seconds until cancelled."""
        logger.info("Feed loop [%s] started – interval %ds", name, interval_s)
        while self._running:
            try:
                await poll_fn()
                await self._update_source_status(name, "success")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Feed loop [%s] error", name)
                await self._update_source_status(name, "error", str(exc))
            await asyncio.sleep(interval_s)

    # ── individual poll handlers ────────────────────────────────────

    async def _poll_weather(self) -> None:
        observations = await self.weather.poll()
        # Weather observations enrich prediction features rather than
        # creating new disaster events.  No auto-prediction triggered.
        logger.debug("Weather: %d observations", len(observations))

    async def _poll_gdacs(self) -> None:
        events = await self.gdacs.poll()
        for event in events:
            await self._process_disaster_event(event, "gdacs")

    async def _poll_usgs(self) -> None:
        events = await self.usgs.poll()
        for event in events:
            await self._process_disaster_event(event, "usgs")

    async def _poll_firms(self) -> None:
        await self.firms.poll()
        # Satellite hotspots are consumed directly by the spread predictor;
        # no individual disaster events are created per hotspot row.

    async def _poll_social(self) -> None:
        """Poll social media — uses mock data when no API token is set."""
        events = await self.social.poll()
        for event in events:
            # Social signals with critical/high severity trigger disaster pipeline
            if event.get("severity") in ("critical", "high"):
                await self._process_disaster_event(event, "social")
            else:
                await self.alerts.evaluate_and_notify(event)

    # ── event → disaster → predictions pipeline ────────────────────

    async def _process_disaster_event(self, event: Dict[str, Any], source: str) -> None:
        """
        For GDACS/USGS events:
         1. Auto-create (or find) a matching disaster record
         2. Run batch predictions (severity + spread + impact)
         3. If critical, dispatch NGO alerts
        """
        disaster_id = await self._auto_create_disaster(event, source)
        if not disaster_id:
            return

        # Mark ingested event as processed and link disaster
        event_id = event.get("id")
        if event_id:
            supabase_admin.table("ingested_events").update({
                "processed": True,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "disaster_id": disaster_id,
            }).eq("id", event_id).execute()

        # Trigger batch predictions via ML service
        prediction_ids = await self._run_batch_predictions(event, disaster_id)

        # Link prediction IDs back to the ingested event
        if prediction_ids and event_id:
            supabase_admin.table("ingested_events").update({
                "prediction_ids": prediction_ids,
            }).eq("id", event_id).execute()

        # Evaluate alert threshold
        await self.alerts.evaluate_and_notify(
            event,
            disaster_id=disaster_id,
            prediction_id=prediction_ids[0] if prediction_ids else None,
        )

    async def _auto_create_disaster(self, event: Dict[str, Any], source: str) -> Optional[str]:
        """Create or find a disaster record for the event."""
        try:
            lat = event.get("latitude")
            lon = event.get("longitude")

            # Try to find a matching location
            location_id = await self._find_or_create_location(event)

            raw = event.get("raw_payload", {})
            disaster_type = raw.get("disaster_type_mapped", event.get("event_type", "other"))
            if disaster_type == "earthquake":
                pass  # already correct
            elif disaster_type not in (
                "earthquake", "flood", "hurricane", "tornado", "wildfire",
                "tsunami", "drought", "landslide", "volcano",
            ):
                disaster_type = "other"

            disaster_data = {
                "id": str(uuid4()),
                "type": disaster_type,
                "severity": event.get("severity", "medium"),
                "title": event.get("title", f"Auto-detected {disaster_type}"),
                "description": event.get("description", ""),
                "status": "active",
                "start_date": datetime.now(timezone.utc).isoformat(),
                "location_id": location_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            resp = supabase_admin.table("disasters").insert(disaster_data).execute()
            if resp.data:
                did = resp.data[0]["id"]
                logger.info("Auto-created disaster %s from %s event", did, source)
                return did
            return None

        except Exception:
            logger.exception("Failed to auto-create disaster from %s event", source)
            return None

    async def _find_or_create_location(self, event: Dict[str, Any]) -> str:
        """Find a nearby location or create a new one."""
        lat = event.get("latitude")
        lon = event.get("longitude")
        name = event.get("location_name", "Auto-detected Location")

        if lat is not None and lon is not None:
            # Look for a location within ~0.5 degrees (~55 km)
            resp = (
                supabase_admin.table("locations")
                .select("id")
                .gte("latitude", lat - 0.5)
                .lte("latitude", lat + 0.5)
                .gte("longitude", lon - 0.5)
                .lte("longitude", lon + 0.5)
                .limit(1)
                .execute()
            )
            if resp.data:
                return resp.data[0]["id"]

        # Create a new location
        loc_data = {
            "id": str(uuid4()),
            "name": name[:255] if name else "Unknown",
            "type": "city",
            "latitude": lat or 0,
            "longitude": lon or 0,
            "city": "Unknown",
            "state": "Unknown",
            "country": "Unknown",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = supabase_admin.table("locations").insert(loc_data).execute()
        return resp.data[0]["id"] if resp.data else loc_data["id"]

    async def _run_batch_predictions(self, event: Dict[str, Any], disaster_id: str) -> List[str]:
        """
        Run severity + spread + impact predictions using the ML service.
        Returns list of prediction UUIDs.
        """
        if not self._ml_service:
            logger.warning("ML service not available – skipping predictions")
            return []

        prediction_ids: List[str] = []
        raw = event.get("raw_payload", {})
        lat = event.get("latitude")
        lon = event.get("longitude")

        # Get location_id from the disaster record
        location_id = None
        try:
            disaster_resp = supabase_admin.table("disasters").select("location_id").eq("id", disaster_id).limit(1).execute()
            if disaster_resp.data:
                location_id = disaster_resp.data[0].get("location_id")
        except Exception:
            logger.debug("Could not fetch location_id for disaster %s", disaster_id)

        if not location_id:
            logger.warning("No location_id for disaster %s – skipping predictions", disaster_id)
            return []

        # Fetch latest weather features for the location
        weather_features = {}
        if lat and lon:
            from app.services.ingestion.weather_service import WeatherService
            weather_features = await WeatherService.latest_features_for_location(
                location_id
            )

        # Default features if weather unavailable
        base_features = {
            "temperature": weather_features.get("temperature", 25),
            "humidity": weather_features.get("humidity", 50),
            "wind_speed": weather_features.get("wind_speed", 10),
            "pressure": weather_features.get("pressure", 1013),
        }

        disaster_type = raw.get("disaster_type_mapped", event.get("event_type", "other"))

        # 1. Severity prediction
        try:
            severity_features = {
                **base_features,
                "disaster_type": disaster_type,
            }
            result = await self._ml_service.predict("severity", severity_features)
            pid = str(uuid4())
            pred_data = {
                "id": pid,
                "disaster_id": disaster_id,
                "location_id": location_id,
                "prediction_type": "severity",
                "features": severity_features,
                "confidence_score": min(result.get("confidence_score", 0.5), 1.0),
                "predicted_severity": result.get("predicted_severity"),
                "model_version": result.get("model_version", "1.0.0"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase_admin.table("predictions").insert(pred_data).execute()
            prediction_ids.append(pid)
        except Exception:
            logger.exception("Severity prediction failed for event %s", event.get("id"))

        # 2. Spread prediction
        try:
            spread_features = {
                "current_area": raw.get("magnitude", 10) * 5 if raw.get("magnitude") else 50,
                "wind_speed": base_features["wind_speed"],
                "terrain_type": "mixed",
            }
            result = await self._ml_service.predict("spread", spread_features)
            pid = str(uuid4())
            pred_data = {
                "id": pid,
                "disaster_id": disaster_id,
                "location_id": location_id,
                "prediction_type": "spread",
                "features": spread_features,
                "confidence_score": min(result.get("confidence_score", 0.5), 1.0),
                "affected_area_km": result.get("predicted_area_km2"),
                "model_version": result.get("model_version", "1.0.0"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase_admin.table("predictions").insert(pred_data).execute()
            prediction_ids.append(pid)
        except Exception:
            logger.exception("Spread prediction failed for event %s", event.get("id"))

        # 3. Impact prediction
        try:
            severity_score_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            impact_features = {
                "severity_score": severity_score_map.get(event.get("severity", "medium"), 2),
                "affected_population": int(raw.get("gdacs_population", 0) or 0) or 10000,
            }
            result = await self._ml_service.predict("impact", impact_features)
            pid = str(uuid4())
            pred_data = {
                "id": pid,
                "disaster_id": disaster_id,
                "location_id": location_id,
                "prediction_type": "impact",
                "features": impact_features,
                "confidence_score": min(result.get("confidence_score", 0.5), 1.0),
                "predicted_casualties": result.get("predicted_casualties"),
                "model_version": result.get("model_version", "1.0.0"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            supabase_admin.table("predictions").insert(pred_data).execute()
            prediction_ids.append(pid)
        except Exception:
            logger.exception("Impact prediction failed for event %s", event.get("id"))

        logger.info("Batch predictions complete for event %s: %d predictions", event.get("id"), len(prediction_ids))
        return prediction_ids

    # ── source status bookkeeping ───────────────────────────────────

    async def _update_source_status(self, source_name_key: str, status: str, error: Optional[str] = None) -> None:
        """Update last_polled_at and last_status in external_data_sources."""
        # Map loop name → source_name in DB
        name_map = {
            "weather": "openweathermap",
            "gdacs": "gdacs",
            "usgs": "usgs_earthquakes",
            "firms": "nasa_firms",
            "social": "social_media",
        }
        source_name = name_map.get(source_name_key, source_name_key)
        try:
            update: Dict[str, Any] = {
                "last_polled_at": datetime.now(timezone.utc).isoformat(),
                "last_status": status,
            }
            if error:
                update["last_error"] = error[:500]
            else:
                update["last_error"] = None

            supabase_admin.table("external_data_sources").update(update).eq("source_name", source_name).execute()
        except Exception:
            logger.debug("Failed to update source status for %s", source_name)

    # ── manual trigger (used by API router) ─────────────────────────

    async def poll_source(self, source_name: str) -> List[Dict[str, Any]]:
        """Manually trigger a single source poll. Returns new events/observations."""
        dispatch = {
            "weather": self._poll_weather_return,
            "gdacs": self.gdacs.poll,
            "usgs": self.usgs.poll,
            "firms": self._poll_firms_return,
            "social": self.social.poll,
        }
        fn = dispatch.get(source_name)
        if not fn:
            raise ValueError(f"Unknown source: {source_name}")
        return await fn()

    async def _poll_weather_return(self) -> List[Dict[str, Any]]:
        return await self.weather.poll()

    async def _poll_firms_return(self) -> List[Dict[str, Any]]:
        return await self.firms.poll()

    # ── status / health ─────────────────────────────────────────────

    async def get_status(self) -> Dict[str, Any]:
        """Return the current status of all data sources."""
        resp = supabase_admin.table("external_data_sources").select("*").execute()
        sources = resp.data or []
        return {
            "orchestrator_running": self._running,
            "sources": [
                {
                    "name": s["source_name"],
                    "type": s["source_type"],
                    "active": s["is_active"],
                    "last_polled": s.get("last_polled_at"),
                    "status": s.get("last_status"),
                    "error": s.get("last_error"),
                    "interval_s": s["poll_interval_s"],
                }
                for s in sources
            ],
        }
