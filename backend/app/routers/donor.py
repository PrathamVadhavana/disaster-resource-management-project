"""
Donor endpoints – donations CRUD, pledge support, and donor stats.

All endpoints require a valid Bearer token. Users can only manage their
own donations/pledges (RLS enforced at DB level).
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from app.dependencies import require_donor, require_verified_donor, get_current_user_id
from app.database import supabase, supabase_admin

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class DonationCreate(BaseModel):
    disaster_id: str
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


# ── Donation Endpoints ────────────────────────────────────────────────────────

@router.get("/donations")
async def list_donations(
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """List all donations for the authenticated donor."""
    q = (
        supabase_admin.table("donations")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        q = q.eq("status", status)
    resp = q.execute()
    base_donations = resp.data or []

    if not base_donations:
        return []

    # Manual enrichment
    disaster_ids = list(set(d["disaster_id"] for d in base_donations if d.get("disaster_id")))
    request_ids = list(set(d["request_id"] for d in base_donations if d.get("request_id")))

    disaster_map = {}
    if disaster_ids:
        d_resp = supabase_admin.table("disasters").select("id, title, type").in_("id", disaster_ids).execute()
        for d in (d_resp.data or []):
            disaster_map[d["id"]] = d

    request_map = {}
    victim_ids = set()
    if request_ids:
        r_resp = supabase_admin.table("resource_requests").select("id, resource_type, description, victim_id").in_("id", request_ids).execute()
        for r in (r_resp.data or []):
            request_map[r["id"]] = r
            if r.get("victim_id"):
                victim_ids.add(r["victim_id"])

    user_map = {}
    if victim_ids:
        u_resp = supabase_admin.table("users").select("id, full_name").in_("id", list(victim_ids)).execute()
        for u in (u_resp.data or []):
            user_map[u["id"]] = u

    # Flatten disaster and victim info
    final_rows = []
    for r in base_donations:
        d = disaster_map.get(r.get("disaster_id"), {})
        r["disaster_title"] = d.get("title", "Unknown")
        r["disaster_type"] = d.get("type", "disaster")
        
        req = request_map.get(r.get("request_id"), {})
        vid = req.get("victim_id")
        v = user_map.get(vid, {})
        r["resource_type"] = req.get("resource_type")
        r["victim_name"] = v.get("full_name") or "Unknown"
        final_rows.append(r)
    return final_rows


@router.post("/donations")
async def create_donation(body: DonationCreate, donor=Depends(require_verified_donor)):
    """Record a new donation."""
    user_id = donor.get("id")
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
    return resp.data[0]


@router.patch("/donations/{donation_id}")
async def update_donation(donation_id: str, body: DonationUpdate, user_id: str = Depends(get_current_user_id)):
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
async def generate_donation_receipt(donation_id: str, user_id: str = Depends(get_current_user_id)):
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
        raise HTTPException(status_code=400, detail="Receipts are only available for completed donations")
        
    # Manual enrichment for disaster and request
    disaster_title = "Unknown Disaster"
    did = donation.get("disaster_id")
    if did:
        d_resp = supabase_admin.table("disasters").select("title").eq("id", did).maybe_single().execute()
        if d_resp.data:
            disaster_title = d_resp.data.get("title", "Unknown Disaster")

    request_desc = "General Support"
    rid = donation.get("request_id")
    if rid:
        r_resp = supabase_admin.table("resource_requests").select("description").eq("id", rid).maybe_single().execute()
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
        "allocated_to": request_desc if donation.get("request_id") else "General Disaster Relief Fund",
        "payment_reference": donation.get("payment_ref", "N/A"),
        "status": "COMPLETED",
        "message": "Thank you for your generous contribution to disaster relief efforts."
    }
    return receipt


@router.delete("/donations/{donation_id}")
async def delete_donation(donation_id: str, user_id: str = Depends(get_current_user_id)):
    """Remove a donation record."""
    supabase_admin.table("donations").delete().eq("id", donation_id).eq("user_id", user_id).execute()
    return {"deleted": True}


# ── Pledge Endpoints ──────────────────────────────────────────────────────────

@router.get("/pledges")
async def list_pledges(user_id: str = Depends(get_current_user_id)):
    """List all pledged causes for the authenticated donor."""
    resp = (
        supabase_admin.table("donor_pledges")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    base_pledges = resp.data or []
    
    # Manual enrichment for disasters
    disaster_ids = list(set(p["disaster_id"] for p in base_pledges if p.get("disaster_id")))
    disaster_map = {}
    if disaster_ids:
        d_resp = supabase_admin.table("disasters").select("id, title, type, severity, status").in_("id", disaster_ids).execute()
        for d in (d_resp.data or []):
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
    row = {"user_id": user_id, "disaster_id": body.disaster_id}
    resp = supabase_admin.table("donor_pledges").insert(row).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create pledge")
    return resp.data[0]


@router.delete("/pledges/{disaster_id}")
async def remove_pledge(disaster_id: str, user_id: str = Depends(get_current_user_id)):
    """Remove a pledge."""
    supabase_admin.table("donor_pledges").delete().eq("disaster_id", disaster_id).eq("user_id", user_id).execute()
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
        .eq("user_id", user_id)
        .execute()
    )
    pledges = pledges_resp.data or []

    return {
        "total_donations": len(donations),
        "completed_donations": len(completed),
        "pending_donations": len(donations) - len(completed),
        "total_donated": total_donated,
        "causes_supported": len(pledges),
        "impact_score": min(100, round(total_donated / 100 + len(completed) * 5 + len(pledges) * 2)),
    }
