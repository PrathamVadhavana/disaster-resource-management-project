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

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import supabase_admin

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
            "polled_at": datetime.now(timezone.utc).isoformat(),
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
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    processed: Optional[bool] = Query(None, description="Filter by processed status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List recent ingested events with optional filters."""
    query = supabase_admin.table("ingested_events").select(
        "*, external_data_sources(source_name, source_type)"
    )

    if event_type:
        query = query.eq("event_type", event_type)
    if severity:
        query = query.eq("severity", severity)
    if processed is not None:
        query = query.eq("processed", processed)

    query = query.order("ingested_at", desc=True).range(offset, offset + limit - 1)
    resp = query.execute()

    return {
        "events": resp.data or [],
        "count": len(resp.data or []),
        "offset": offset,
        "limit": limit,
    }


@router.get("/events/{event_id}")
async def get_ingested_event(event_id: str):
    """Get a specific ingested event."""
    resp = (
        supabase_admin.table("ingested_events")
        .select("*, external_data_sources(source_name, source_type)")
        .eq("id", event_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return resp.data


# ── Weather observations ────────────────────────────────────────────

@router.get("/weather")
async def list_weather_observations(
    location_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent weather observations."""
    query = supabase_admin.table("weather_observations").select("*")
    if location_id:
        query = query.eq("location_id", location_id)
    query = query.order("observed_at", desc=True).limit(limit)
    resp = query.execute()
    return {"observations": resp.data or [], "count": len(resp.data or [])}


@router.get("/weather/latest/{location_id}")
async def latest_weather(location_id: str):
    """Get the most recent weather observation for a location."""
    resp = (
        supabase_admin.table("weather_observations")
        .select("*")
        .eq("location_id", location_id)
        .order("observed_at", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="No weather data for this location")
    return resp.data[0]


# ── Satellite observations ──────────────────────────────────────────

@router.get("/satellites")
async def list_satellite_observations(
    disaster_id: Optional[str] = Query(None),
    confidence: Optional[str] = Query(None, description="low, nominal, high"),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent satellite / fire hotspot observations."""
    query = supabase_admin.table("satellite_observations").select("*")
    if disaster_id:
        query = query.eq("disaster_id", disaster_id)
    if confidence:
        query = query.eq("confidence", confidence)
    query = query.order("acq_datetime", desc=True).limit(limit)
    resp = query.execute()
    return {"observations": resp.data or [], "count": len(resp.data or [])}


# ── Alert notifications ────────────────────────────────────────────

@router.get("/alerts")
async def list_alert_notifications(
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="pending, sent, failed, acknowledged"),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent alert notifications."""
    query = supabase_admin.table("alert_notifications").select("*")
    if severity:
        query = query.eq("severity", severity)
    if status:
        query = query.eq("status", status)
    query = query.order("created_at", desc=True).limit(limit)
    resp = query.execute()
    return {"alerts": resp.data or [], "count": len(resp.data or [])}


# ── Data source management ──────────────────────────────────────────

@router.get("/sources")
async def list_data_sources():
    """List all registered external data sources."""
    resp = supabase_admin.table("external_data_sources").select("*").execute()
    return {"sources": resp.data or []}


@router.patch("/sources/{source_id}")
async def update_data_source(source_id: str, body: Dict[str, Any]):
    """Update a data source config (e.g. toggle is_active, change interval)."""
    allowed_fields = {"is_active", "poll_interval_s", "config_json"}
    update_data = {k: v for k, v in body.items() if k in allowed_fields}
    if not update_data:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    resp = (
        supabase_admin.table("external_data_sources")
        .update(update_data)
        .eq("id", source_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Data source not found")
    return resp.data[0]
