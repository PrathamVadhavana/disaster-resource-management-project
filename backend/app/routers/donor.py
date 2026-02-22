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

from app.database import supabase, supabase_admin

router = APIRouter()
security = HTTPBearer()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        resp = supabase.auth.get_user(credentials.credentials)
        if not resp or not resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return str(resp.user.id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


# ── Schemas ───────────────────────────────────────────────────────────────────

class DonationCreate(BaseModel):
    disaster_id: str
    amount: float = 0
    currency: str = "USD"
    status: str = "pending"
    payment_ref: Optional[str] = None
    notes: Optional[str] = None


class DonationUpdate(BaseModel):
    amount: Optional[float] = None
    status: Optional[str] = None
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
    user_id: str = Depends(_get_user_id),
):
    """List all donations for the authenticated donor."""
    q = (
        supabase_admin.table("donations")
        .select("*, disasters(id, title, type, severity, status)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        q = q.eq("status", status)
    resp = q.execute()
    rows = resp.data or []
    # Flatten disaster info for frontend convenience
    for r in rows:
        d = r.pop("disasters", None) or {}
        r["disaster_title"] = d.get("title", "Unknown")
        r["disaster_type"] = d.get("type", "disaster")
        r["disaster_severity"] = d.get("severity", "medium")
        r["disaster_status"] = d.get("status", "unknown")
    return rows


@router.post("/donations")
async def create_donation(body: DonationCreate, user_id: str = Depends(_get_user_id)):
    """Record a new donation."""
    row = {
        "user_id": user_id,
        "disaster_id": body.disaster_id,
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
async def update_donation(donation_id: str, body: DonationUpdate, user_id: str = Depends(_get_user_id)):
    """Update a donation (e.g. mark completed with amount)."""
    updates = {}
    if body.amount is not None:
        updates["amount"] = body.amount
    if body.status is not None:
        updates["status"] = body.status
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


@router.delete("/donations/{donation_id}")
async def delete_donation(donation_id: str, user_id: str = Depends(_get_user_id)):
    """Remove a donation record."""
    supabase_admin.table("donations").delete().eq("id", donation_id).eq("user_id", user_id).execute()
    return {"deleted": True}


# ── Pledge Endpoints ──────────────────────────────────────────────────────────

@router.get("/pledges")
async def list_pledges(user_id: str = Depends(_get_user_id)):
    """List all pledged causes for the authenticated donor."""
    resp = (
        supabase_admin.table("donor_pledges")
        .select("*, disasters(id, title, type, severity, status)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


@router.post("/pledges")
async def create_pledge(body: PledgeCreate, user_id: str = Depends(_get_user_id)):
    """Pledge support for a disaster cause."""
    row = {"user_id": user_id, "disaster_id": body.disaster_id}
    resp = supabase_admin.table("donor_pledges").insert(row).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create pledge")
    return resp.data[0]


@router.delete("/pledges/{disaster_id}")
async def remove_pledge(disaster_id: str, user_id: str = Depends(_get_user_id)):
    """Remove a pledge."""
    supabase_admin.table("donor_pledges").delete().eq("disaster_id", disaster_id).eq("user_id", user_id).execute()
    return {"deleted": True}


# ── Donor Stats ───────────────────────────────────────────────────────────────

@router.get("/stats")
async def donor_stats(user_id: str = Depends(_get_user_id)):
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
