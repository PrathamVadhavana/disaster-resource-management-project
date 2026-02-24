"""
NGO Request Fulfillment Workflow Router.

Endpoints for NGOs to view pending requests, claim them, update status, 
and view their own dashboard statistics.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone

from app.database import supabase, supabase_admin
from app.dependencies import require_ngo, require_verified_ngo
from app.services.notification_service import notify_request_status_change

router = APIRouter()
security = HTTPBearer()

# ── Schemas ───────────────────────────────────────────────────────────────────

class ClaimRequestBody(BaseModel):
    estimated_delivery: Optional[str] = Field(None, description="ISO date for estimated delivery")
    notes: Optional[str] = Field(None, description="Internal notes regarding fulfillment")


class UpdateFulfillmentBody(BaseModel):
    status: str = Field(..., description="'in_progress' or 'completed'")
    proof_url: Optional[str] = Field(None, description="URL to delivery proof (image/document)")
    notes: Optional[str] = Field(None, description="Update notes")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/requests/available")
async def list_available_requests(
    ngo=Depends(require_ngo),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    priority: Optional[str] = Query(None, description="Filter by priority: critical,high,medium,low"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all approved requests that have not been assigned yet."""
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

    # Manual enrichment
    victim_ids = [r["victim_id"] for r in base_requests if r.get("victim_id")]
    user_map = {}
    if victim_ids:
        users_resp = supabase_admin.table("users").select("id, full_name, email, phone").in_("id", victim_ids).execute()
        for u in (users_resp.data or []):
            user_map[u["id"]] = u

    requests = []
    for r in base_requests:
        v = user_map.get(r.get("victim_id"), {})
        r["victim_name"] = v.get("full_name") or "Unknown"
        r["victim_phone"] = v.get("phone") or ""
        r["victim_email"] = v.get("email") or ""
        requests.append(r)
    return {"requests": requests, "total": resp.count or 0}


@router.get("/requests/assigned")
async def list_assigned_requests(
    ngo=Depends(require_ngo),
    status: Optional[str] = Query(None, description="Filter by status: assigned,in_progress,completed"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List requests currently assigned to this NGO."""
    query = (
        supabase_admin.table("resource_requests")
        .select("*", count="exact")
        .eq("assigned_to", str(ngo.get("id")))
        .order("updated_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status:
        query = query.eq("status", status)

    resp = query.execute()
    base_requests = resp.data or []

    # Manual enrichment
    victim_ids = [r["victim_id"] for r in base_requests if r.get("victim_id")]
    user_map = {}
    if victim_ids:
        users_resp = supabase_admin.table("users").select("id, full_name, email, phone").in_("id", victim_ids).execute()
        for u in (users_resp.data or []):
            user_map[u["id"]] = u

    requests = []
    for r in base_requests:
        v = user_map.get(r.get("victim_id"), {})
        r["victim_name"] = v.get("full_name") or "Unknown"
        r["victim_phone"] = v.get("phone") or ""
        r["victim_email"] = v.get("email") or ""
        requests.append(r)
    return {"requests": requests, "total": resp.count or 0}


@router.post("/requests/{request_id}/claim")
async def claim_request(
    request_id: str,
    body: ClaimRequestBody,
    ngo=Depends(require_verified_ngo),
):
    """Assign an available approved request to this NGO."""
    ngo_id = str(ngo.get("id"))

    # Verify request is eligible
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
        raise HTTPException(status_code=400, detail="Only 'approved' requests can be claimed")
        
    if existing.data.get("assigned_to"):
        raise HTTPException(status_code=400, detail="Request is already assigned")

    # Claim the request
    updates = {
        "status": "assigned",
        "assigned_to": ngo_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
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

    return resp.data[0]


@router.put("/requests/{request_id}/status")
async def update_fulfillment_status(
    request_id: str,
    body: UpdateFulfillmentBody,
    ngo=Depends(require_verified_ngo),
):
    """Update fulfillment status (e.g., mark as in_progress or completed)."""
    ngo_id = str(ngo.get("id"))

    # Verify ownership
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
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    # Append to existing notes or replace? Replace for simplicity here.
    if body.notes:
        updates["admin_note"] = body.notes  # Assuming we can use admin_note or need a dedicated ngo_note field

    resp = (
        supabase_admin.table("resource_requests")
        .update(updates)
        .eq("id", request_id)
        .execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to update request status")

    # Notify victim
    try:
        await notify_request_status_change(
            request_id=request_id,
            victim_id=existing.data.get("victim_id", ""),
            resource_type=existing.data.get("resource_type", "resources"),
            old_status=existing.data.get("status"),
            new_status=body.status,
            admin_id=ngo_id, 
        )
    except Exception as e:
        print(f"Error notifying victim: {e}")

    return resp.data[0]


@router.get("/dashboard-stats")
async def get_ngo_dashboard_stats(
    ngo=Depends(require_ngo),
):
    """Get aggregated dashboard statistics for the NGO."""
    ngo_id = str(ngo.get("id"))

    resp = (
        supabase_admin.table("resource_requests")
        .select("status, priority")
        .eq("assigned_to", ngo_id)
        .execute()
    )

    requests = resp.data or []

    stats = {
        "total_assigned": len(requests),
        "assigned": sum(1 for r in requests if r["status"] == "assigned"),
        "in_progress": sum(1 for r in requests if r["status"] == "in_progress"),
        "completed": sum(1 for r in requests if r["status"] == "completed"),
        "by_priority": {}
    }

    for r in requests:
        p = r["priority"]
        stats["by_priority"][p] = stats["by_priority"].get(p, 0) + 1

    return stats
