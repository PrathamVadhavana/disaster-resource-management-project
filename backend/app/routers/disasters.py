from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.database import db
from app.schemas import (
    Disaster,
    DisasterCreate,
    DisasterUpdate,
    DisasterStatus,
    DisasterSeverity,
    DisasterType
)
from app.core.helpers import serialize_disaster, serialize_datetime_fields
from app.core.cache import cache_get, cache_set, cache_invalidate_pattern, CACHE_TTL_SHORT
from app.dependencies import require_role
from app.services.notification_service import notify_all_by_role

logger = logging.getLogger("disasters_router")

router = APIRouter()


@router.get("/")
async def get_disasters(
    status: Optional[DisasterStatus] = None,
    severity: Optional[DisasterSeverity] = None,
    type: Optional[DisasterType] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get all disasters with optional filtering"""
    try:
        # Build a deterministic cache key from the query params
        cache_key = f"disasters:list:{status}:{severity}:{type}:{limit}:{offset}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # Fetch disasters without joins to avoid "schema cache" errors
        query = db.table("disasters").select("*")

        if status:
            query = query.eq("status", status.value)
        if severity:
            query = query.eq("severity", severity.value)
        if type:
            query = query.eq("type", type.value)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        response = await query.async_execute()
        base_disasters = response.data or []

        # Manual enrichment for locations
        location_ids = list(set(d["location_id"] for d in base_disasters if d.get("location_id")))
        location_map = {}
        if location_ids:
            loc_resp = await db.table("locations").select("id, latitude, longitude, name, city, country").in_("id", location_ids).async_execute()
            for loc in (loc_resp.data or []):
                location_map[loc["id"]] = loc

        disasters_data = []
        for d in base_disasters:
            d["locations"] = location_map.get(d.get("location_id"))
            disasters_data.append(serialize_disaster(d))

        await cache_set(cache_key, disasters_data, CACHE_TTL_SHORT)
        return disasters_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{disaster_id}", response_model=Disaster)
async def get_disaster(disaster_id: str):
    """Get a specific disaster by ID"""
    try:
        response = await db.table("disasters").select("*").eq("id", disaster_id).single().async_execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Disaster not found")

        return serialize_datetime_fields(response.data)

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Disaster not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_disaster(
    disaster_data: Dict[str, Any],
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Create a new disaster record (admin/ngo only)"""
    try:
        disaster_dict = dict(disaster_data)
        disaster_dict["status"] = "active"

        response = await db.table("disasters").insert(disaster_dict).async_execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create disaster")

        await cache_invalidate_pattern("disasters:*")

        disaster_id = response.data[0]["id"]

        # Notify NGOs and Volunteers about the new disaster
        title = disaster_dict.get("title", "New Disaster")
        severity = disaster_dict.get("severity", "unknown")
        d_type = disaster_dict.get("type", "disaster")
        try:
            await notify_all_by_role(
                role="ngo",
                title="🚨 New Disaster Reported",
                message=f"{title} ({d_type}, severity: {severity}) has been created. Check your dashboard for requests.",
                notification_type="warning",
                related_id=disaster_id,
                related_type="disaster",
            )
            await notify_all_by_role(
                role="volunteer",
                title="🚨 New Disaster — Volunteers Needed",
                message=f"{title} ({d_type}, severity: {severity}). Check available assignments if you can help.",
                notification_type="warning",
                related_id=disaster_id,
                related_type="disaster",
            )
        except Exception:
            pass

        return {
            "id": disaster_id,
            "message": "Disaster created successfully",
            "status": "created"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create disaster: {e}")


@router.patch("/{disaster_id}", response_model=Disaster)
async def update_disaster(
    disaster_id: str,
    disaster_update: DisasterUpdate,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Update an existing disaster (admin/ngo only)"""
    try:
        update_dict = disaster_update.model_dump(exclude_unset=True)

        response = (
            await db.table("disasters")
            .update(update_dict)
            .eq("id", disaster_id)
            .async_execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Disaster not found")

        await cache_invalidate_pattern("disasters:*")

        # Auto-generate Causal Audit Report when status → resolved
        updated = response.data[0]
        if update_dict.get("status") == "resolved" or update_dict.get("status") == DisasterStatus.RESOLVED.value:
            try:
                from app.services.audit_report_generator import on_disaster_resolved
                import asyncio
                asyncio.create_task(on_disaster_resolved(updated))
                logger.info("Causal audit report generation triggered for %s", disaster_id)
            except Exception as audit_err:
                logger.warning("Causal audit trigger failed: %s", audit_err)

        return serialize_datetime_fields(updated)

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Disaster not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{disaster_id}", status_code=204)
async def delete_disaster(
    disaster_id: str,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Delete a disaster — soft delete by setting status to resolved (admin/ngo only)"""
    try:
        response = (
            await db.table("disasters")
            .update({
                "status": DisasterStatus.RESOLVED.value,
                "updated_at": datetime.utcnow().isoformat()
            })
            .eq("id", disaster_id)
            .async_execute()
        )
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Disaster not found")
        
        return None
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{disaster_id}/resources")
async def get_disaster_resources(disaster_id: str):
    """Get all resources allocated to a specific disaster"""
    try:
        response = (
            await db.table("resources")
            .select("*")
            .eq("disaster_id", disaster_id)
            .async_execute()
        )
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
