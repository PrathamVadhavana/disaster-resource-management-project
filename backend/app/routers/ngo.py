"""
NGO Dashboard Router — Full Production Implementation.

Endpoints for NGOs to:
- View approved requests & submit availability
- Track assigned requests & deliveries
- Manage inventory (available_resources)
- View enhanced dashboard stats with GPS distance
- Audit trail via operational_pulse
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import math

from app.database import supabase, supabase_admin
from app.dependencies import require_ngo, require_verified_ngo
from app.services.notification_service import notify_request_status_change

router = APIRouter()
security = HTTPBearer()

# ── GPS Utility ───────────────────────────────────────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS points in km."""
    R = 6371.0
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Status Flow ───────────────────────────────────────────────────────────────

STATUS_ORDER = [
    "pending",
    "approved",
    "availability_submitted",
    "under_review",
    "assigned",
    "in_progress",
    "delivered",
    "completed",
    "closed",
]

VALID_TRANSITIONS = {}
for i, s in enumerate(STATUS_ORDER):
    if i + 1 < len(STATUS_ORDER):
        VALID_TRANSITIONS[s] = STATUS_ORDER[i + 1]


# ── Schemas ───────────────────────────────────────────────────────────────────


class ClaimRequestBody(BaseModel):
    estimated_delivery: Optional[str] = Field(
        None, description="ISO date for estimated delivery"
    )
    notes: Optional[str] = Field(
        None, description="Internal notes regarding fulfillment"
    )


class UpdateFulfillmentBody(BaseModel):
    status: str = Field(..., description="'in_progress' or 'completed'")
    proof_url: Optional[str] = Field(
        None, description="URL to delivery proof (image/document)"
    )
    notes: Optional[str] = Field(None, description="Update notes")


class AvailabilitySubmission(BaseModel):
    available_quantity: int = Field(..., ge=1)
    estimated_delivery_time: str = Field(..., description="ISO datetime for ETA")
    assigned_team: Optional[str] = None
    vehicle_type: Optional[str] = None
    ngo_latitude: Optional[float] = None
    ngo_longitude: Optional[float] = None
    notes: Optional[str] = None


class DeliveryStatusUpdate(BaseModel):
    new_status: str = Field(..., description="Next status in strict flow")
    proof_url: Optional[str] = None
    notes: Optional[str] = None
    delivery_latitude: Optional[float] = None
    delivery_longitude: Optional[float] = None


class InventoryItem(BaseModel):
    category: str = Field(..., description="Food, Water, Medical, Shelter, Clothing")
    resource_type: str
    title: str
    description: Optional[str] = None
    total_quantity: int = Field(..., ge=1)
    unit: str = "units"
    address_text: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _log_pulse(
    actor_id: str,
    target_id: str,
    action_type: str,
    description: str,
    metadata: dict = None,
):
    """Write to operational_pulse for audit trail."""
    try:
        supabase_admin.table("operational_pulse").insert(
            {
                "actor_id": actor_id,
                "target_id": target_id,
                "action_type": action_type,
                "description": description,
                "metadata": metadata or {},
            }
        ).execute()
    except Exception as e:
        print(f"Pulse log error: {e}")


def _send_notification(
    user_id: str, title: str, message: str, priority: str = "medium", data: dict = None
):
    """Insert into the notifications table."""
    try:
        supabase_admin.table("notifications").insert(
            {
                "user_id": user_id,
                "title": title,
                "message": message,
                "priority": priority,
                "data": data or {},
            }
        ).execute()
    except Exception as e:
        print(f"Notification insert error: {e}")


