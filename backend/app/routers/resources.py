from fastapi import APIRouter, HTTPException, Depends
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
import logging
import uuid

from app.database import db
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
from app.dependencies import require_role

# GNN-based allocator imports
from ml.gat_model import (
    GATAllocator,
    load_checkpoint,
    hungarian_assignment,
    explain_assignment,
    DEFAULT_CHECKPOINT,
)
from ml.graph_builder import (
    VictimNode,
    NgoNode,
    build_graph,
    victim_node_from_dict,
    ngo_node_from_dict,
)

logger = logging.getLogger(__name__)

# ── Lazy-loaded GAT model singleton ──────────────────────────────────────

_gat_model: Optional[GATAllocator] = None


def _get_gat_model() -> Optional[GATAllocator]:
    """Load the trained GAT model once (returns None if checkpoint missing)."""
    global _gat_model
    if _gat_model is not None:
        return _gat_model
    if DEFAULT_CHECKPOINT.exists():
        try:
            _gat_model = load_checkpoint()
            logger.info("GAT allocator loaded from %s", DEFAULT_CHECKPOINT)
        except Exception as exc:
            logger.warning("Failed to load GAT checkpoint: %s", exc)
    else:
        logger.info("GAT checkpoint not found at %s — will fall back to LP solver", DEFAULT_CHECKPOINT)
    return _gat_model

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
        query = db.table("resources").select("*")
        
        if location_id:
            query = query.eq("location_id", location_id)
        if status:
            query = query.eq("status", status.value)
        if disaster_id:
            query = query.eq("disaster_id", disaster_id)
        
        query = query.order("priority", desc=True).limit(limit)
        response = await query.async_execute()
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=Resource, status_code=201)
async def create_resource(
    resource: ResourceCreate,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Create a new resource (admin/ngo only)"""
    try:
        resource_dict = resource.model_dump()
        resource_dict["id"] = str(uuid.uuid4())
        resource_dict["status"] = ResourceStatus.AVAILABLE.value
        resource_dict["created_at"] = datetime.now(timezone.utc).isoformat()
        resource_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        response = await db.table("resources").insert(resource_dict).async_execute()
        
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create resource")
        
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{resource_id}", response_model=Resource)
async def update_resource(
    resource_id: str,
    resource_update: ResourceUpdate,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Update an existing resource (admin/ngo only)"""
    try:
        update_dict = resource_update.model_dump(exclude_unset=True)
        update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        response = (
            await db.table("resources")
            .update(update_dict)
            .eq("id", resource_id)
            .async_execute()
        )
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Resource not found")
        
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/allocate", response_model=AllocationResponse)
async def allocate_resources(
    allocation_request: AllocationRequest,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """
    Allocate resources to a disaster using a Graph Attention Network (GAT).

    The GAT encodes a bipartite victim↔NGO graph, produces assignment
    probabilities via a bilinear head, then applies the Hungarian algorithm
    for optimal one-to-one matching.  Each allocation includes SHAP-style
    feature explanations (top 3 contributing features).

    Falls back to the PuLP LP solver when the GAT checkpoint is unavailable.
    """
    try:
        disaster_id = allocation_request.disaster_id
        required_resources = allocation_request.required_resources
        max_distance_km = allocation_request.max_distance_km

        # ── Map user-supplied priority_weights (kept for LP fallback) ──
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
            await db.table("resources")
            .select("*")
            .eq("status", ResourceStatus.AVAILABLE.value)
            .async_execute()
        )
        raw_resources = response.data or []

        # Resolve locations (lat/lng) for each resource
        location_cache: dict = {}
        location_ids = list({r["location_id"] for r in raw_resources})
        if location_ids:
            loc_resp = (
                await db.table("locations")
                .select("id, latitude, longitude")
                .in_("id", location_ids)
                .async_execute()
            )
            for loc in (loc_resp.data or []):
                location_cache[loc["id"]] = (loc["latitude"], loc["longitude"])

        # ── Resolve disaster zone coordinates ─────────────────────────
        disaster_resp = (
            await db.table("disasters")
            .select("location_id")
            .eq("id", disaster_id)
            .limit(1)
            .async_execute()
        )
        zone_lat, zone_lng = 0.0, 0.0
        if disaster_resp.data:
            d_loc_id = disaster_resp.data[0]["location_id"]
            if d_loc_id in location_cache:
                zone_lat, zone_lng = location_cache[d_loc_id]
            else:
                loc_resp2 = (
                    await db.table("locations")
                    .select("latitude, longitude")
                    .eq("id", d_loc_id)
                    .limit(1)
                    .async_execute()
                )
                if loc_resp2.data:
                    zone_lat = loc_resp2.data[0]["latitude"]
                    zone_lng = loc_resp2.data[0]["longitude"]

        # ── Try GNN-based allocation ──────────────────────────────────
        gat = _get_gat_model()
        if gat is not None:
            return await _allocate_with_gnn(
                gat=gat,
                disaster_id=disaster_id,
                raw_resources=raw_resources,
                required_resources=required_resources,
                location_cache=location_cache,
                zone_lat=zone_lat,
                zone_lng=zone_lng,
                max_distance_km=max_distance_km,
            )

        # ── Fallback: LP solver ───────────────────────────────────────
        logger.info("Using LP solver fallback for allocation")
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

        result = solve_allocation(
            resources=available,
            needs=needs,
            weights=weights,
            max_distance_km=max_distance_km,
        )

        if result.allocations:
            allocated_ids = [alloc["resource_id"] for alloc in result.allocations]
            now_iso = datetime.now(timezone.utc).isoformat()
            await db.table("resources").update(
                {
                    "status": ResourceStatus.ALLOCATED.value,
                    "disaster_id": disaster_id,
                    "allocated_to": disaster_id,
                    "updated_at": now_iso,
                }
            ).in_("id", allocated_ids).async_execute()

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


# ── GNN allocation helper ───────────────────────────────────────────────


async def _allocate_with_gnn(
    *,
    gat: GATAllocator,
    disaster_id: str,
    raw_resources: List[Dict[str, Any]],
    required_resources: List[Dict[str, Any]],
    location_cache: dict,
    zone_lat: float,
    zone_lng: float,
    max_distance_km: float,
) -> AllocationResponse:
    """
    Run the GAT model on a bipartite graph built from victim requests and
    NGO/resource data, apply Hungarian matching, and return the allocation.
    """
    import torch
    from app.services.distance import haversine

    now = datetime.now(timezone.utc)

    # ── Build victim nodes from required_resources ────────────────────
    victims: List[VictimNode] = []
    for i, req in enumerate(required_resources):
        victims.append(
            VictimNode(
                id=f"req_{i}",
                lat=zone_lat,
                lon=zone_lng,
                priority_score=float(req.get("priority", 5)),
                medical_needs_encoded=1.0 if req.get("type", "").lower() == "medical" else 0.0,
                hours_since_request=0.0,
                resource_type=req.get("type", "Other"),
            )
        )

    # ── Build NGO nodes from available resources ─────────────────────
    # Group resources by location to form NGO nodes
    ngo_map: Dict[str, Dict[str, Any]] = {}
    for r in raw_resources:
        loc_id = r["location_id"]
        if loc_id not in ngo_map:
            lat, lng = location_cache.get(loc_id, (0.0, 0.0))
            ngo_map[loc_id] = {
                "id": loc_id,
                "lat": lat,
                "lon": lng,
                "types": set(),
                "resource_ids": [],
                "total_quantity": 0.0,
            }
        ngo_map[loc_id]["types"].add(r.get("type", "Other"))
        ngo_map[loc_id]["resource_ids"].append(r["id"])
        ngo_map[loc_id]["total_quantity"] += r.get("quantity", 0)

    ngos: List[NgoNode] = []
    ngo_resource_map: List[Dict[str, Any]] = []  # parallel list for look-up
    for loc_id, info in ngo_map.items():
        n_resources = len(info["resource_ids"])
        ngos.append(
            NgoNode(
                id=info["id"],
                lat=info["lat"],
                lon=info["lon"],
                capacity_score=min(info["total_quantity"] / 100.0, 1.0),
                available_resource_types=list(info["types"]),
                avg_response_time_hours=2.0,
                current_load_ratio=0.0,
            )
        )
        ngo_resource_map.append(info)

    if not victims or not ngos:
        return AllocationResponse(
            disaster_id=disaster_id,
            allocations=[],
            optimization_score=0.0,
            unmet_needs=[{"type": r.get("type"), "quantity": r.get("quantity"), "urgency": r.get("priority", 5)} for r in required_resources],
            score_breakdown=OptimizationScoreBreakdown(
                coverage_pct=0.0,
                unmet_needs=[],
                estimated_delivery_km=0.0,
                solver_status="trivial_empty",
            ),
        )

    # ── Build graph & run GNN ────────────────────────────────────────
    graph = build_graph(victims, ngos, radius_km=max_distance_km)
    edge_probs = gat.predict_probs(graph)

    # ── Hungarian one-to-one matching ────────────────────────────────
    assignments = hungarian_assignment(graph, edge_probs)

    # ── Build allocation results with SHAP explanations ──────────────
    allocations: List[Dict[str, Any]] = []
    met_indices: set = set()
    total_dist = 0.0

    for victim_idx, ngo_idx, prob in assignments:
        if ngo_idx >= len(ngo_resource_map):
            continue

        ngo_info = ngo_resource_map[ngo_idx]
        req = required_resources[victim_idx] if victim_idx < len(required_resources) else {}
        req_type = req.get("type", "Other")

        # Pick the best matching resource from this NGO location
        best_rid = None
        for rid in ngo_info["resource_ids"]:
            r_row = next((r for r in raw_resources if r["id"] == rid), None)
            if r_row and r_row.get("type", "").lower() == req_type.lower():
                best_rid = rid
                break
        if best_rid is None and ngo_info["resource_ids"]:
            best_rid = ngo_info["resource_ids"][0]

        dist_km = haversine(zone_lat, zone_lng, ngo_info["lat"], ngo_info["lon"])
        total_dist += dist_km
        met_indices.add(victim_idx)

        # SHAP explanations (top 3)
        explanations = explain_assignment(gat, graph, victim_idx, ngo_idx, top_k=3)

        allocations.append({
            "resource_id": best_rid,
            "type": req_type,
            "quantity": req.get("quantity", 0),
            "location": ngo_info["id"],
            "distance_km": round(dist_km, 2),
            "assignment_probability": round(prob, 4),
            "explanations": explanations,
        })

    # ── Persist allocation decisions ──────────────────────────────────
    if allocations:
        allocated_ids = [a["resource_id"] for a in allocations if a["resource_id"]]
        if allocated_ids:
            now_iso = now.isoformat()
            await db.table("resources").update(
                {
                    "status": ResourceStatus.ALLOCATED.value,
                    "disaster_id": disaster_id,
                    "allocated_to": disaster_id,
                    "updated_at": now_iso,
                }
            ).in_("id", allocated_ids).async_execute()

    # ── Compute unmet needs ──────────────────────────────────────────
    unmet = []
    for i, req in enumerate(required_resources):
        if i not in met_indices:
            unmet.append({
                "type": req.get("type", "Other"),
                "quantity": req.get("quantity", 0),
                "urgency": req.get("priority", 5),
            })

    n_total = len(required_resources)
    coverage_pct = round(len(met_indices) / n_total * 100 if n_total else 0, 2)

    breakdown = OptimizationScoreBreakdown(
        coverage_pct=coverage_pct,
        unmet_needs=unmet,
        estimated_delivery_km=round(total_dist, 2),
        solver_status="gat_optimal",
    )

    return AllocationResponse(
        disaster_id=disaster_id,
        allocations=allocations,
        optimization_score=round(len(met_indices) / n_total if n_total else 0, 4),
        unmet_needs=unmet,
        score_breakdown=breakdown,
    )


@router.post("/{resource_id}/deallocate")
async def deallocate_resource(
    resource_id: str,
    _user: dict = Depends(require_role("admin", "ngo")),
):
    """Deallocate a resource and make it available again (admin/ngo only)"""
    try:
        response = (
            await db.table("resources")
            .update({
                'status': ResourceStatus.AVAILABLE.value,
                'disaster_id': None,
                'allocated_to': None,
                'updated_at': datetime.now(timezone.utc).isoformat()
            })
            .eq('id', resource_id)
            .async_execute()
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
        query = db.table("resource_consumption_log").select("*")
        if resource_type:
            query = query.eq("resource_type", resource_type)
        # Pull last 30 days of data
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        query = query.gte("timestamp", cutoff).order("timestamp", desc=False)
        resp = await query.async_execute()
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
