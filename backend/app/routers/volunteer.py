"""
Volunteer Operations Router.

Endpoints for volunteers to:
- View and manage their profile
- Browse available resource-delivery tasks (not just raw disasters)
- Accept or decline a specific task
- Check in/out of a deployment
- Update delivery status for assigned requests
- View full ops history and dashboard stats
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from app.database import db_admin
from app.dependencies import require_verified_volunteer, require_volunteer
from app.services.notification_service import generate_delivery_code, notify_all_admins

router = APIRouter()
security = HTTPBearer()

# ── Delivery status progression ───────────────────────────────────────────────

DELIVERY_STATUS_ORDER = ["assigned", "in_progress", "delivered", "completed"]


# ── Schemas ───────────────────────────────────────────────────────────────────


class VolunteerProfileUpdate(BaseModel):
    skills: list[str] | None = None
    assets: list[str] | None = None
    availability_status: str | None = None
    bio: str | None = None


class CheckInBody(BaseModel):
    disaster_id: str
    task_description: str = Field(..., description="Role/task the volunteer will do")
    latitude: float | None = None
    longitude: float | None = None


class CheckOutBody(BaseModel):
    notes: str | None = Field(None, description="Report or notes on what was accomplished")


class TaskAcceptBody(BaseModel):
    estimated_arrival: str | None = Field(None, description="ISO datetime for estimated arrival at victim")
    notes: str | None = None


class DeliveryStatusUpdate(BaseModel):
    new_status: str = Field(..., description="One of: in_progress, delivered, completed")
    notes: str | None = None
    proof_url: str | None = Field(None, description="URL to delivery proof photo/document")
    delivery_latitude: float | None = None
    delivery_longitude: float | None = None
    delivery_code: str | None = Field(None, description="Confirmation code provided by victim on delivery")


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _log_pulse(actor_id: str, target_id: str, action_type: str, description: str, metadata: dict = None):
    try:
        await db_admin.table("operational_pulse").insert({
            "actor_id": actor_id,
            "target_id": target_id,
            "action_type": action_type,
            "description": description,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }).async_execute()
    except Exception:
        pass


async def _send_notification(user_id: str, title: str, message: str, priority: str = "medium", data: dict = None):
    try:
        await db_admin.table("notifications").insert({
            "user_id": user_id,
            "title": title,
            "message": message,
            "priority": priority,
            "data": data or {},
            "created_at": datetime.now(UTC).isoformat(),
        }).async_execute()
    except Exception:
        pass


# ── Profile ───────────────────────────────────────────────────────────────────


@router.get("/profile")
async def get_volunteer_profile(volunteer=Depends(require_volunteer)):
    """Get the volunteer's extended profile (skills, availability, etc.)."""
    user_id = str(volunteer.get("id"))
    resp = await db_admin.table("volunteer_profiles").select("*").eq("user_id", user_id).maybe_single().async_execute()
    if not resp.data:
        profile = {"user_id": user_id, "skills": [], "assets": [], "availability_status": "available"}
        insert_resp = await db_admin.table("volunteer_profiles").insert(profile).async_execute()
        return insert_resp.data[0] if insert_resp.data else profile
    return resp.data


