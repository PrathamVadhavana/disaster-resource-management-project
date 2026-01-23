from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime
import uuid

from app.database import supabase
from app.schemas import (
    Resource,
    ResourceCreate,
    ResourceUpdate,
    AllocationRequest,
    AllocationResponse,
    ResourceStatus
)

router = APIRouter()


@router.get("/", response_model=List[Resource])
async def get_resources(
    location_id: str = None,
    status: ResourceStatus = None,
    disaster_id: str = None,
    limit: int = 100,
):
    """Get all resources with optional filtering"""
    try:
        query = supabase.table("resources").select("*")
        
        if location_id:
            query = query.eq("location_id", location_id)
        if status:
            query = query.eq("status", status.value)
        if disaster_id:
            query = query.eq("disaster_id", disaster_id)
        
        query = query.order("priority", desc=True).limit(limit)
        response = query.execute()
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Resource, status_code=201)
async def create_resource(resource: ResourceCreate):
    """Create a new resource"""
    try:
        resource_dict = resource.model_dump()
        resource_dict["id"] = str(uuid.uuid4())
        resource_dict["status"] = ResourceStatus.AVAILABLE.value
        resource_dict["created_at"] = datetime.utcnow().isoformat()
        resource_dict["updated_at"] = datetime.utcnow().isoformat()
        
        response = supabase.table("resources").insert(resource_dict).execute()
        
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create resource")
        
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{resource_id}", response_model=Resource)
async def update_resource(resource_id: str, resource_update: ResourceUpdate):
    """Update an existing resource"""
    try:
        update_dict = resource_update.model_dump(exclude_unset=True)
        update_dict["updated_at"] = datetime.utcnow().isoformat()
        
        response = (
            supabase.table("resources")
            .update(update_dict)
            .eq("id", resource_id)
            .execute()
        )
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/allocate", response_model=AllocationResponse)
async def allocate_resources(allocation_request: AllocationRequest):
    """
    Allocate resources to a disaster using optimization algorithm
    This is a simplified version - in production, use more sophisticated algorithms
    """
    try:
        disaster_id = allocation_request.disaster_id
        required_resources = allocation_request.required_resources
        
        # Get available resources
        response = (
            supabase.table("resources")
            .select("*")
            .eq("status", ResourceStatus.AVAILABLE.value)
            .execute()
        )
        
        available_resources = response.data
        allocations = []
        unmet_needs = []
        
        # Simple greedy allocation algorithm
        for requirement in required_resources:
            req_type = requirement['type']
            req_quantity = requirement['quantity']
            req_priority = requirement.get('priority', 5)
            
            # Find matching resources sorted by priority
            matching = [
                r for r in available_resources
                if r['type'] == req_type and r['quantity'] >= req_quantity
            ]
            matching.sort(key=lambda x: x['priority'], reverse=True)
            
            if matching:
                # Allocate the highest priority resource
                resource = matching[0]
                allocations.append({
                    'resource_id': resource['id'],
                    'type': req_type,
                    'quantity': req_quantity,
                    'location': resource['location_id']
                })
                
                # Update resource status
                supabase.table("resources").update({
                    'status': ResourceStatus.ALLOCATED.value,
                    'disaster_id': disaster_id,
                    'allocated_to': disaster_id,
                    'updated_at': datetime.utcnow().isoformat()
                }).eq('id', resource['id']).execute()
                
                available_resources.remove(resource)
            else:
                unmet_needs.append({
                    'type': req_type,
                    'quantity': req_quantity,
                    'priority': req_priority
                })
        
        # Calculate optimization score (% of requirements met)
        total_requirements = len(required_resources)
        met_requirements = len(allocations)
        optimization_score = met_requirements / total_requirements if total_requirements > 0 else 0
        
        return AllocationResponse(
            disaster_id=disaster_id,
            allocations=allocations,
            optimization_score=optimization_score,
            unmet_needs=unmet_needs
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Allocation failed: {str(e)}")


@router.post("/{resource_id}/deallocate")
async def deallocate_resource(resource_id: str):
    """Deallocate a resource and make it available again"""
    try:
        response = (
            supabase.table("resources")
            .update({
                'status': ResourceStatus.AVAILABLE.value,
                'disaster_id': None,
                'allocated_to': None,
                'updated_at': datetime.utcnow().isoformat()
            })
            .eq('id', resource_id)
            .execute()
        )
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        return {"message": "Resource deallocated successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
