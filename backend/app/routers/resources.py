from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime, timedelta
import uuid

from app.database import supabase
from app.schemas import (
    Resource,
    ResourceCreate,
    ResourceUpdate,
    AllocationRequest,
    AllocationResponse,
    OptimizationScoreBreakdown,
    ForecastResponse,
    ForecastItemSchema,
    ResourceStatus
)
from app.services.allocation_engine import (
    AvailableResource,
    ResourceNeed,
    PriorityWeights,
    solve_allocation,
)
from app.services.forecast_service import (
    ConsumptionRecord,
    generate_forecast,
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
    Allocate resources to a disaster using a constraint-based LP optimiser.

    The engine uses PuLP to solve a Mixed-Integer Linear Program that
    maximises coverage weighted by urgency while minimising delivery
    distance, with bonuses for soon-to-expire perishables.
    """
    try:
        disaster_id = allocation_request.disaster_id
        required_resources = allocation_request.required_resources
        max_distance_km = allocation_request.max_distance_km

        # ── Map user-supplied priority_weights to engine dataclass ────
        pw = allocation_request.priority_weights
        weights = (
            PriorityWeights(
                urgency_weight=pw.urgency_weight,
                distance_weight=pw.distance_weight,
                expiry_weight=pw.expiry_weight,
                coverage_weight=pw.coverage_weight,
            )
            if pw
            else PriorityWeights()
        )

        # ── Fetch available resources from the database ───────────────
        response = (
            supabase.table("resources")
            .select("*")
            .eq("status", ResourceStatus.AVAILABLE.value)
            .execute()
        )
        raw_resources = response.data or []

        # Resolve locations (lat/lng) for each resource
        location_cache: dict = {}
        location_ids = list({r["location_id"] for r in raw_resources})
        if location_ids:
            loc_resp = (
                supabase.table("locations")
                .select("id, latitude, longitude")
                .in_("id", location_ids)
                .execute()
            )
            for loc in (loc_resp.data or []):
                location_cache[loc["id"]] = (loc["latitude"], loc["longitude"])

        available: List[AvailableResource] = []
        for r in raw_resources:
            lat, lng = location_cache.get(r["location_id"], (0.0, 0.0))
            expiry = None
            if r.get("expiry_date"):
                try:
                    expiry = datetime.fromisoformat(r["expiry_date"])
                except (ValueError, TypeError):
                    pass
            available.append(
                AvailableResource(
                    id=r["id"],
                    resource_type=r["type"],
                    quantity=r["quantity"],
                    priority=r.get("priority", 5),
                    location_lat=lat,
                    location_lng=lng,
                    location_id=r["location_id"],
                    expiry_date=expiry,
                )
            )

        # ── Resolve disaster zone coordinates ─────────────────────────
        disaster_resp = (
            supabase.table("disasters")
            .select("location_id")
            .eq("id", disaster_id)
            .limit(1)
            .execute()
        )
        zone_lat, zone_lng = 0.0, 0.0
        if disaster_resp.data:
            d_loc_id = disaster_resp.data[0]["location_id"]
            if d_loc_id in location_cache:
                zone_lat, zone_lng = location_cache[d_loc_id]
            else:
                loc_resp2 = (
                    supabase.table("locations")
                    .select("latitude, longitude")
                    .eq("id", d_loc_id)
                    .limit(1)
                    .execute()
                )
                if loc_resp2.data:
                    zone_lat = loc_resp2.data[0]["latitude"]
                    zone_lng = loc_resp2.data[0]["longitude"]

        # ── Build needs list ──────────────────────────────────────────
        needs: List[ResourceNeed] = []
        for req in required_resources:
            needs.append(
                ResourceNeed(
                    need_type=req["type"],
                    quantity=req["quantity"],
                    urgency=req.get("priority", 5),
                    zone_lat=zone_lat,
                    zone_lng=zone_lng,
                )
            )

        # ── Run LP solver ─────────────────────────────────────────────
        result = solve_allocation(
            resources=available,
            needs=needs,
            weights=weights,
            max_distance_km=max_distance_km,
        )

        # ── Persist allocation decisions (batched) ────────────────────────
        if result.allocations:
            allocated_ids = [alloc["resource_id"] for alloc in result.allocations]
            now_iso = datetime.utcnow().isoformat()
            supabase.table("resources").update(
                {
                    "status": ResourceStatus.ALLOCATED.value,
                    "disaster_id": disaster_id,
                    "allocated_to": disaster_id,
                    "updated_at": now_iso,
                }
            ).in_("id", allocated_ids).execute()

        breakdown = OptimizationScoreBreakdown(
            coverage_pct=result.coverage_pct,
            unmet_needs=result.unmet_needs,
            estimated_delivery_km=result.estimated_delivery_km,
            solver_status=result.solver_status,
        )

        return AllocationResponse(
            disaster_id=disaster_id,
            allocations=result.allocations,
            optimization_score=result.optimization_score,
            unmet_needs=result.unmet_needs,
            score_breakdown=breakdown,
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


@router.get("/forecast", response_model=ForecastResponse)
async def get_resource_forecast(
    resource_type: str = None,
    horizon_hours: int = 72,
):
    """
    Return predicted shortfall by resource type for the next *horizon_hours*.

    Uses historical resource consumption data to forecast demand vs supply.
    If no consumption history exists the response will contain empty items.
    """
    try:
        # Fetch consumption / allocation history
        query = supabase.table("resource_consumption_log").select("*")
        if resource_type:
            query = query.eq("resource_type", resource_type)
        # Pull last 30 days of data
        cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
        query = query.gte("timestamp", cutoff).order("timestamp", desc=False)
        resp = query.execute()
        rows = resp.data or []

        records = [
            ConsumptionRecord(
                resource_type=r["resource_type"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                quantity_consumed=r.get("quantity_consumed", 0),
                quantity_available=r.get("quantity_available", 0),
            )
            for r in rows
        ]

        forecast = generate_forecast(records, horizon_hours=horizon_hours)

        return ForecastResponse(
            generated_at=forecast.generated_at,
            horizon_hours=forecast.horizon_hours,
            method=forecast.method,
            items=[
                ForecastItemSchema(
                    resource_type=it.resource_type,
                    forecast_hour=it.forecast_hour,
                    predicted_demand=it.predicted_demand,
                    predicted_supply=it.predicted_supply,
                    shortfall=it.shortfall,
                    confidence_lower=it.confidence_lower,
                    confidence_upper=it.confidence_upper,
                )
                for it in forecast.items
            ],
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Forecast generation failed: {str(e)}",
        )
