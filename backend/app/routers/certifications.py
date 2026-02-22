"""
Volunteer certifications CRUD – backed by ``volunteer_certifications`` table.

All endpoints require a valid Bearer token. Users can only manage their own
certifications (RLS enforced at DB level; service-role bypass for admin).
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timezone

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

class CertificationCreate(BaseModel):
    name: str
    issuer: Optional[str] = "Self-reported"
    date_obtained: Optional[str] = None
    expiry_date: Optional[str] = None


class CertificationUpdate(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    date_obtained: Optional[str] = None
    expiry_date: Optional[str] = None


def _compute_status(expiry_date: Optional[str]) -> str:
    if not expiry_date:
        return "active"
    try:
        exp = date.fromisoformat(expiry_date)
        return "expired" if exp < date.today() else "active"
    except Exception:
        return "active"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/certifications")
async def list_certifications(user_id: str = Depends(_get_user_id)):
    """List all certifications for the authenticated volunteer."""
    resp = (
        supabase_admin.table("volunteer_certifications")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    rows = resp.data or []
    # Recompute status based on current date
    for r in rows:
        r["status"] = _compute_status(r.get("expiry_date"))
    return rows


@router.post("/certifications")
async def create_certification(body: CertificationCreate, user_id: str = Depends(_get_user_id)):
    """Add a new certification."""
    status = _compute_status(body.expiry_date)
    row = {
        "user_id": user_id,
        "name": body.name,
        "issuer": body.issuer or "Self-reported",
        "date_obtained": body.date_obtained,
        "expiry_date": body.expiry_date,
        "status": status,
    }
    resp = supabase_admin.table("volunteer_certifications").insert(row).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to create certification")
    return resp.data[0]


@router.put("/certifications/{cert_id}")
async def update_certification(cert_id: str, body: CertificationUpdate, user_id: str = Depends(_get_user_id)):
    """Update an existing certification."""
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.issuer is not None:
        updates["issuer"] = body.issuer
    if body.date_obtained is not None:
        updates["date_obtained"] = body.date_obtained
    if body.expiry_date is not None:
        updates["expiry_date"] = body.expiry_date
        updates["status"] = _compute_status(body.expiry_date)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    resp = (
        supabase_admin.table("volunteer_certifications")
        .update(updates)
        .eq("id", cert_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Certification not found")
    return resp.data[0]


@router.delete("/certifications/{cert_id}")
async def delete_certification(cert_id: str, user_id: str = Depends(_get_user_id)):
    """Delete a certification."""
    resp = (
        supabase_admin.table("volunteer_certifications")
        .delete()
        .eq("id", cert_id)
        .eq("user_id", user_id)
        .execute()
    )
    return {"deleted": True}
