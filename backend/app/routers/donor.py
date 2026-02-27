"""
Donor endpoints – donations CRUD, pledge support, and donor stats.

All endpoints require a valid Bearer token. Users can only manage their
own donations/pledges (RLS enforced at DB level).
"""

import math

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.dependencies import require_donor, require_verified_donor, get_current_user_id
from app.database import supabase, supabase_admin

router = APIRouter()


# ── GPS Utility ───────────────────────────────────────────────────────────────


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two GPS points in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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


# ── Schemas ───────────────────────────────────────────────────────────────────


class DonationCreate(BaseModel):
    disaster_id: Optional[str] = None
    request_id: Optional[str] = None
    amount: float = 0
    currency: str = "USD"
    status: str = "pending"
    payment_ref: Optional[str] = None
    notes: Optional[str] = None


class DonationUpdate(BaseModel):
    amount: Optional[float] = None
    status: Optional[str] = None
    request_id: Optional[str] = None
    payment_ref: Optional[str] = None
    notes: Optional[str] = None


class PledgeCreate(BaseModel):
    disaster_id: str


# ── Approved Requests (for donor browsing) ────────────────────────────────────


@router.get("/approved-requests")
async def list_approved_requests(
    resource_type: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    donor_latitude: Optional[float] = Query(None, description="Donor GPS latitude"),
    donor_longitude: Optional[float] = Query(None, description="Donor GPS longitude"),
    sort: Optional[str] = Query(
        "priority", description="Sort: priority, distance, created_at"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    donor=Depends(require_donor),
):
    """List approved resource requests that donors can pledge support for.
    Supports distance-based sorting when GPS coordinates are provided."""
    import json

    try:
        # Resolve donor GPS early so we know if distance sorting is needed
        donor_id = donor.get("id")
        d_lat = donor_latitude
        d_lon = donor_longitude
        if d_lat is None or d_lon is None:
            try:
                du = (
                    supabase_admin.table("users")
                    .select("metadata")
                    .eq("id", donor_id)
                    .maybe_single()
                    .execute()
                )
                if du.data and du.data.get("metadata"):
                    d_lat = d_lat or du.data["metadata"].get("latitude")
                    d_lon = d_lon or du.data["metadata"].get("longitude")
            except Exception:
                pass

        # Store donor GPS in metadata for future use
        if donor_latitude and donor_longitude:
            try:
                cur = (
                    supabase_admin.table("users")
                    .select("metadata")
                    .eq("id", donor_id)
                    .maybe_single()
                    .execute()
                )
                meta = (cur.data or {}).get("metadata") or {}
                meta["latitude"] = donor_latitude
                meta["longitude"] = donor_longitude
                supabase_admin.table("users").update({"metadata": meta}).eq(
                    "id", donor_id
                ).execute()
            except Exception:
                pass

        needs_client_sort = sort == "distance" and d_lat and d_lon

        query = supabase_admin.table("resource_requests").select("*", count="exact")
        query = query.in_("status", ["approved", "assigned"])

        if resource_type:
            query = query.eq("resource_type", resource_type)
        if priority:
            query = query.eq("priority", priority)
        if search:
            query = query.or_(
                f"description.ilike.%{search}%,resource_type.ilike.%{search}%"
            )

        if needs_client_sort:
            # Fetch all records for client-side distance sort, then paginate
            query = query.order("created_at", desc=True)
        else:
            query = query.order("created_at", desc=True)
            offset = (page - 1) * page_size
            query = query.range(offset, offset + page_size - 1)

        response = query.execute()
        base_requests = response.data or []
        total_count = response.count or 0

        # Enrich with victim info
        victim_ids = list(
            set(r["victim_id"] for r in base_requests if r.get("victim_id"))
        )
        user_map = {}
        if victim_ids:
            users_resp = (
                supabase_admin.table("users")
                .select("id, full_name")
                .in_("id", victim_ids)
                .execute()
            )
            for u in users_resp.data or []:
                user_map[u["id"]] = u

        # Check which requests this donor has already pledged to
        existing_donations = []
        if donor_id and base_requests:
            req_ids = [r["id"] for r in base_requests]
            d_resp = (
                supabase_admin.table("donations")
                .select("request_id")
                .eq("user_id", donor_id)
                .in_("request_id", req_ids)
                .execute()
            )
            existing_donations = [d["request_id"] for d in (d_resp.data or [])]

        requests = []
        for r in base_requests:
            row = dict(r)
            for key in (
                "items",
                "attachments",
                "nlp_classification",
                "urgency_signals",
            ):
                val = row.get(key)
                if val is None:
                    row[key] = []
                elif isinstance(val, str):
                    try:
                        row[key] = json.loads(val)
                    except (json.JSONDecodeError, TypeError):
                        row[key] = []

            vid = row.get("victim_id")
            v = user_map.get(vid, {})
            row["victim_name"] = v.get("full_name") or "Anonymous"
            row["already_pledged"] = row["id"] in existing_donations

            # Compute distance
            row["distance_km"] = None
            if d_lat and d_lon and row.get("latitude") and row.get("longitude"):
                row["distance_km"] = round(
                    haversine_km(d_lat, d_lon, row["latitude"], row["longitude"]), 2
                )

            requests.append(row)

        # Sort and paginate for distance mode
        if needs_client_sort:
            requests.sort(
                key=lambda r: (
                    r["distance_km"] if r["distance_km"] is not None else float("inf")
                )
            )
            offset = (page - 1) * page_size
            requests = requests[offset : offset + page_size]
        elif sort == "priority":
            prio_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            requests.sort(key=lambda r: prio_order.get(r.get("priority", "medium"), 2))

        return {
            "requests": requests,
            "total": total_count,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        print(f"\u274c DONOR APPROVED REQUESTS ERROR: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching approved requests: {str(e)}"
        )


# ── Donation Endpoints ────────────────────────────────────────────────────────


@router.get("/donations")
async def list_donations(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
):
    """List all donations for the authenticated donor."""
    q = (
        supabase_admin.table("donations")
        .select("*", count="exact")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
    )
    if status:
        q = q.eq("status", status)

    offset = (page - 1) * page_size
    q = q.range(offset, offset + page_size - 1)
    resp = q.execute()
    base_donations = resp.data or []
    total_count = resp.count or 0

    if not base_donations:
        return {
            "donations": [],
            "total": total_count,
            "page": page,
            "page_size": page_size,
        }

    # Manual enrichment
    disaster_ids = list(
        set(d["disaster_id"] for d in base_donations if d.get("disaster_id"))
    )
    request_ids = list(
        set(d["request_id"] for d in base_donations if d.get("request_id"))
    )

    disaster_map = {}
    if disaster_ids:
        d_resp = (
            supabase_admin.table("disasters")
            .select("id, title, type")
            .in_("id", disaster_ids)
            .execute()
        )
        for d in d_resp.data or []:
            disaster_map[d["id"]] = d

    request_map = {}
    victim_ids = set()
    if request_ids:
        r_resp = (
            supabase_admin.table("resource_requests")
            .select("id, resource_type, description, victim_id")
            .in_("id", request_ids)
            .execute()
        )
        for r in r_resp.data or []:
            request_map[r["id"]] = r
            if r.get("victim_id"):
                victim_ids.add(r["victim_id"])

    user_map = {}
    if victim_ids:
        u_resp = (
            supabase_admin.table("users")
            .select("id, full_name")
            .in_("id", list(victim_ids))
            .execute()
        )
        for u in u_resp.data or []:
            user_map[u["id"]] = u

    # Flatten disaster and victim info
    final_rows = []
    for r in base_donations:
        d = disaster_map.get(r.get("disaster_id"), {})
        req = request_map.get(r.get("request_id"), {})
        vid = req.get("victim_id")
        v = user_map.get(vid, {})

        # Use disaster title if available, otherwise show request resource type
        if d.get("title"):
            r["disaster_title"] = d["title"]
            r["disaster_type"] = d.get("type", "disaster")
        elif req.get("resource_type"):
            r["disaster_title"] = req["resource_type"]
            r["disaster_type"] = "pledge"
        else:
            r["disaster_title"] = "Donation"
            r["disaster_type"] = "general"

        r["resource_type"] = req.get("resource_type")
        r["description"] = req.get("description")
        r["victim_name"] = v.get("full_name") or None
        r["request_id"] = r.get("request_id")
        final_rows.append(r)
    return {
        "donations": final_rows,
        "total": total_count,
        "page": page,
        "page_size": page_size,
    }


@router.post("/donations")
async def create_donation(body: DonationCreate, donor=Depends(require_verified_donor)):
    """Record a new donation / pledge. Notifies admins and logs to operational_pulse."""
    user_id = donor.get("id")
    donor_name = donor.get("full_name") or donor.get("email") or "Unknown Donor"
    row = {
        "user_id": user_id,
        "disaster_id": body.disaster_id,
        "request_id": body.request_id,
        "amount": body.amount,
        "currency": body.currency,
        "status": body.status,
        "payment_ref": body.payment_ref,
        "notes": body.notes,
    }
    resp = supabase_admin.table("donations").insert(row).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to record donation")

    donation = resp.data[0]

    # If this is a request-linked pledge, update status & notify admin
    if body.request_id:
        # Fetch the request for context
        req_resp = (
            supabase_admin.table("resource_requests")
            .select("status, resource_type")
            .eq("id", body.request_id)
            .maybe_single()
            .execute()
        )
        resource_type = "resources"
        if req_resp.data:
            resource_type = req_resp.data.get("resource_type", "resources")
            # Mark the request so admin knows there are pledges
            current_status = req_resp.data.get("status")
            if current_status == "approved":
                supabase_admin.table("resource_requests").update(
                    {
                        "status": "availability_submitted",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", body.request_id).execute()

        # Compute distance for metadata
        distance_km = None
        try:
            du = (
                supabase_admin.table("users")
                .select("metadata")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if du.data and du.data.get("metadata"):
                d_lat = du.data["metadata"].get("latitude")
                d_lon = du.data["metadata"].get("longitude")
                if d_lat and d_lon and req_resp.data:
                    rr = (
                        supabase_admin.table("resource_requests")
                        .select("latitude, longitude")
                        .eq("id", body.request_id)
                        .maybe_single()
                        .execute()
                    )
                    if rr.data and rr.data.get("latitude") and rr.data.get("longitude"):
                        distance_km = round(
                            haversine_km(
                                d_lat, d_lon, rr.data["latitude"], rr.data["longitude"]
                            ),
                            2,
                        )
        except Exception:
            pass

        # Log to operational_pulse
        _log_pulse(
            actor_id=user_id,
            target_id=body.request_id,
            action_type="donor_pledge_submitted",
            description=f"Donor '{donor_name}' pledged support for request {body.request_id[:8]}...",
            metadata={
                "notes": body.notes,
                "amount": body.amount,
                "distance_km": distance_km,
                "provider_role": "donor",
            },
        )

        # Notify all admins
        admin_users = (
            supabase_admin.table("users").select("id").eq("role", "admin").execute()
        )
        for admin in admin_users.data or []:
            _send_notification(
                user_id=admin["id"],
                title="Donor Pledge Submitted",
                message=f"Donor '{donor_name}' pledged support for {resource_type} request {body.request_id[:8]}...",
                priority="high",
                data={
                    "request_id": body.request_id,
                    "donor_id": user_id,
                    "type": "donor_pledge",
                },
            )

    return donation


@router.patch("/donations/{donation_id}")
async def update_donation(
    donation_id: str, body: DonationUpdate, user_id: str = Depends(get_current_user_id)
):
    """Update a donation (e.g. mark completed with amount)."""
    updates = {}
    if body.amount is not None:
        updates["amount"] = body.amount
    if body.status is not None:
        updates["status"] = body.status
    if body.request_id is not None:
        updates["request_id"] = body.request_id
    if body.payment_ref is not None:
        updates["payment_ref"] = body.payment_ref
    if body.notes is not None:
        updates["notes"] = body.notes
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    resp = (
        supabase_admin.table("donations")
        .update(updates)
        .eq("id", donation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Donation not found")
    return resp.data[0]


@router.get("/donations/{donation_id}/receipt")
async def generate_donation_receipt(
    donation_id: str, user_id: str = Depends(get_current_user_id)
):
    """Generate a digital receipt for a completed donation."""
    # Fetch donation without joins
    resp = (
        supabase_admin.table("donations")
        .select("*")
        .eq("id", donation_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Donation not found")

    donation = resp.data
    if donation.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail="Receipts are only available for completed donations",
        )

    # Manual enrichment for disaster and request
    disaster_title = "Unknown Disaster"
    did = donation.get("disaster_id")
    if did:
        d_resp = (
            supabase_admin.table("disasters")
            .select("title")
            .eq("id", did)
            .maybe_single()
            .execute()
        )
        if d_resp.data:
            disaster_title = d_resp.data.get("title", "Unknown Disaster")

    request_desc = "General Support"
    rid = donation.get("request_id")
    if rid:
        r_resp = (
            supabase_admin.table("resource_requests")
            .select("description")
            .eq("id", rid)
            .maybe_single()
            .execute()
        )
        if r_resp.data:
            request_desc = r_resp.data.get("description", "General Support")

    # Generate a simple formatted receipt
    receipt = {
        "receipt_id": f"REC-{donation['id'][:8].upper()}",
        "date": donation["updated_at"],
        "donor_id": user_id,
        "amount": donation["amount"],
        "currency": donation["currency"],
        "cause": disaster_title,
        "allocated_to": (
            request_desc
            if donation.get("request_id")
            else "General Disaster Relief Fund"
        ),
        "payment_reference": donation.get("payment_ref", "N/A"),
        "status": "COMPLETED",
        "message": "Thank you for your generous contribution to disaster relief efforts.",
    }
    return receipt


@router.delete("/donations/{donation_id}")
async def delete_donation(
    donation_id: str, user_id: str = Depends(get_current_user_id)
):
    """Remove a donation record."""
    supabase_admin.table("donations").delete().eq("id", donation_id).eq(
        "user_id", user_id
    ).execute()
    return {"deleted": True}


# ── Pledge Endpoints ──────────────────────────────────────────────────────────


@router.get("/pledges")
async def list_pledges(user_id: str = Depends(get_current_user_id)):
    """List all pledged causes for the authenticated donor."""
    resp = (
        supabase_admin.table("donor_pledges")
        .select("*")
        .eq("donor_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    base_pledges = resp.data or []

    # Manual enrichment for disasters
    disaster_ids = list(
        set(p["disaster_id"] for p in base_pledges if p.get("disaster_id"))
    )
    disaster_map = {}
    if disaster_ids:
        d_resp = (
            supabase_admin.table("disasters")
            .select("id, title, type, severity, status")
            .in_("id", disaster_ids)
            .execute()
        )
        for d in d_resp.data or []:
            disaster_map[d["id"]] = d

    pledges = []
    for p in base_pledges:
        p["disasters"] = disaster_map.get(p.get("disaster_id"))
        pledges.append(p)
    return pledges


@router.post("/pledges")
async def create_pledge(body: PledgeCreate, donor=Depends(require_verified_donor)):
    """Pledge support for a disaster cause."""
    user_id = donor.get("id")
    row = {"donor_id": user_id, "disaster_id": body.disaster_id}
    resp = supabase_admin.table("donor_pledges").insert(row).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create pledge")
    return resp.data[0]


@router.delete("/pledges/{disaster_id}")
async def remove_pledge(disaster_id: str, user_id: str = Depends(get_current_user_id)):
    """Remove a pledge."""
    supabase_admin.table("donor_pledges").delete().eq("disaster_id", disaster_id).eq(
        "donor_id", user_id
    ).execute()
    return {"deleted": True}


# ── Donor Stats ───────────────────────────────────────────────────────────────


@router.get("/stats")
async def donor_stats(user_id: str = Depends(get_current_user_id)):
    """Aggregated stats for the donor dashboard."""
    donations_resp = (
        supabase_admin.table("donations")
        .select("amount, status")
        .eq("user_id", user_id)
        .execute()
    )
    donations = donations_resp.data or []
    completed = [d for d in donations if d["status"] == "completed"]
    total_donated = sum(float(d.get("amount", 0)) for d in completed)

    pledges_resp = (
        supabase_admin.table("donor_pledges")
        .select("id")
        .eq("donor_id", user_id)
        .execute()
    )
    pledges = pledges_resp.data or []

    return {
        "total_donations": len(donations),
        "completed_donations": len(completed),
        "pending_donations": len(donations) - len(completed),
        "total_donated": total_donated,
        "causes_supported": len(pledges),
        "impact_score": min(
            100, round(total_donated / 100 + len(completed) * 5 + len(pledges) * 2)
        ),
    }
