"""
Volunteer Operations Router.

Endpoints for volunteers to view available tasks/disaster zones,
check-in, check-out, and view their dashboard stats.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone

from app.database import db, db_admin
from app.dependencies import require_volunteer, require_verified_volunteer
from app.services.notification_service import notify_all_admins

router = APIRouter()
security = HTTPBearer()

# ── Schemas ───────────────────────────────────────────────────────────────────


class VolunteerProfileUpdate(BaseModel):
    skills: Optional[List[str]] = None
    assets: Optional[List[str]] = None
    availability_status: Optional[str] = None
    bio: Optional[str] = None


class CheckInBody(BaseModel):
    disaster_id: str
    task_description: str = Field(..., description="Role/Task the volunteer will do")
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class CheckOutBody(BaseModel):
    notes: Optional[str] = Field(
        None, description="Report or notes on what was accomplished"
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/profile")
async def get_volunteer_profile(
    volunteer=Depends(require_volunteer),
):
    """Get the volunteer's extended profile (skills, availability, etc.)."""
    user_id = str(volunteer.get("id"))
    resp = (
        await db_admin.table("volunteer_profiles")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .async_execute()
    )
    if not resp.data:
        # Auto-create default profile
        profile = {
            "user_id": user_id,
            "skills": [],
            "assets": [],
            "availability_status": "available",
        }
        insert_resp = (
            await db_admin.table("volunteer_profiles").insert(profile).async_execute()
        )
        return insert_resp.data[0] if insert_resp.data else profile
    return resp.data


@router.put("/profile")
async def update_volunteer_profile(
    data: VolunteerProfileUpdate,
    volunteer=Depends(require_volunteer),
):
    """Update the volunteer's extended profile."""
    user_id = str(volunteer.get("id"))
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Ensure profile exists first
    existing = (
        await db_admin.table("volunteer_profiles")
        .select("id")
        .eq("user_id", user_id)
        .maybe_single()
        .async_execute()
    )
    if not existing.data:
        update_data["user_id"] = user_id
        resp = await db_admin.table("volunteer_profiles").insert(update_data).async_execute()
    else:
        resp = (
            await db_admin.table("volunteer_profiles")
            .update(update_data)
            .eq("user_id", user_id)
            .async_execute()
        )
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to update profile")
    return resp.data[0]


@router.get("/assignments/available")
async def list_available_assignments(
    volunteer=Depends(require_volunteer),
    limit: int = Query(50, ge=1, le=100),
):
    """List active disasters that might need volunteers."""
    # This might be further refined with specific task boards from DB,
    # but for now we list active disasters.
    resp = (
        await db_admin.table("disasters")
        .select("id, title, description, location_id, severity, status, created_at")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(limit)
        .async_execute()
    )
    assignments = resp.data or []

    # Enrich locations
    location_ids = list(
        set(a["location_id"] for a in assignments if a.get("location_id"))
    )
    if location_ids:
        loc_resp = (
            await db_admin.table("locations")
            .select("id, name")
            .in_("id", location_ids)
            .async_execute()
        )
        loc_map = {loc["id"]: loc.get("name") for loc in (loc_resp.data or [])}
        for a in assignments:
            a["location_name"] = loc_map.get(a.get("location_id"), "Unknown")

    return {"assignments": assignments}


@router.get("/ops/active")
async def get_active_deployment(
    volunteer=Depends(require_volunteer),
):
    """Get the current active check-in (deployment) for the volunteer."""
    user_id = str(volunteer.get("id"))
    resp = (
        await db_admin.table("volunteer_ops")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .maybe_single()
        .async_execute()
    )
    if not resp.data:
        return {"active_deployment": None}

    op = resp.data
    # Manual enrichment for disaster info
    did = op.get("disaster_id")
    if did:
        d_resp = (
            await db_admin.table("disasters")
            .select("title, location_id, severity")
            .eq("id", did)
            .maybe_single()
            .async_execute()
        )
        if d_resp.data:
            op["disaster_title"] = d_resp.data.get("title", "Unknown")
            op["severity"] = d_resp.data.get("severity")
            lid = d_resp.data.get("location_id")
            if lid:
                loc_resp = (
                    await db_admin.table("locations")
                    .select("name")
                    .eq("id", lid)
                    .maybe_single()
                    .async_execute()
                )
                if loc_resp.data:
                    op["location_name"] = loc_resp.data.get("name")

    return {"active_deployment": op}


