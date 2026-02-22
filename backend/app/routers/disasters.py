from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.database import supabase
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

        query = supabase.table("disasters").select("*, locations(latitude, longitude, name, city, country)")

        if status:
            query = query.eq("status", status.value)
        if severity:
            query = query.eq("severity", severity.value)
        if type:
            query = query.eq("type", type.value)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        response = query.execute()

        disasters_data = [serialize_disaster(d) for d in response.data]

        await cache_set(cache_key, disasters_data, CACHE_TTL_SHORT)
        return disasters_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{disaster_id}", response_model=Disaster)
async def get_disaster(disaster_id: str):
    """Get a specific disaster by ID"""
    try:
        response = supabase.table("disasters").select("*").eq("id", disaster_id).single().execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Disaster not found")

        return serialize_datetime_fields(response.data)

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Disaster not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_disaster(disaster_data: Dict[str, Any]):
    """Create a new disaster record"""
    try:
        disaster_dict = dict(disaster_data)
        disaster_dict["status"] = "active"

        response = supabase.table("disasters").insert(disaster_dict).execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create disaster")

        await cache_invalidate_pattern("disasters:*")

        disaster_id = response.data[0]["id"]
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
async def update_disaster(disaster_id: str, disaster_update: DisasterUpdate):
    """Update an existing disaster"""
    try:
        update_dict = disaster_update.model_dump(exclude_unset=True)

        response = (
            supabase.table("disasters")
            .update(update_dict)
            .eq("id", disaster_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=404, detail="Disaster not found")

        await cache_invalidate_pattern("disasters:*")
        return serialize_datetime_fields(response.data[0])

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Disaster not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{disaster_id}", status_code=204)
async def delete_disaster(disaster_id: str):
    """Delete a disaster (soft delete by setting status to resolved)"""
    try:
        response = (
            supabase.table("disasters")
            .update({
                "status": DisasterStatus.RESOLVED.value,
                "updated_at": datetime.utcnow().isoformat()
            })
            .eq("id", disaster_id)
            .execute()
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
            supabase.table("resources")
            .select("*")
            .eq("disaster_id", disaster_id)
            .execute()
        )
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
