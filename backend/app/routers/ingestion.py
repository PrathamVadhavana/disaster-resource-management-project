"""
Phase 4 – Ingestion API router.

Provides endpoints for:
  - GET  /api/ingestion/status          – health / status of all feeds
  - POST /api/ingestion/poll/{source}   – manually trigger a single feed poll
  - GET  /api/ingestion/events          – list recent ingested events
  - GET  /api/ingestion/weather         – list recent weather observations
  - GET  /api/ingestion/satellites      – list recent satellite observations
  - GET  /api/ingestion/alerts          – list alert notifications
  - POST /api/ingestion/start           – start the orchestrator (admin)
  - POST /api/ingestion/stop            – stop the orchestrator (admin)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services.ingestion import memory_store

router = APIRouter()

# Global orchestrator reference (set via set_orchestrator at startup)
_orchestrator = None


def set_orchestrator(orch) -> None:
    global _orchestrator
    _orchestrator = orch


def get_orchestrator():
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Ingestion orchestrator not initialized")
    return _orchestrator


# ── Status & control ────────────────────────────────────────────────


@router.get("/status")
async def ingestion_status():
    """Return status of all external data source feeds."""
    orch = get_orchestrator()
    return await orch.get_status()


@router.post("/poll/{source_name}")
async def manual_poll(source_name: str):
    """Manually trigger a single source poll (weather, gdacs, usgs, firms, social)."""
    orch = get_orchestrator()
    try:
        events = await orch.poll_source(source_name)
        return {
            "source": source_name,
            "events_ingested": len(events) if events else 0,
            "polled_at": datetime.now(UTC).isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Poll failed: {str(e)}")


@router.post("/start")
async def start_orchestrator():
    """Start the background ingestion loops."""
    orch = get_orchestrator()
    if orch.is_running:
        return {"message": "Orchestrator already running"}
    await orch.start()
    return {"message": "Orchestrator started", "status": "running"}


@router.post("/stop")
async def stop_orchestrator():
    """Stop all background ingestion loops."""
    orch = get_orchestrator()
    if not orch.is_running:
        return {"message": "Orchestrator already stopped"}
    await orch.stop()
    return {"message": "Orchestrator stopped", "status": "idle"}


# ── Ingested events ────────────────────────────────────────────────


@router.get("/events")
async def list_ingested_events(
    event_type: str | None = Query(None, description="Filter by event type"),
    severity: str | None = Query(None, description="Filter by severity"),
    processed: bool | None = Query(None, description="Filter by processed status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List recent ingested events with optional filters (served from memory)."""
    events = memory_store.query_ingested_events(
        event_type=event_type,
        severity=severity,
        processed=processed,
        limit=limit,
        offset=offset,
    )

    # Enrich with source info from memory
    sources = {s["id"]: s for s in memory_store.get_all_sources()}
    for e in events:
        e["external_data_sources"] = sources.get(e.get("source_id"))

    return {
        "events": events,
        "count": len(events),
        "offset": offset,
        "limit": limit,
    }


@router.get("/events/{event_id}")
async def get_ingested_event(event_id: str):
    """Get a specific ingested event."""
    event = memory_store.get_ingested_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    sources = {s["id"]: s for s in memory_store.get_all_sources()}
    event["external_data_sources"] = sources.get(event.get("source_id"))
    return event


# ── Weather observations ────────────────────────────────────────────


@router.get("/weather")
async def list_weather_observations(
    location_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent weather observations (from memory)."""
    observations = memory_store.query_weather(location_id=location_id, limit=limit)
    return {"observations": observations, "count": len(observations)}


@router.get("/weather/latest/{location_id}")
async def latest_weather(location_id: str):
    """Get the most recent weather observation for a location."""
    row = memory_store.latest_weather_for_location(location_id)
    if not row:
        raise HTTPException(status_code=404, detail="No weather data for this location")
    return row


# ── Satellite observations ──────────────────────────────────────────


@router.get("/satellites")
async def list_satellite_observations(
    disaster_id: str | None = Query(None),
    confidence: str | None = Query(None, description="low, nominal, high"),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent satellite / fire hotspot observations (from memory)."""
    observations = memory_store.query_satellites(disaster_id=disaster_id, confidence=confidence, limit=limit)
    return {"observations": observations, "count": len(observations)}


# ── Alert notifications ────────────────────────────────────────────


@router.get("/alerts")
async def list_alert_notifications(
    severity: str | None = Query(None),
    status: str | None = Query(None, description="pending, sent, failed, acknowledged"),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent alert notifications (from memory)."""
    alerts = memory_store.query_alerts(severity=severity, status=status, limit=limit)
    return {"alerts": alerts, "count": len(alerts)}


# ── Data source management ──────────────────────────────────────────


@router.get("/sources")
async def list_data_sources():
    """List all registered external data sources (from memory)."""
    return {"sources": memory_store.get_all_sources()}


@router.patch("/sources/{source_id}")
async def update_data_source(source_id: str, body: dict[str, Any]):
    """Update a data source config (e.g. toggle is_active, change interval)."""
    allowed_fields = {"is_active", "poll_interval_s"}
    update_data = {k: v for k, v in body.items() if k in allowed_fields}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    # Find and update the source in memory
    sources = memory_store.get_all_sources()
    for src in sources:
        if src["id"] == source_id:
            src.update(update_data)
            return src
    raise HTTPException(status_code=404, detail="Data source not found")