@router.post("/ops/check-in")
async def volunteer_check_in(
    body: CheckInBody,
    volunteer=Depends(require_verified_volunteer),
):
    """Check in to a disaster zone/task."""
    user_id = str(volunteer.get("id"))

    # Verify no active deployments
    active = (
        await db_admin.table("volunteer_ops")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .async_execute()
    )
    if active.data:
        raise HTTPException(
            status_code=400,
            detail="Already checked into an active deployment. Check out first.",
        )

    now = datetime.now(timezone.utc).isoformat()
    row = {
        "user_id": user_id,
        "disaster_id": body.disaster_id,
        "task_description": body.task_description,
        "latitude": body.latitude,
        "longitude": body.longitude,
        "status": "active",
        "check_in_time": now,
        "updated_at": now,
    }

    resp = await db_admin.table("volunteer_ops").insert(row).async_execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to check in")

    # Notify admins about volunteer check-in
    try:
        vol_name = volunteer.get("full_name") or volunteer.get("email") or "A volunteer"
        await notify_all_admins(
            title="✅ Volunteer Checked In",
            message=f"{vol_name} checked in to disaster {body.disaster_id[:8]}... — Task: {body.task_description}",
            notification_type="info",
            related_id=body.disaster_id,
            related_type="disaster",
        )
    except Exception:
        pass

    return resp.data[0]


@router.post("/ops/{op_id}/check-out")
async def volunteer_check_out(
    op_id: str,
    body: CheckOutBody,
    volunteer=Depends(require_volunteer),
):
    """Check out of an active deployment."""
    user_id = str(volunteer.get("id"))

    existing = (
        await db_admin.table("volunteer_ops")
        .select("*")
        .eq("id", op_id)
        .eq("user_id", user_id)
        .single()
        .async_execute()
    )

    if not existing.data:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if existing.data.get("status") != "active":
        raise HTTPException(status_code=400, detail="Deployment is already completed")

    now = datetime.now(timezone.utc)
    check_in_time_str = existing.data.get("check_in_time")

    # Calculate hours worked
    hours_worked = 0.0
    if check_in_time_str:
        try:
            check_in_time = datetime.fromisoformat(
                check_in_time_str.replace("Z", "+00:00")
            )
            hours_worked = round((now - check_in_time).total_seconds() / 3600.0, 2)
        except ValueError:
            pass

    updates = {
        "status": "completed",
        "check_out_time": now.isoformat(),
        "hours_worked": hours_worked,
        "notes": body.notes,
        "updated_at": now.isoformat(),
    }

    resp = (
        await db_admin.table("volunteer_ops").update(updates).eq("id", op_id).async_execute()
    )

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to check out")

    # Notify admins about volunteer check-out
    try:
        vol_name = volunteer.get("full_name") or volunteer.get("email") or "A volunteer"
        await notify_all_admins(
            title="🏁 Volunteer Checked Out",
            message=f"{vol_name} checked out after {hours_worked}h. Notes: {body.notes or 'None'}",
            notification_type="info",
            related_id=existing.data.get("disaster_id"),
            related_type="disaster",
        )
    except Exception:
        pass

    return resp.data[0]


@router.get("/dashboard-stats")
async def get_volunteer_dashboard_stats(
    volunteer=Depends(require_volunteer),
):
    """Get aggregated dashboard statistics for the volunteer."""
    user_id = str(volunteer.get("id"))

    # Active ops and hours
    resp = (
        await db_admin.table("volunteer_ops")
        .select("status, hours_worked")
        .eq("user_id", user_id)
        .async_execute()
    )
    ops = resp.data or []

    total_deployments = len(ops)
    completed_deployments = sum(1 for o in ops if o["status"] == "completed")
    total_hours = sum(o.get("hours_worked", 0.0) for o in ops if o.get("hours_worked"))

    # Get certifications count
    cert_resp = (
        await db_admin.table("volunteer_certifications")
        .select("id")
        .eq("user_id", user_id)
        .async_execute()
    )
    cert_count = len(cert_resp.data or [])

    return {
        "total_deployments": total_deployments,
        "completed_deployments": completed_deployments,
        "total_hours_contributed": round(total_hours, 1),
        "certifications_count": cert_count,
        "impact_score": min(
            100, int(completed_deployments * 5 + total_hours * 2 + cert_count * 10)
        ),
    }
