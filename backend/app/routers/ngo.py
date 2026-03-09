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

from app.database import db, db_admin
from app.dependencies import require_ngo, require_verified_ngo
from app.services.notification_service import (
    notify_request_status_change,
    notify_all_admins,
    notify_user,
    generate_delivery_code,
)

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


async def _log_pulse(
    actor_id: str,
    target_id: str,
    action_type: str,
    description: str,
    metadata: dict = None,
):
    """Write to operational_pulse for audit trail."""
    try:
        await db_admin.table("operational_pulse").insert(
            {
                "actor_id": actor_id,
                "target_id": target_id,
                "action_type": action_type,
                "description": description,
                "metadata": metadata or {},
            }
        ).async_execute()
    except Exception as e:
        print(f"Pulse log error: {e}")


async def _send_notification(
    user_id: str, title: str, message: str, priority: str = "medium", data: dict = None
):
    """Insert into the notifications table."""
    try:
        await db_admin.table("notifications").insert(
            {
                "user_id": user_id,
                "title": title,
                "message": message,
                "priority": priority,
                "data": data or {},
            }
        ).async_execute()
    except Exception as e:
        print(f"Notification insert error: {e}")


async def _enrich_with_victim(requests_list: list) -> list:
    """Add victim name / phone / email to a list of request dicts."""
    victim_ids = [r["victim_id"] for r in requests_list if r.get("victim_id")]
    user_map = {}
    if victim_ids:
        users_resp = (
            await db_admin.table("users")
            .select("id, full_name, email, phone")
            .in_("id", victim_ids)
            .async_execute()
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
        await db_admin.table("users")
        .select("metadata")
        .eq("id", ngo_id)
        .maybe_single()
        .async_execute()
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
            await db_admin.table("users").update({"metadata": meta}).eq(
                "id", ngo_id
            ).async_execute()
        except Exception:
            pass

    # Priority mapping for proper ordering (lower = more urgent)
    _PRIO_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    # Both distance and priority need client-side sorting (priority because
    # alphabetical ordering puts "critical" after "medium"), so always fetch
    # all matching records and sort/paginate client-side.
    needs_client_sort = True

    query = (
        db_admin.table("resource_requests")
        .select("*", count="exact")
        .in_("status", ["approved", "availability_submitted", "under_review"])
    )

    if resource_type:
        query = query.eq("resource_type", resource_type)
    if priority:
        query = query.eq("priority", priority)

    resp = await query.async_execute()
    # Show unassigned requests OR partially fulfilled ones (where donors have
    # contributed but an NGO hasn't claimed yet for delivery)
    base_requests = [
        r for r in (resp.data or [])
        if not r.get("assigned_to")
        or r.get("status") == "under_review"
    ]
    total_count = len(base_requests)

    requests = await _enrich_with_victim(base_requests)

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
                await db_admin.table("operational_pulse")
                .select("target_id")
                .eq("actor_id", ngo_id)
                .eq("action_type", "ngo_availability_submitted")
                .in_("target_id", req_ids)
                .async_execute()
            )
            submitted_set = {p["target_id"] for p in (pulse_resp.data or [])}
        except Exception:
            pass

    for r in requests:
        r["availability_submitted"] = r["id"] in submitted_set

    # Sort and paginate client-side
    if sort == "distance" and n_lat and n_lon:
        requests.sort(
            key=lambda r: (
                r["distance_km"] if r["distance_km"] is not None else float("inf")
            )
        )
    else:
        # Sort by priority (critical first) then by created_at descending
        requests.sort(
            key=lambda r: (
                _PRIO_ORDER.get(r.get("priority", "low"), 99),
                -(datetime.fromisoformat(r["created_at"]).timestamp() if r.get("created_at") else 0),
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
        await db_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .async_execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")

    req_status = existing.data.get("status")
    if req_status not in ("approved", "availability_submitted", "under_review"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit availability for request in '{req_status}' status. Must be 'approved' or 'under_review'.",
        )

    # Allow multiple NGOs to contribute — only block if request is fully assigned and in-progress
    if existing.data.get("assigned_to") and req_status in ("in_progress", "delivered", "completed"):
        raise HTTPException(status_code=400, detail="Request is already in progress and cannot accept new availability")

    # Prevent duplicate submission
    dup = (
        await db_admin.table("operational_pulse")
        .select("id")
        .eq("actor_id", ngo_id)
        .eq("target_id", request_id)
        .eq("action_type", "ngo_availability_submitted")
        .async_execute()
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
    await _log_pulse(
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

    # Update request status and track fulfillment
    if req_status in ("approved", "availability_submitted", "under_review"):
        # Track partial fulfillment
        fulfillment_entries = existing.data.get("fulfillment_entries") or []
        ngo_name = ngo.get("full_name") or ngo.get("email") or "NGO"
        entry = {
            "provider_id": ngo_id,
            "provider_name": ngo_name,
            "provider_role": "ngo",
            "donation_type": "resource",
            "amount": 0,
            "resource_items": [{"resource_type": existing.data.get("resource_type", "Custom"), "quantity": body.available_quantity}],
            "status": "availability_submitted",
            "estimated_delivery_time": body.estimated_delivery_time,
            "distance_km": distance_km,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        fulfillment_entries.append(entry)

        # Calculate fulfillment percentage
        request_items = existing.data.get("items") or []
        total_requested = sum(it.get("quantity", 1) for it in request_items) if request_items else existing.data.get("quantity", 1)
        total_fulfilled = sum(
            ri.get("quantity", 0)
            for fe in fulfillment_entries
            for ri in (fe.get("resource_items") or [])
        )
        fulfillment_pct = min(100, round((total_fulfilled / max(total_requested, 1)) * 100))

        new_status = "under_review" if fulfillment_pct < 100 else "availability_submitted"
        await db_admin.table("resource_requests").update(
            {
                "status": new_status,
                "fulfillment_entries": fulfillment_entries,
                "fulfillment_pct": fulfillment_pct,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", request_id).async_execute()

    # Update NGO user metadata with GPS
    if body.ngo_latitude and body.ngo_longitude:
        try:
            current = (
                await db_admin.table("users")
                .select("metadata")
                .eq("id", ngo_id)
                .maybe_single()
                .async_execute()
            )
            meta = (current.data or {}).get("metadata") or {}
            meta["latitude"] = body.ngo_latitude
            meta["longitude"] = body.ngo_longitude
            await db_admin.table("users").update({"metadata": meta}).eq(
                "id", ngo_id
            ).async_execute()
        except Exception:
            pass

    # Notify admins
    admin_users = (
        await db_admin.table("users").select("id").eq("role", "admin").async_execute()
    )
    for admin in admin_users.data or []:
        await _send_notification(
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

    # Notify victim that an NGO has offered to help
    victim_id = existing.data.get("victim_id")
    if victim_id:
        try:
            await notify_user(
                user_id=victim_id,
                title="🤝 A Responder Has Offered Help",
                message=f"An NGO has submitted availability for your {existing.data.get('resource_type', 'resource')} request. An admin will assign them shortly.",
                notification_type="info",
                related_id=request_id,
                related_type="request",
            )
        except Exception:
            pass

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
        await db_admin.table("operational_pulse")
        .select("*")
        .eq("actor_id", ngo_id)
        .eq("target_id", request_id)
        .eq("action_type", "ngo_availability_submitted")
        .order("created_at", desc=True)
        .limit(1)
        .async_execute()
    )

    if not resp.data:
        return {"submitted": False, "data": None}

    return {"submitted": True, "data": resp.data[0]}


@router.get("/requests/{request_id}/pool")
async def get_request_pool_ngo(
    request_id: str, ngo=Depends(require_ngo)
):
    """View resource pool for a request — shows all NGO and donor contributors."""
    resp = (
        await db_admin.table("resource_requests")
        .select("id, items, quantity, resource_type, status, fulfillment_entries, fulfillment_pct")
        .eq("id", request_id)
        .in_("status", ["approved", "assigned", "availability_submitted", "under_review", "in_progress", "delivered", "completed"])
        .single()
        .async_execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Request not found")

    entries = resp.data.get("fulfillment_entries") or []
    items = resp.data.get("items") or []

    ngo_list, donor_list = [], []
    for e in entries:
        info = {
            "provider_name": e.get("provider_name", "Anonymous"),
            "donation_type": e.get("donation_type", "resource"),
            "amount": e.get("amount", 0),
            "resource_items": e.get("resource_items") or [],
            "status": e.get("status", "pledged"),
            "created_at": e.get("created_at"),
        }
        if e.get("provider_role") == "ngo":
            ngo_list.append(info)
        else:
            donor_list.append(info)

    total_requested = sum(it.get("quantity", 1) for it in items) if items else resp.data.get("quantity", 1)
    return {
        "request_id": request_id,
        "fulfillment_pct": resp.data.get("fulfillment_pct", 0),
        "total_requested": total_requested,
        "total_contributors": len(entries),
        "ngo_contributors": ngo_list,
        "donor_contributors": donor_list,
    }


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
    """List requests currently assigned to this NGO (via assigned_to or fulfillment_entries)."""
    ngo_id = str(ngo.get("id"))

    # Match by direct assignment OR as contributor in fulfillment_entries
    or_filter = f'assigned_to.eq.{ngo_id},fulfillment_entries.cs.[{{"provider_id":"{ngo_id}"}}]'

    query = (
        db_admin.table("resource_requests")
        .select("*", count="exact")
        .or_(or_filter)
        .order("updated_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        query = query.eq("status", status)

    resp = await query.async_execute()
    base_requests = resp.data or []

    requests = await _enrich_with_victim(base_requests)

    # Compute status counts
    all_assigned = (
        await db_admin.table("resource_requests")
        .select("status")
        .or_(or_filter)
        .async_execute()
    )
    status_counts = {}
    for r in all_assigned.data or []:
        s = r["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    # Enrich with distance and availability data
    ngo_user = (
        await db_admin.table("users")
        .select("metadata")
        .eq("id", ngo_id)
        .maybe_single()
        .async_execute()
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
        await db_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .async_execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")

    if existing.data.get("status") not in ("approved", "availability_submitted", "under_review"):
        raise HTTPException(
            status_code=400, detail="Only 'approved', 'availability_submitted', or 'under_review' requests can be claimed"
        )

    # Block only if already assigned to a different NGO
    current_assignee = existing.data.get("assigned_to")
    if current_assignee and current_assignee != ngo_id and existing.data.get("assigned_role") == "ngo":
        raise HTTPException(status_code=400, detail="Request is already assigned to another NGO")

    updates = {
        "status": "assigned",
        "assigned_to": ngo_id,
        "assigned_role": "ngo",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.estimated_delivery:
        updates["estimated_delivery"] = body.estimated_delivery

    resp = (
        await db_admin.table("resource_requests")
        .update(updates)
        .eq("id", request_id)
        .async_execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to claim request")

    await _log_pulse(
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
        await db_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .async_execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Request not found")

    if existing.data.get("assigned_to") != ngo_id:
        # Check if NGO is at least a contributor via fulfillment_entries
        fulfillment_entries = existing.data.get("fulfillment_entries") or []
        is_contributor = any(fe.get("provider_id") == ngo_id for fe in fulfillment_entries)
        if not is_contributor:
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

    # Generate delivery confirmation code when status becomes "delivered"
    delivery_code = None
    if body.new_status == "delivered":
        delivery_code = generate_delivery_code()
        updates["delivery_confirmation_code"] = delivery_code

    resp = (
        await db_admin.table("resource_requests")
        .update(updates)
        .eq("id", request_id)
        .async_execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to update delivery status")

    await _log_pulse(
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

        # Send delivery code to victim when delivered
        if body.new_status == "delivered" and delivery_code and existing.data.get("victim_id"):
            await notify_user(
                user_id=existing.data["victim_id"],
                title="📦 Delivery Arrived — Confirm Receipt",
                message=f"Your {existing.data.get('resource_type', 'resource')} has been delivered. Confirmation code: {delivery_code}. Share this code with the deliverer to complete the handoff.",
                notification_type="success",
                related_id=request_id,
                related_type="request",
            )

    except Exception as e:
        print(f"Error notifying victim: {e}")

    # Notify admins about delivery status change
    try:
        await notify_all_admins(
            title=f"🚚 Delivery Status: {body.new_status.replace('_', ' ').title()}",
            message=f"Request {request_id[:8]}... status changed: {current_status} → {body.new_status}",
            notification_type="info",
            related_id=request_id,
            related_type="request",
        )
    except Exception:
        pass

    # On completion, notify the donor who pledged (if any)
    if body.new_status == "completed":
        try:
            donor_resp = (
                await db_admin.table("donations")
                .select("user_id")
                .eq("request_id", request_id)
                .async_execute()
            )
            for d in donor_resp.data or []:
                await notify_user(
                    user_id=d["user_id"],
                    title="🎉 Your Donation Made an Impact!",
                    message=f"The request you pledged support for ({existing.data.get('resource_type', 'resources')}) has been completed. Thank you!",
                    notification_type="success",
                    related_id=request_id,
                    related_type="request",
                )
        except Exception:
            pass

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
        await db_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .async_execute()
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
        await db_admin.table("resource_requests")
        .update(updates)
        .eq("id", request_id)
        .async_execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to update request status")

    await _log_pulse(
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
        await db_admin.table("resource_requests")
        .select("status, priority, created_at, updated_at, latitude, longitude")
        .eq("assigned_to", ngo_id)
        .async_execute()
    )
    assigned_requests = assigned_resp.data or []

    # All approved requests (available) — filter client-side because
    # IS NULL check won't match documents where the field is absent
    approved_resp = (
        await db_admin.table("resource_requests")
        .select("id, assigned_to", count="exact")
        .eq("status", "approved")
        .async_execute()
    )
    approved_resp.data = [r for r in (approved_resp.data or []) if not r.get("assigned_to")]
    approved_resp.count = len(approved_resp.data)

    # Availability submissions by this NGO
    avail_resp = (
        await db_admin.table("operational_pulse")
        .select("id", count="exact")
        .eq("actor_id", ngo_id)
        .eq("action_type", "ngo_availability_submitted")
        .async_execute()
    )

    # NGO coordinates for distance calculation
    ngo_user = (
        await db_admin.table("users")
        .select("metadata")
        .eq("id", ngo_id)
        .maybe_single()
        .async_execute()
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
        db_admin.table("available_resources")
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

    resp = await query.async_execute()
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

    resp = await db_admin.table("available_resources").insert(insert_data).async_execute()

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to add inventory item")

    await _log_pulse(
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
        await db_admin.table("available_resources")
        .select("*")
        .eq("resource_id", resource_id)
        .eq("provider_id", ngo_id)
        .single()
        .async_execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if total_quantity is not None:
        updates["total_quantity"] = total_quantity
    if status:
        updates["status"] = status

    resp = (
        await db_admin.table("available_resources")
        .update(updates)
        .eq("resource_id", resource_id)
        .async_execute()
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
        db_admin.table("operational_pulse")
        .select("*", count="exact")
        .eq("actor_id", ngo_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if action_type:
        query = query.eq("action_type", action_type)

    resp = await query.async_execute()
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
        db_admin.table("notifications")
        .select("*")
        .eq("user_id", ngo_id)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if unread_only:
        query = query.eq("read", False)

    resp = await query.async_execute()

    # Count unread
    unread_resp = (
        await db_admin.table("notifications")
        .select("id", count="exact")
        .eq("user_id", ngo_id)
        .eq("read", False)
        .async_execute()
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
        await db_admin.table("notifications").update(
            {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat(),
            }
        ).in_("id", notification_ids).eq("user_id", ngo_id).async_execute()
    else:
        await db_admin.table("notifications").update(
            {
                "read": True,
                "read_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", ngo_id).eq("read", False).async_execute()

    return {"message": "Notifications marked as read"}