@router.put("/profile")
async def update_volunteer_profile(data: VolunteerProfileUpdate, volunteer=Depends(require_volunteer)):
    """Update the volunteer's extended profile."""
    user_id = str(volunteer.get("id"))
    update_data = {k: v for k, v in data.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(UTC).isoformat()

    existing = await db_admin.table("volunteer_profiles").select("id").eq("user_id", user_id).maybe_single().async_execute()
    if not existing.data:
        update_data["user_id"] = user_id
        resp = await db_admin.table("volunteer_profiles").insert(update_data).async_execute()
    else:
        resp = await db_admin.table("volunteer_profiles").update(update_data).eq("user_id", user_id).async_execute()

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to update profile")
    return resp.data[0]


# ── Available tasks ───────────────────────────────────────────────────────────


@router.get("/tasks/available")
async def list_available_tasks(
    volunteer=Depends(require_volunteer),
    limit: int = Query(50, ge=1, le=100),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
):
    """
    List approved resource requests that need a volunteer for delivery.
    Returns actual tasks (victim aid requests) rather than raw disasters,
    so volunteers know exactly what they will be delivering and to whom.
    """
    query = (
        db_admin.table("resource_requests")
        .select("id, resource_type, items, quantity, priority, status, disaster_id, latitude, longitude, description, created_at, estimated_delivery, fulfillment_pct")
        .in_("status", ["approved", "availability_submitted", "under_review"])
        .order("priority", desc=True)
        .order("created_at", desc=False)
        .limit(limit)
    )
    if resource_type:
        query = query.eq("resource_type", resource_type)

    resp = await query.async_execute()
    tasks = resp.data or []

    disaster_ids = list({t["disaster_id"] for t in tasks if t.get("disaster_id")})
    disaster_map = {}
    if disaster_ids:
        d_resp = await db_admin.table("disasters").select("id, title, type, severity, status, location_id").in_("id", disaster_ids).async_execute()
        disaster_map = {d["id"]: d for d in (d_resp.data or [])}

    location_ids = list({disaster_map.get(t.get("disaster_id"), {}).get("location_id") for t in tasks if disaster_map.get(t.get("disaster_id"), {}).get("location_id")})
    location_map = {}
    if location_ids:
        loc_resp = await db_admin.table("locations").select("id, name, region").in_("id", location_ids).async_execute()
        location_map = {loc["id"]: loc for loc in (loc_resp.data or [])}

    for task in tasks:
        d = disaster_map.get(task.get("disaster_id"), {})
        task["disaster"] = d
        task["location"] = location_map.get(d.get("location_id"), {})
        if latitude and longitude and task.get("latitude") and task.get("longitude"):
            from math import asin, cos, radians, sin, sqrt
            lat1, lon1 = radians(latitude), radians(longitude)
            lat2, lon2 = radians(task["latitude"]), radians(task["longitude"])
            task["distance_km"] = round(
                2 * 6371 * asin(sqrt(sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2)), 1
            )

    return {"tasks": tasks, "total": len(tasks)}


@router.get("/tasks/available/disasters")
async def list_available_disasters(
    volunteer=Depends(require_volunteer),
    limit: int = Query(50, ge=1, le=100),
):
    """List active disasters that need general volunteer presence (non-delivery tasks)."""
    resp = (
        await db_admin.table("disasters")
        .select("id, title, description, location_id, severity, status, created_at")
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(limit)
        .async_execute()
    )
    disasters = resp.data or []

    location_ids = list({d["location_id"] for d in disasters if d.get("location_id")})
    if location_ids:
        loc_resp = await db_admin.table("locations").select("id, name").in_("id", location_ids).async_execute()
        loc_map = {loc["id"]: loc.get("name") for loc in (loc_resp.data or [])}
        for d in disasters:
            d["location_name"] = loc_map.get(d.get("location_id"), "Unknown")

    return {"disasters": disasters}


# ── Task acceptance ───────────────────────────────────────────────────────────


@router.post("/tasks/{request_id}/accept")
async def accept_delivery_task(
    request_id: str,
    body: TaskAcceptBody,
    volunteer=Depends(require_verified_volunteer),
):
    """
    Volunteer accepts a specific delivery task.
    Adds volunteer as contributor in fulfillment_entries with status 'volunteered'.
    Notifies the victim and admins.
    """
    user_id = str(volunteer.get("id"))
    vol_name = volunteer.get("full_name") or volunteer.get("email") or "A volunteer"

    req_resp = (
        await db_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .maybe_single()
        .async_execute()
    )
    if not req_resp.data:
        raise HTTPException(status_code=404, detail="Request not found")

    req = req_resp.data
    current_status = req.get("status")
    if current_status not in ("approved", "availability_submitted", "under_review"):
        raise HTTPException(
            status_code=400,
            detail=f"Request is not open for volunteer assignment (current status: {current_status})",
        )

    fulfillment_entries = req.get("fulfillment_entries") or []
    already_assigned = any(
        e.get("provider_id") == user_id and e.get("provider_role") == "volunteer"
        for e in fulfillment_entries
    )
    if already_assigned:
        raise HTTPException(status_code=400, detail="You have already accepted this task")

    entry = {
        "provider_id": user_id,
        "provider_name": vol_name,
        "provider_role": "volunteer",
        "status": "volunteered",
        "notes": body.notes,
        "estimated_arrival": body.estimated_arrival,
        "created_at": datetime.now(UTC).isoformat(),
    }
    fulfillment_entries.append(entry)

    await db_admin.table("resource_requests").update({
        "fulfillment_entries": fulfillment_entries,
        "updated_at": datetime.now(UTC).isoformat(),
    }).eq("id", request_id).async_execute()

    await notify_all_admins(
        title="Volunteer accepted task",
        message=f"{vol_name} has volunteered to deliver request {request_id[:8]}... ({req.get('resource_type', 'resources')})",
        notification_type="info",
        related_id=request_id,
        related_type="resource_request",
    )

    victim_id = req.get("victim_id")
    if victim_id:
        await _send_notification(
            user_id=victim_id,
            title="A volunteer is coming",
            message=f"Volunteer {vol_name} has accepted your request and will deliver your {req.get('resource_type', 'items')}.",
            priority="high",
            data={"request_id": request_id, "volunteer_id": user_id, "type": "volunteer_accepted"},
        )

    await _log_pulse(
        actor_id=user_id,
        target_id=request_id,
        action_type="volunteer_task_accepted",
        description=f"Volunteer '{vol_name}' accepted delivery task for request {request_id[:8]}...",
        metadata={"resource_type": req.get("resource_type"), "estimated_arrival": body.estimated_arrival},
    )

    return {"message": "Task accepted successfully", "request_id": request_id}


@router.post("/tasks/{request_id}/decline")
async def decline_delivery_task(request_id: str, volunteer=Depends(require_volunteer)):
    """Remove volunteer from a task they previously accepted."""
    user_id = str(volunteer.get("id"))

    req_resp = (
        await db_admin.table("resource_requests")
        .select("fulfillment_entries")
        .eq("id", request_id)
        .maybe_single()
        .async_execute()
    )
    if not req_resp.data:
        raise HTTPException(status_code=404, detail="Request not found")

    entries = req_resp.data.get("fulfillment_entries") or []
    updated = [e for e in entries if not (e.get("provider_id") == user_id and e.get("provider_role") == "volunteer")]

    if len(updated) == len(entries):
        raise HTTPException(status_code=400, detail="You are not assigned to this task")

    await db_admin.table("resource_requests").update({
        "fulfillment_entries": updated,
        "updated_at": datetime.now(UTC).isoformat(),
    }).eq("id", request_id).async_execute()

    return {"message": "Task declined and removed from your list"}


# ── Assigned delivery requests ────────────────────────────────────────────────


@router.get("/requests/assigned")
async def list_assigned_requests(
    volunteer=Depends(require_volunteer),
    status: str | None = Query(None, description="Filter by: assigned, in_progress, delivered, completed"),
):
    """
    List all resource requests where this volunteer appears in fulfillment_entries.
    This is the volunteer's personal delivery task list.
    """
    user_id = str(volunteer.get("id"))

    query = (
        db_admin.table("resource_requests")
        .select("id, resource_type, items, quantity, priority, status, disaster_id, victim_id, latitude, longitude, description, estimated_delivery, fulfillment_entries, delivery_confirmation_code, created_at, updated_at")
        .order("updated_at", desc=True)
    )
    if status:
        query = query.eq("status", status)

    resp = await query.async_execute()
    
    all_requests = resp.data or []
    requests = []
    for r in all_requests:
        entries = r.get("fulfillment_entries") or []
        if any(e.get("provider_id") == user_id and e.get("provider_role") == "volunteer" for e in entries):
            requests.append(r)

    victim_ids = list({r["victim_id"] for r in requests if r.get("victim_id")})
    victim_map = {}
    if victim_ids:
        v_resp = await db_admin.table("users").select("id, full_name").in_("id", victim_ids).async_execute()
        victim_map = {v["id"]: v.get("full_name", "Unknown") for v in (v_resp.data or [])}

    for r in requests:
        r["victim_name"] = victim_map.get(r.get("victim_id"), "Unknown")
        r["my_entry"] = next(
            (e for e in (r.get("fulfillment_entries") or []) if e.get("provider_id") == user_id),
            None,
        )

    return {"requests": requests, "total": len(requests)}


@router.put("/requests/{request_id}/delivery")
async def update_delivery_status(
    request_id: str,
    body: DeliveryStatusUpdate,
    volunteer=Depends(require_verified_volunteer),
):
    """
    Volunteer updates the delivery status for their assigned request.
    Enforces strict status progression: assigned -> in_progress -> delivered -> completed.
    On 'delivered', generates a confirmation code sent to the victim for receipt verification.
    """
    user_id = str(volunteer.get("id"))
    vol_name = volunteer.get("full_name") or volunteer.get("email") or "Volunteer"

    if body.new_status not in DELIVERY_STATUS_ORDER:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(DELIVERY_STATUS_ORDER)}",
        )

    req_resp = (
        await db_admin.table("resource_requests")
        .select("*")
        .eq("id", request_id)
        .maybe_single()
        .async_execute()
    )
    if not req_resp.data:
        raise HTTPException(status_code=404, detail="Request not found")

    req = req_resp.data
    current_status = req.get("status")

    fulfillment_entries = req.get("fulfillment_entries") or []
    vol_entry = next(
        (e for e in fulfillment_entries if e.get("provider_id") == user_id and e.get("provider_role") == "volunteer"),
        None,
    )
    if not vol_entry:
        raise HTTPException(status_code=403, detail="You are not assigned to this request")

    if current_status in DELIVERY_STATUS_ORDER and body.new_status in DELIVERY_STATUS_ORDER:
        current_idx = DELIVERY_STATUS_ORDER.index(current_status)
        new_idx = DELIVERY_STATUS_ORDER.index(body.new_status)
        if new_idx <= current_idx:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot move status backward from '{current_status}' to '{body.new_status}'",
            )

    now = datetime.now(UTC).isoformat()
    updates: dict = {"status": body.new_status, "updated_at": now}

    vol_entry["status"] = body.new_status
    vol_entry["updated_at"] = now
    if body.notes:
        vol_entry["notes"] = body.notes
    if body.proof_url:
        vol_entry["proof_url"] = body.proof_url
    updates["fulfillment_entries"] = fulfillment_entries

    if body.new_status == "delivered":
        code = generate_delivery_code()
        updates["delivery_confirmation_code"] = code
        if body.delivery_latitude:
            updates["delivery_latitude"] = body.delivery_latitude
        if body.delivery_longitude:
            updates["delivery_longitude"] = body.delivery_longitude

        victim_id = req.get("victim_id")
        if victim_id:
            await _send_notification(
                user_id=victim_id,
                title="Your items have been delivered",
                message=(
                    f"{vol_name} has delivered your {req.get('resource_type', 'items')}. "
                    f"Your confirmation code is: {code}. Please confirm receipt."
                ),
                priority="high",
                data={"request_id": request_id, "delivery_code": code, "type": "delivery_arrived"},
            )

    if body.new_status == "completed" and body.delivery_code:
        stored_code = req.get("delivery_confirmation_code")
        if stored_code and body.delivery_code != stored_code:
            raise HTTPException(status_code=400, detail="Delivery confirmation code does not match")
        updates["delivery_confirmed_at"] = now

    await db_admin.table("resource_requests").update(updates).eq("id", request_id).async_execute()

    await _log_pulse(
        actor_id=user_id,
        target_id=request_id,
        action_type=f"volunteer_delivery_{body.new_status}",
        description=f"Volunteer '{vol_name}' updated delivery to '{body.new_status}' for request {request_id[:8]}...",
        metadata={"new_status": body.new_status, "proof_url": body.proof_url},
    )

    if body.new_status == "delivered":
        await notify_all_admins(
            title="Delivery completed",
            message=f"{vol_name} delivered request {request_id[:8]}... — awaiting victim confirmation.",
            notification_type="info",
            related_id=request_id,
            related_type="resource_request",
        )

    return {"message": f"Delivery status updated to '{body.new_status}'", "request_id": request_id}


