import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.core.cache import CACHE_TTL_SHORT, cache_get, cache_invalidate_pattern, cache_set
from app.core.helpers import serialize_datetime_fields, serialize_disaster
from app.database import db
from app.dependencies import require_role
from app.schemas import Disaster, DisasterSeverity, DisasterStatus, DisasterType, DisasterUpdate
from app.services.notification_service import notify_all_by_role

logger = logging.getLogger("disasters_router")

router = APIRouter()


@router.get("/")
async def get_disasters(
    status: str | None = Query(None, description="Filter by status (comma-separated for multiples)"),
    severity: str | None = Query(None, description="Filter by severity (comma-separated for multiples)"),
    type: str | None = Query(None, description="Filter by type (comma-separated for multiples)"),
    source: str | None = Query(None, description="Filter by source (automated, victim)"),
    search: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get all disasters with optional filtering"""
    try:
        # Build a deterministic cache key from the query params
        cache_key = f"disasters:list:{status}:{severity}:{type}:{source}:{limit}:{offset}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # Fetch disasters without joins to avoid "schema cache" errors
        query = db.table("disasters").select("*")

        if status:
            status_list = [s.strip() for s in status.split(",") if s.strip()]
            if len(status_list) == 1:
                query = query.eq("status", status_list[0])
            else:
                query = query.in_("status", status_list)
        
        if severity:
            severity_list = [s.strip() for s in severity.split(",") if s.strip()]
            if len(severity_list) == 1:
                query = query.eq("severity", severity_list[0])
            else:
                query = query.in_("severity", severity_list)

        if type:
            type_list = [t.strip() for t in type.split(",") if t.strip()]
            if len(type_list) == 1:
                query = query.eq("type", type_list[0])
            else:
                query = query.in_("type", type_list)

        if source:
            # Filter by source in metadata JSONB
            query = query.eq("metadata->>source", source)
        if search:
            # Search across title, location_name, and type fields
            search_lower = search.lower()
            query = query.or_(
                f"title.ilike.%{search_lower}%,location_name.ilike.%{search_lower}%,type.ilike.%{search_lower}%"
            )

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        response = await query.async_execute()
        base_disasters = response.data or []

        # Manual enrichment for locations
        location_ids = list(set(d["location_id"] for d in base_disasters if d.get("location_id")))
        location_map = {}
        if location_ids:
            loc_resp = (
                await db.table("locations")
                .select("id, latitude, longitude, name, city, country")
                .in_("id", location_ids)
                .async_execute()
            )
            for loc in loc_resp.data or []:
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
    disaster_data: dict[str, Any],
    user: dict = Depends(require_role("admin", "ngo", "victim")),
):
    """Create a new disaster record (admin/ngo/victim)"""
    try:
        disaster_dict = dict(disaster_data)
        disaster_dict["status"] = "active"

        # Set source and reported_by in metadata
        meta = disaster_dict.get("metadata") or {}
        if not meta.get("source"):
            meta["source"] = user.get("role", "admin")
        if not meta.get("reported_by"):
            meta["reported_by"] = user.get("id")
        disaster_dict["metadata"] = meta

        # Filter out location_name if it exists but the column doesn't exist in DB yet
        # This handles the case where frontend sends location_name but DB schema hasn't been updated
        if "location_name" in disaster_dict:
            # Try to insert with location_name first
            try:
                response = await db.table("disasters").insert(disaster_dict).async_execute()
            except Exception as e:
                if "location_name" in str(e) and "schema cache" in str(e):
                    # Column doesn't exist, remove it and try again
                    disaster_dict_filtered = {k: v for k, v in disaster_dict.items() if k != "location_name"}
                    response = await db.table("disasters").insert(disaster_dict_filtered).async_execute()
                else:
                    raise e
        else:
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

        return {"id": disaster_id, "message": "Disaster created successfully", "status": "created"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create disaster: {e}")


@router.patch("/{disaster_id}", response_model=Disaster)
async def update_disaster(
    disaster_id: str,
    disaster_update: DisasterUpdate,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Update an existing disaster (admin/ngo only)"""
    try:
        update_dict = disaster_update.model_dump(exclude_unset=True)

        response = await db.table("disasters").update(update_dict).eq("id", disaster_id).async_execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Disaster not found")

        await cache_invalidate_pattern("disasters:*")

        updated = response.data[0]
        if update_dict.get("status") in ["resolved", DisasterStatus.RESOLVED.value]:
            logger.info("Triggering causal audit report generation for disaster %s", disaster_id)
            from app.services.audit_report_generator import on_disaster_resolved

            background_tasks.add_task(on_disaster_resolved, updated)

        return serialize_datetime_fields(updated)

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Disaster not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{disaster_id}", status_code=204)
async def delete_disaster(
    disaster_id: str,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Delete a disaster — soft delete by setting status to resolved (admin/ngo only)"""
    try:
        response = (
            await db.table("disasters")
            .update({"status": DisasterStatus.RESOLVED.value, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", disaster_id)
            .async_execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Disaster not found")

        # Trigger causal audit report
        from app.services.audit_report_generator import on_disaster_resolved

        background_tasks.add_task(on_disaster_resolved, response.data[0])

        return None

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{disaster_id}/resources")
async def get_disaster_resources(disaster_id: str):
    """Get all resources allocated to a specific disaster"""
    try:
        response = await db.table("resources").select("*").eq("disaster_id", disaster_id).async_execute()

        return response.data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dropdown/options")
async def get_disaster_dropdown_options():
    """Get disasters for dropdown selection - includes active and recent resolved disasters"""
    try:
        # Get active disasters and recently resolved ones (last 30 days)
        from datetime import datetime, timedelta

        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()

        response = (
            await db.table("disasters")
            .select("id, title, type, severity, status, created_at")
            .or_(f"status.eq.active,created_at.gte.{thirty_days_ago}")
            .order("created_at", desc=True)
            .limit(50)
            .async_execute()
        )

        disasters = response.data or []

        # Format for dropdown
        options = []
        for d in disasters:
            status_badge = "🔴 Active" if d.get("status") == "active" else "✅ Resolved"
            options.append(
                {
                    "id": d["id"],
                    "label": f"{d['title']} ({d['type'].title()}) - {status_badge}",
                    "value": d["id"],
                    "type": d["type"],
                    "status": d["status"],
                    "severity": d["severity"],
                    "created_at": d["created_at"],
                }
            )

        return options

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