def _enrich_with_victim(requests_list: list) -> list:
    """Add victim name / phone / email to a list of request dicts."""
    victim_ids = [r["victim_id"] for r in requests_list if r.get("victim_id")]
    user_map = {}
    if victim_ids:
        users_resp = (
            supabase_admin.table("users")
            .select("id, full_name, email, phone")
            .in_("id", victim_ids)
            .execute()
        )
        for u in users_resp.data or []:
            user_map[u["id"]] = u
    for r in requests_list:
        v = user_map.get(r.get("victim_id"), {})
        r["victim_name"] = v.get("full_name") or "Unknown"
        r["victim_phone"] = v.get("phone") or ""
        r["victim_email"] = v.get("email") or ""
    return requests_list


# ── Endpoints ─────────────────────────────────────────────────────────────────

# ================ AVAILABLE REQUESTS ================


@router.get("/requests/available")
async def list_available_requests(
    ngo=Depends(require_ngo),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    priority: Optional[str] = Query(
        None, description="Filter by priority: critical,high,medium,low"
    ),
    ngo_latitude: Optional[float] = Query(
        None, description="NGO GPS latitude for distance"
    ),
    ngo_longitude: Optional[float] = Query(
        None, description="NGO GPS longitude for distance"
    ),
    sort: Optional[str] = Query(
        "priority", description="Sort: priority, distance, created_at"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all approved requests that have not been assigned yet.
    Supports live GPS params for distance compute and distance-based sorting."""

    ngo_id = str(ngo.get("id"))

    # Resolve NGO GPS: prefer query params, fall back to stored metadata
    n_lat = ngo_latitude
    n_lon = ngo_longitude
    ngo_user = (
        supabase_admin.table("users")
        .select("metadata")
        .eq("id", ngo_id)
        .maybe_single()
        .execute()
    )
    if n_lat is None or n_lon is None:
        if ngo_user.data and ngo_user.data.get("metadata"):
            n_lat = n_lat or ngo_user.data["metadata"].get("latitude")
            n_lon = n_lon or ngo_user.data["metadata"].get("longitude")

    # Store live GPS in metadata if provided
    if ngo_latitude and ngo_longitude:
        try:
            meta = (ngo_user.data or {}).get("metadata") or {}
            meta["latitude"] = ngo_latitude
            meta["longitude"] = ngo_longitude
            supabase_admin.table("users").update({"metadata": meta}).eq(
                "id", ngo_id
            ).execute()
        except Exception:
            pass

    # For distance sorting, we need ALL matching records first, then sort, then paginate
    # For priority sorting, DB handles it directly
    needs_client_sort = sort == "distance" and n_lat and n_lon

    if needs_client_sort:
        # Fetch all matching records (no pagination yet)
        query = (
            supabase_admin.table("resource_requests")
            .select("*", count="exact")
            .eq("status", "approved")
            .is_("assigned_to", "null")
        )
    else:
        query = (
            supabase_admin.table("resource_requests")
            .select("*", count="exact")
            .eq("status", "approved")
            .is_("assigned_to", "null")
            .order("priority", desc=True)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )

    if resource_type:
        query = query.eq("resource_type", resource_type)
    if priority:
        query = query.eq("priority", priority)

    resp = query.execute()
    base_requests = resp.data or []
    total_count = resp.count or 0

    requests = _enrich_with_victim(base_requests)

    # Compute distance for all records
    for r in requests:
        r["distance_km"] = None
        if n_lat and n_lon and r.get("latitude") and r.get("longitude"):
            r["distance_km"] = round(
                haversine_km(n_lat, n_lon, r["latitude"], r["longitude"]), 2
            )

    # Batch check availability submissions (avoid N+1 queries)
    req_ids = [r["id"] for r in requests]
    submitted_set = set()
    if req_ids:
        try:
            pulse_resp = (
                supabase_admin.table("operational_pulse")
                .select("target_id")
                .eq("actor_id", ngo_id)
                .eq("action_type", "ngo_availability_submitted")
                .in_("target_id", req_ids)
                .execute()
            )
            submitted_set = {p["target_id"] for p in (pulse_resp.data or [])}
        except Exception:
            pass

    for r in requests:
        r["availability_submitted"] = r["id"] in submitted_set

    # Sort and paginate for distance mode
    if needs_client_sort:
        requests.sort(
            key=lambda r: (
                r["distance_km"] if r["distance_km"] is not None else float("inf")
            )
        )
        # Apply pagination after sorting
        requests = requests[offset : offset + limit]

    return {"requests": requests, "total": total_count}


# ================ SUBMIT AVAILABILITY ================


@router.post("/requests/{request_id}/availability")
async def submit_availability(
    request_id: str,
    body: AvailabilitySubmission,
    ngo=Depends(require_verified_ngo),
):
    """Submit resource availability for an approved request."""
    ngo_id = str(ngo.get("id"))

    # Verify request exists and is approved
    existing = (
        supabase_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")

    req_status = existing.data.get("status")
    if req_status not in ("approved", "availability_submitted"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit availability for request in '{req_status}' status. Must be 'approved'.",
        )

    if existing.data.get("assigned_to"):
        raise HTTPException(status_code=400, detail="Request is already assigned")

    # Prevent duplicate submission
    dup = (
        supabase_admin.table("operational_pulse")
        .select("id")
        .eq("actor_id", ngo_id)
        .eq("target_id", request_id)
        .eq("action_type", "ngo_availability_submitted")
        .execute()
    )
    if dup.data and len(dup.data) > 0:
        raise HTTPException(
            status_code=400,
            detail="You have already submitted availability for this request",
        )

    # Compute distance
    distance_km = None
    if (
        body.ngo_latitude
        and body.ngo_longitude
        and existing.data.get("latitude")
        and existing.data.get("longitude")
    ):
        distance_km = round(
            haversine_km(
                body.ngo_latitude,
                body.ngo_longitude,
                existing.data["latitude"],
                existing.data["longitude"],
            ),
            2,
        )

    # Log availability in operational_pulse
    _log_pulse(
        actor_id=ngo_id,
        target_id=request_id,
        action_type="ngo_availability_submitted",
        description=f"NGO submitted availability: {body.available_quantity} units, ETA {body.estimated_delivery_time}",
        metadata={
            "available_quantity": body.available_quantity,
            "estimated_delivery_time": body.estimated_delivery_time,
            "assigned_team": body.assigned_team,
            "vehicle_type": body.vehicle_type,
            "ngo_latitude": body.ngo_latitude,
            "ngo_longitude": body.ngo_longitude,
            "distance_km": distance_km,
            "notes": body.notes,
            "provider_role": "ngo",
        },
    )

    # Update request status to availability_submitted (if still approved)
    if req_status == "approved":
        supabase_admin.table("resource_requests").update(
            {
                "status": "availability_submitted",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", request_id).execute()

    # Update NGO user metadata with GPS
    if body.ngo_latitude and body.ngo_longitude:
        try:
            current = (
                supabase_admin.table("users")
                .select("metadata")
                .eq("id", ngo_id)
                .maybe_single()
                .execute()
            )
            meta = (current.data or {}).get("metadata") or {}
            meta["latitude"] = body.ngo_latitude
            meta["longitude"] = body.ngo_longitude
            supabase_admin.table("users").update({"metadata": meta}).eq(
                "id", ngo_id
            ).execute()
        except Exception:
            pass

    # Notify admins
    admin_users = (
        supabase_admin.table("users").select("id").eq("role", "admin").execute()
    )
    for admin in admin_users.data or []:
        _send_notification(
            user_id=admin["id"],
            title="NGO Availability Submitted",
            message=f"NGO submitted availability for request {request_id[:8]}... ({body.available_quantity} units)",
            priority="high",
            data={
                "request_id": request_id,
                "ngo_id": ngo_id,
                "type": "ngo_availability",
            },
        )

    return {
        "message": "Availability submitted successfully",
        "distance_km": distance_km,
        "status": "availability_submitted",
    }


@router.get("/requests/{request_id}/availability")
async def get_availability(
    request_id: str,
    ngo=Depends(require_ngo),
):
    """Get this NGO's availability submission for a specific request."""
    ngo_id = str(ngo.get("id"))

    resp = (
        supabase_admin.table("operational_pulse")
        .select("*")
        .eq("actor_id", ngo_id)
        .eq("target_id", request_id)
        .eq("action_type", "ngo_availability_submitted")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not resp.data:
        return {"submitted": False, "data": None}

    return {"submitted": True, "data": resp.data[0]}


# ================ ASSIGNED REQUESTS ================


@router.get("/requests/assigned")
async def list_assigned_requests(
    ngo=Depends(require_ngo),
    status: Optional[str] = Query(
        None, description="Filter by status: assigned,in_progress,completed,delivered"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List requests currently assigned to this NGO."""
    ngo_id = str(ngo.get("id"))
    query = (
        supabase_admin.table("resource_requests")
        .select("*", count="exact")
        .eq("assigned_to", ngo_id)
        .order("updated_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        query = query.eq("status", status)

    resp = query.execute()
    base_requests = resp.data or []

    requests = _enrich_with_victim(base_requests)

    # Compute status counts
    all_assigned = (
        supabase_admin.table("resource_requests")
        .select("status")
        .eq("assigned_to", ngo_id)
        .execute()
    )
    status_counts = {}
    for r in all_assigned.data or []:
        s = r["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    # Enrich with distance and availability data
    ngo_user = (
        supabase_admin.table("users")
        .select("metadata")
        .eq("id", ngo_id)
        .maybe_single()
        .execute()
    )
    ngo_lat = None
    ngo_lon = None
    if ngo_user.data and ngo_user.data.get("metadata"):
        ngo_lat = ngo_user.data["metadata"].get("latitude")
        ngo_lon = ngo_user.data["metadata"].get("longitude")

    for r in requests:
        r["distance_km"] = None
        if ngo_lat and ngo_lon and r.get("latitude") and r.get("longitude"):
            r["distance_km"] = round(
                haversine_km(ngo_lat, ngo_lon, r["latitude"], r["longitude"]), 2
            )

        # Progress percentage
        current_idx = (
            STATUS_ORDER.index(r["status"]) if r["status"] in STATUS_ORDER else 0
        )
        assigned_idx = STATUS_ORDER.index("assigned")
        completed_idx = STATUS_ORDER.index("completed")
        total_steps = completed_idx - assigned_idx
        steps_done = max(0, current_idx - assigned_idx)
        r["progress_pct"] = min(100, round((steps_done / max(1, total_steps)) * 100))

    return {
        "requests": requests,
        "total": resp.count or 0,
        "status_counts": status_counts,
    }


# ================ CLAIM REQUEST ================


@router.post("/requests/{request_id}/claim")
async def claim_request(
    request_id: str,
    body: ClaimRequestBody,
    ngo=Depends(require_verified_ngo),
):
    """Assign an available approved request to this NGO."""
    ngo_id = str(ngo.get("id"))

    existing = (
        supabase_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")

    if existing.data.get("status") != "approved":
        raise HTTPException(
            status_code=400, detail="Only 'approved' requests can be claimed"
        )

    if existing.data.get("assigned_to"):
        raise HTTPException(status_code=400, detail="Request is already assigned")

    updates = {
        "status": "assigned",
        "assigned_to": ngo_id,
        "assigned_role": "ngo",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.estimated_delivery:
        updates["estimated_delivery"] = body.estimated_delivery

    resp = (
        supabase_admin.table("resource_requests")
        .update(updates)
        .eq("id", request_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to claim request")

    _log_pulse(
        ngo_id,
        request_id,
        "ngo_request_claimed",
        f"NGO claimed request {request_id[:8]}...",
        {"notes": body.notes, "estimated_delivery": body.estimated_delivery},
    )

    return resp.data[0]


# ================ UPDATE DELIVERY STATUS ================


@router.put("/requests/{request_id}/delivery")
async def update_delivery_status(
    request_id: str,
    body: DeliveryStatusUpdate,
    ngo=Depends(require_verified_ngo),
):
    """Update delivery status with strict flow enforcement."""
    ngo_id = str(ngo.get("id"))

    existing = (
        supabase_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")

    if existing.data.get("assigned_to") != ngo_id:
        raise HTTPException(status_code=403, detail="Not assigned to this request")

    current_status = existing.data.get("status")

    if current_status in ("completed", "closed"):
        raise HTTPException(
            status_code=400,
            detail=f"Request is already '{current_status}' and cannot be updated",
        )

    # Enforce strict status flow
    expected_next = VALID_TRANSITIONS.get(current_status)
    if body.new_status != expected_next:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status transition: '{current_status}' → '{body.new_status}'. Expected next status: '{expected_next}'",
        )

    updates = {
        "status": body.new_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    resp = (
        supabase_admin.table("resource_requests")
        .update(updates)
        .eq("id", request_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to update delivery status")

    _log_pulse(
        ngo_id,
        request_id,
        f"status_change_{body.new_status}",
        f"Status changed: {current_status} → {body.new_status}",
        {
            "proof_url": body.proof_url,
            "notes": body.notes,
            "delivery_latitude": body.delivery_latitude,
            "delivery_longitude": body.delivery_longitude,
        },
    )

    # Notify victim
    try:
        await notify_request_status_change(
            request_id=request_id,
            victim_id=existing.data.get("victim_id", ""),
            resource_type=existing.data.get("resource_type", "resources"),
            old_status=current_status,
            new_status=body.new_status,
            admin_id=ngo_id,
            admin_note=body.notes,
        )
    except Exception as e:
        print(f"Error notifying victim: {e}")

    return resp.data[0]


# ================ LEGACY STATUS UPDATE (keep backward compat) ================


@router.put("/requests/{request_id}/status")
async def update_fulfillment_status(
    request_id: str,
    body: UpdateFulfillmentBody,
    ngo=Depends(require_verified_ngo),
):
    """Update fulfillment status (e.g., mark as in_progress or completed). Legacy endpoint."""
    ngo_id = str(ngo.get("id"))

    existing = (
        supabase_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")

    if existing.data.get("assigned_to") != ngo_id:
        raise HTTPException(status_code=403, detail="Not assigned to this request")

    if existing.data.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Request is already completed")

    updates = {
        "status": body.status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    resp = (
        supabase_admin.table("resource_requests")
        .update(updates)
        .eq("id", request_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to update request status")

    _log_pulse(
        ngo_id,
        request_id,
        f"status_change_{body.status}",
        f"Status changed to {body.status}",
        {"proof_url": body.proof_url, "notes": body.notes},
    )

    try:
        await notify_request_status_change(
            request_id=request_id,
            victim_id=existing.data.get("victim_id", ""),
            resource_type=existing.data.get("resource_type", "resources"),
            old_status=existing.data.get("status"),
            new_status=body.status,
            admin_id=ngo_id,
            admin_note=body.notes,
        )
    except Exception as e:
        print(f"Error notifying victim: {e}")

    return resp.data[0]


# ================ ENHANCED DASHBOARD STATS ================


@router.get("/dashboard-stats")
async def get_ngo_dashboard_stats(
    ngo=Depends(require_ngo),
):
    """Get comprehensive dashboard statistics for the NGO."""
    ngo_id = str(ngo.get("id"))

    # All requests assigned to NGO
    assigned_resp = (
        supabase_admin.table("resource_requests")
        .select("status, priority, created_at, updated_at, latitude, longitude")
        .eq("assigned_to", ngo_id)
        .execute()
    )
    assigned_requests = assigned_resp.data or []

    # All approved requests (available)
    approved_resp = (
        supabase_admin.table("resource_requests")
        .select("id", count="exact")
        .eq("status", "approved")
        .is_("assigned_to", "null")
        .execute()
    )

    # Availability submissions by this NGO
    avail_resp = (
        supabase_admin.table("operational_pulse")
        .select("id", count="exact")
        .eq("actor_id", ngo_id)
        .eq("action_type", "ngo_availability_submitted")
        .execute()
    )

    # NGO coordinates for distance calculation
    ngo_user = (
        supabase_admin.table("users")
        .select("metadata")
        .eq("id", ngo_id)
        .maybe_single()
        .execute()
    )
    ngo_lat = None
    ngo_lon = None
    if ngo_user.data and ngo_user.data.get("metadata"):
        ngo_lat = ngo_user.data["metadata"].get("latitude")
        ngo_lon = ngo_user.data["metadata"].get("longitude")

    total_distance = 0.0
    for r in assigned_requests:
        if ngo_lat and ngo_lon and r.get("latitude") and r.get("longitude"):
            total_distance += haversine_km(
                ngo_lat, ngo_lon, r["latitude"], r["longitude"]
            )

    # Compute average response time (approval to assignment)
    response_times = []
    for r in assigned_requests:
        if r.get("created_at") and r.get("updated_at"):
            try:
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                updated = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                diff_hours = (updated - created).total_seconds() / 3600
                if diff_hours > 0:
                    response_times.append(diff_hours)
            except Exception:
                pass

    avg_response_time = (
        round(sum(response_times) / max(1, len(response_times)), 1)
        if response_times
        else 0
    )

    # Status counts
    status_counts = {}
    priority_counts = {}
    for r in assigned_requests:
        s = r["status"]
        p = r["priority"]
        status_counts[s] = status_counts.get(s, 0) + 1
        priority_counts[p] = priority_counts.get(p, 0) + 1

    urgent_count = priority_counts.get("critical", 0) + priority_counts.get("high", 0)

    stats = {
        "total_approved": approved_resp.count or 0,
        "availability_submitted": avail_resp.count or 0,
        "total_assigned": len(assigned_requests),
        "assigned": status_counts.get("assigned", 0),
        "in_progress": status_counts.get("in_progress", 0),
        "delivered": status_counts.get("delivered", 0),
        "completed": status_counts.get("completed", 0),
        "active_deliveries": status_counts.get("in_progress", 0)
        + status_counts.get("assigned", 0),
        "urgent_requests": urgent_count,
        "avg_response_time_hours": avg_response_time,
        "total_distance_km": round(total_distance, 1),
        "by_priority": priority_counts,
        "by_status": status_counts,
    }

    return stats


# ================ NGO INVENTORY (available_resources) ================


@router.get("/inventory")
async def get_ngo_inventory(
    ngo=Depends(require_ngo),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Get this NGO's resource inventory from available_resources."""
    ngo_id = str(ngo.get("id"))

    query = (
        supabase_admin.table("available_resources")
        .select("*", count="exact")
        .eq("provider_id", ngo_id)
        .eq("provider_role", "ngo")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if category:
        query = query.eq("category", category)
    if status:
        query = query.eq("status", status)

    resp = query.execute()
    items = resp.data or []

    # Compute summary
    summary = {
        "total_items": resp.count or 0,
        "total_quantity": sum(i.get("total_quantity", 0) for i in items),
        "reserved_quantity": sum(i.get("claimed_quantity", 0) for i in items),
        "available_quantity": sum(
            (i.get("total_quantity", 0) - i.get("claimed_quantity", 0)) for i in items
        ),
        "low_stock_count": sum(
            1
            for i in items
            if (i.get("total_quantity", 0) - i.get("claimed_quantity", 0))
            < max(1, i.get("total_quantity", 0) * 0.2)
        ),
    }

    # Enrich each item with available quantity
    for i in items:
        i["available_quantity"] = i.get("total_quantity", 0) - i.get(
            "claimed_quantity", 0
        )
        i["is_low_stock"] = i["available_quantity"] < max(
            1, i.get("total_quantity", 0) * 0.2
        )

    return {"items": items, "summary": summary, "total": resp.count or 0}


@router.post("/inventory")
async def add_inventory_item(
    body: InventoryItem,
    ngo=Depends(require_verified_ngo),
):
    """Add a resource to this NGO's inventory."""
    ngo_id = str(ngo.get("id"))

    insert_data = {
        "provider_id": ngo_id,
        "provider_role": "ngo",
        "category": body.category,
        "resource_type": body.resource_type,
        "title": body.title,
        "description": body.description,
        "total_quantity": body.total_quantity,
        "claimed_quantity": 0,
        "unit": body.unit,
        "address_text": body.address_text or "",
        "status": "available",
        "is_active": True,
    }

    resp = supabase_admin.table("available_resources").insert(insert_data).execute()

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to add inventory item")

    _log_pulse(
        ngo_id,
        resp.data[0]["resource_id"],
        "inventory_added",
        f"Added {body.total_quantity} {body.unit} of {body.title}",
    )

    return resp.data[0]


@router.patch("/inventory/{resource_id}")
async def update_inventory_item(
    resource_id: str,
    total_quantity: Optional[int] = Query(None, ge=0),
    status: Optional[str] = Query(None),
    ngo=Depends(require_verified_ngo),
):
    """Update an inventory item (quantity or status)."""
    ngo_id = str(ngo.get("id"))

    existing = (
        supabase_admin.table("available_resources")
        .select("*")
        .eq("resource_id", resource_id)
        .eq("provider_id", ngo_id)
        .single()
        .execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if total_quantity is not None:
        updates["total_quantity"] = total_quantity
    if status:
        updates["status"] = status

    resp = (
        supabase_admin.table("available_resources")
        .update(updates)
        .eq("resource_id", resource_id)
        .execute()
    )

    return resp.data[0] if resp.data else {"message": "Updated"}


# ================ AUDIT LOG ================


@router.get("/audit-log")
async def get_audit_log(
    ngo=Depends(require_ngo),
    action_type: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Fetch audit trail from operational_pulse for this NGO."""
    ngo_id = str(ngo.get("id"))

    query = (
        supabase_admin.table("operational_pulse")
        .select("*", count="exact")
        .eq("actor_id", ngo_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if action_type:
        query = query.eq("action_type", action_type)

    resp = query.execute()
    return {"entries": resp.data or [], "total": resp.count or 0}


# ================ NOTIFICATIONS ================


@router.get("/notifications")
async def get_ngo_notifications(
    ngo=Depends(require_ngo),
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=50),
):
    """Get notifications for this NGO user."""
    ngo_id = str(ngo.get("id"))

    query = (
        supabase_admin.table("notifications")
        .select("*")
        .eq("user_id", ngo_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if unread_only:
        query = query.eq("read", False)

    resp = query.execute()

    # Count unread
    unread_resp = (
        supabase_admin.table("notifications")
        .select("id", count="exact")
        .eq("user_id", ngo_id)
        .eq("read", False)
        .execute()
    )

    return {
        "notifications": resp.data or [],
        "unread_count": unread_resp.count or 0,
    }


@router.post("/notifications/mark-read")
async def mark_notifications_read(
    ngo=Depends(require_ngo),
    notification_ids: Optional[List[str]] = None,
):
    """Mark notifications as read."""
    ngo_id = str(ngo.get("id"))

    if notification_ids:
        supabase_admin.table("notifications").update(
            {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat(),
            }
        ).in_("id", notification_ids).eq("user_id", ngo_id).execute()
    else:
        supabase_admin.table("notifications").update(
            {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", ngo_id).eq("read", False).execute()

    return {"message": "Notifications marked as read"}
