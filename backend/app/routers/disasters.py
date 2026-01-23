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

router = APIRouter()


@router.get("/", response_model=List[Disaster])
async def get_disasters(
    status: Optional[DisasterStatus] = None,
    severity: Optional[DisasterSeverity] = None,
    type: Optional[DisasterType] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Get all disasters with optional filtering"""
    try:
        query = supabase.table("disasters").select("*")

        if status:
            query = query.eq("status", status.value)
        if severity:
            query = query.eq("severity", severity.value)
        if type:
            query = query.eq("type", type.value)

        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

        response = query.execute()

        # Manually convert datetime objects to strings for JSON serialization
        disasters_data = []
        for disaster in response.data:
            if isinstance(disaster.get('created_at'), datetime):
                disaster['created_at'] = disaster['created_at'].isoformat()
            if isinstance(disaster.get('updated_at'), datetime):
                disaster['updated_at'] = disaster['updated_at'].isoformat()
            if isinstance(disaster.get('start_date'), datetime):
                disaster['start_date'] = disaster['start_date'].isoformat()
            if disaster.get('end_date') and isinstance(disaster['end_date'], datetime):
                disaster['end_date'] = disaster['end_date'].isoformat()
            disasters_data.append(disaster)

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

        # Manually convert datetime objects to strings for JSON serialization
        disaster_data = response.data
        if isinstance(disaster_data.get('created_at'), datetime):
            disaster_data['created_at'] = disaster_data['created_at'].isoformat()
        if isinstance(disaster_data.get('updated_at'), datetime):
            disaster_data['updated_at'] = disaster_data['updated_at'].isoformat()
        if isinstance(disaster_data.get('start_date'), datetime):
            disaster_data['start_date'] = disaster_data['start_date'].isoformat()
        if disaster_data.get('end_date') and isinstance(disaster_data['end_date'], datetime):
            disaster_data['end_date'] = disaster_data['end_date'].isoformat()

        return disaster_data

    except Exception as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Disaster not found")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_disaster(disaster_data: Dict[str, Any]):
    """Create a new disaster record"""
    try:
        # Manually create the disaster dict without Pydantic validation
        disaster_dict = dict(disaster_data)
        disaster_dict["status"] = "active"

        response = supabase.table("disasters").insert(disaster_dict).execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create disaster")

        # Return just the ID to avoid datetime serialization issues
        disaster_id = response.data[0]["id"]
        return {
            "id": disaster_id,
            "message": "Disaster created successfully",
            "status": "created"
        }

    except Exception as e:
        print(f"DEBUG: Disaster creation failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "error": "Failed to create disaster",
            "message": str(e)
        }


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

        # Manually convert datetime objects to strings for JSON serialization
        disaster_data = response.data[0]
        if isinstance(disaster_data.get('created_at'), datetime):
            disaster_data['created_at'] = disaster_data['created_at'].isoformat()
        if isinstance(disaster_data.get('updated_at'), datetime):
            disaster_data['updated_at'] = disaster_data['updated_at'].isoformat()
        if isinstance(disaster_data.get('start_date'), datetime):
            disaster_data['start_date'] = disaster_data['start_date'].isoformat()
        if disaster_data.get('end_date') and isinstance(disaster_data['end_date'], datetime):
            disaster_data['end_date'] = disaster_data['end_date'].isoformat()

        return disaster_data

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