# ── Check-in / check-out (general deployment) ─────────────────────────────────


@router.get("/ops/active")
async def get_active_deployment(volunteer=Depends(require_volunteer)):
    """Get the current active check-in deployment for the volunteer."""
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
    did = op.get("disaster_id")
    if did:
        d_resp = await db_admin.table("disasters").select("title, location_id, severity").eq("id", did).maybe_single().async_execute()
        if d_resp.data:
            op["disaster_title"] = d_resp.data.get("title", "Unknown")
            op["severity"] = d_resp.data.get("severity")
            lid = d_resp.data.get("location_id")
            if lid:
                loc_resp = await db_admin.table("locations").select("name").eq("id", lid).maybe_single().async_execute()
                if loc_resp.data:
                    op["location_name"] = loc_resp.data.get("name")

    return {"active_deployment": op}


@router.get("/ops/history")
async def get_ops_history(
    volunteer=Depends(require_volunteer),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, description="Filter by: active, completed"),
):
    """Full history of all volunteer deployments with disaster details."""
    user_id = str(volunteer.get("id"))

    query = (
        db_admin.table("volunteer_ops")
        .select("*")
        .eq("user_id", user_id)
        .order("check_in_time", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)

    resp = await query.async_execute()
    ops = resp.data or []

    disaster_ids = list({o["disaster_id"] for o in ops if o.get("disaster_id")})
    disaster_map = {}
    if disaster_ids:
        d_resp = await db_admin.table("disasters").select("id, title, type, severity").in_("id", disaster_ids).async_execute()
        disaster_map = {d["id"]: d for d in (d_resp.data or [])}

    for op in ops:
        op["disaster"] = disaster_map.get(op.get("disaster_id"), {})

    return {"ops": ops, "total": len(ops)}


@router.post("/ops/check-in")
async def volunteer_check_in(body: CheckInBody, volunteer=Depends(require_verified_volunteer)):
    """Check in to a disaster zone/task."""
    user_id = str(volunteer.get("id"))

    active = await db_admin.table("volunteer_ops").select("id").eq("user_id", user_id).eq("status", "active").async_execute()
    if active.data:
        raise HTTPException(status_code=400, detail="Already checked into an active deployment. Check out first.")

    now = datetime.now(UTC).isoformat()
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

    try:
        vol_name = volunteer.get("full_name") or volunteer.get("email") or "A volunteer"
        await notify_all_admins(
            title="Volunteer checked in",
            message=f"{vol_name} checked in to disaster {body.disaster_id[:8]}... — Task: {body.task_description}",
            notification_type="info",
            related_id=body.disaster_id,
            related_type="disaster",
        )
    except Exception:
        pass

    return resp.data[0]


@router.post("/ops/{op_id}/check-out")
async def volunteer_check_out(op_id: str, body: CheckOutBody, volunteer=Depends(require_volunteer)):
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

    now = datetime.now(UTC)
    hours_worked = 0.0
    check_in_str = existing.data.get("check_in_time")
    if check_in_str:
        try:
            check_in_time = datetime.fromisoformat(check_in_str.replace("Z", "+00:00"))
            hours_worked = round((now - check_in_time).total_seconds() / 3600.0, 2)
        except ValueError:
            pass

    resp = await db_admin.table("volunteer_ops").update({
        "status": "completed",
        "check_out_time": now.isoformat(),
        "hours_worked": hours_worked,
        "notes": body.notes,
        "updated_at": now.isoformat(),
    }).eq("id", op_id).async_execute()

    if not resp.data:
        raise HTTPException(status_code=500, detail="Failed to check out")

    try:
        vol_name = volunteer.get("full_name") or volunteer.get("email") or "A volunteer"
        await notify_all_admins(
            title="Volunteer checked out",
            message=f"{vol_name} checked out after {hours_worked}h. Notes: {body.notes or 'None'}",
            notification_type="info",
            related_id=existing.data.get("disaster_id"),
            related_type="disaster",
        )
    except Exception:
        pass

    return resp.data[0]


# ── Dashboard stats ───────────────────────────────────────────────────────────


@router.get("/dashboard-stats")
async def get_volunteer_dashboard_stats(volunteer=Depends(require_volunteer)):
    """Aggregated dashboard statistics for the volunteer."""
    user_id = str(volunteer.get("id"))

    ops_resp = await db_admin.table("volunteer_ops").select("status, hours_worked").eq("user_id", user_id).async_execute()
    ops = ops_resp.data or []

    total_deployments = len(ops)
    completed_deployments = sum(1 for o in ops if o["status"] == "completed")
    total_hours = sum(o.get("hours_worked", 0.0) for o in ops if o.get("hours_worked"))

    deliveries_resp = (
        await db_admin.table("resource_requests")
        .select("id, status, fulfillment_entries")
        .async_execute()
    )
    all_deliveries = deliveries_resp.data or []
    deliveries = [d for d in all_deliveries if any(e.get("provider_id") == user_id and e.get("provider_role") == "volunteer" for e in (d.get("fulfillment_entries") or []))]
    total_deliveries = len(deliveries)
    completed_deliveries = sum(1 for d in deliveries if d.get("status") in ("delivered", "completed"))

    cert_resp = await db_admin.table("volunteer_certifications").select("id").eq("user_id", user_id).async_execute()
    cert_count = len(cert_resp.data or [])

    return {
        "total_deployments": total_deployments,
        "completed_deployments": completed_deployments,
        "total_hours_contributed": round(total_hours, 1),
        "total_delivery_tasks": total_deliveries,
        "completed_deliveries": completed_deliveries,
        "certifications_count": cert_count,
        "impact_score": min(100, int(completed_deployments * 5 + total_hours * 2 + cert_count * 10 + completed_deliveries * 8)),
    }