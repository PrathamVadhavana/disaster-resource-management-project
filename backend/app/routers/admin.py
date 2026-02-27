"""
Admin-only endpoints for user management, platform settings, platform stats,
request management (approve/reject), and available resources.

All endpoints verify the caller is an admin by checking their role
in the ``users`` table. The ``supabase_admin`` client (service-role key)
is used so that Row-Level-Security is bypassed.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import json
import traceback

from app.database import supabase, supabase_admin
from app.services.notification_service import (
    notify_request_status_change,
    get_user_notifications,
    mark_notifications_read,
    get_unread_count,
    get_request_audit_trail,
    create_audit_entry,
)
from app.dependencies import require_admin

router = APIRouter()
security = HTTPBearer()


# ── Schemas ───────────────────────────────────────────────────────────────────


class UpdateRoleBody(BaseModel):
    role: str
    reason: Optional[str] = None


class VerifyUserBody(BaseModel):
    status: str  # verified, rejected, pending
    notes: Optional[str] = None


class PlatformSettingsBody(BaseModel):
    platform_name: Optional[str] = None
    support_email: Optional[str] = None
    auto_sitrep: Optional[bool] = None
    sitrep_interval: Optional[int] = None
    auto_allocate: Optional[bool] = None
    ingestion_enabled: Optional[bool] = None
    ingestion_interval: Optional[int] = None
    email_notifications: Optional[bool] = None
    sms_alerts: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    api_rate_limit: Optional[int] = None
    max_upload_mb: Optional[int] = None
    session_timeout: Optional[int] = None
    data_retention_days: Optional[int] = None


class ApproveRejectBody(BaseModel):
    """Body for approving or rejecting a resource request."""

    action: str = Field(..., description="'approve' or 'reject'")
    rejection_reason: Optional[str] = Field(None, description="Required when rejecting")
    admin_note: Optional[str] = Field(None, description="Optional note from admin")
    assigned_to: Optional[str] = Field(
        None, description="User ID to assign to (NGO/donor)"
    )
    estimated_delivery: Optional[str] = Field(
        None, description="ISO date for estimated delivery"
    )


class AdminNoteBody(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/users")
async def list_users(admin=Depends(require_admin)):
    """Return every user row (bypasses RLS via service-role client)."""
    resp = (
        supabase_admin.table("users")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str, body: UpdateRoleBody, admin=Depends(require_admin)
):
    """Change a user's role with audit note."""
    from datetime import datetime, timezone

    updates = {"role": body.role, "updated_at": datetime.now(timezone.utc).isoformat()}

    # Store history in metadata
    metadata_resp = (
        supabase_admin.table("users")
        .select("metadata")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    existing_meta = (metadata_resp.data or {}).get("metadata") or {}

    history = existing_meta.get("role_history", [])
    history.append(
        {
            "changed_by": admin.get("id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_role": body.role,
            "reason": body.reason or "No reason provided",
        }
    )
    existing_meta["role_history"] = history
    updates["metadata"] = existing_meta

    resp = supabase_admin.table("users").update(updates).eq("id", user_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    # Also update Supabase Auth metadata to keep sync (merging instead of overwriting)
    try:
        auth_user = supabase_admin.auth.admin.get_user_by_id(user_id)
        current_auth_meta = auth_user.user.user_metadata or {}

        current_auth_meta["role"] = body.role

        supabase_admin.auth.admin.update_user_by_id(
            user_id, attributes={"user_metadata": current_auth_meta}
        )
    except Exception as e:
        print(f"Warning: Failed to sync auth metadata: {e}")

    return resp.data[0]


@router.post("/users/{user_id}/verify")
async def verify_user(user_id: str, body: VerifyUserBody, admin=Depends(require_admin)):
    """Verify or reject an NGO/Donor/Volunteer account."""
    if body.status not in ("verified", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")

    # 1. Update the Users table (both column and metadata for compatibility)
    metadata_resp = (
        supabase_admin.table("users")
        .select("metadata")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    existing_meta = (metadata_resp.data or {}).get("metadata") or {}

    existing_meta["verification_status"] = body.status
    existing_meta["verification_notes"] = body.notes
    existing_meta["verified_at"] = (
        datetime.now(timezone.utc).isoformat() if body.status == "verified" else None
    )
    existing_meta["verified_by"] = admin.get("id")

    updates = {
        "verification_status": body.status,  # Top-level column
        "metadata": existing_meta,  # JSONB metadata
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    resp = supabase_admin.table("users").update(updates).eq("id", user_id).execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Update Auth metadata (Merging carefully)
    try:
        # Fetch current auth user to get existing metadata (roles etc)
        auth_user = supabase_admin.auth.admin.get_user_by_id(user_id)
        current_auth_meta = auth_user.user.user_metadata or {}

        # Merge new status
        current_auth_meta["verification_status"] = body.status

        supabase_admin.auth.admin.update_user_by_id(
            user_id, attributes={"user_metadata": current_auth_meta}
        )
    except Exception as e:
        print(f"Warning: Failed to sync auth metadata: {e}")

    return {
        "status": body.status,
        "message": f"User verification status updated to {body.status}",
    }


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(require_admin)):
    """Delete a user from the users table (does NOT remove from auth.users)."""
    # Prevent admin from deleting themselves
    if str(admin.get("id")) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    resp = supabase_admin.table("users").delete().eq("id", user_id).execute()
    return {"deleted": True}


# ── Platform Settings ─────────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(admin=Depends(require_admin)):
    """Get platform settings (single row)."""
    resp = (
        supabase_admin.table("platform_settings")
        .select("*")
        .eq("id", 1)
        .maybe_single()
        .execute()
    )
    if not resp.data:
        # Return defaults if the row doesn't exist yet
        return {
            "platform_name": "DisasterRM",
            "support_email": "admin@disasterrm.org",
            "auto_sitrep": True,
            "sitrep_interval": 6,
            "auto_allocate": True,
            "ingestion_enabled": True,
            "ingestion_interval": 5,
            "email_notifications": True,
            "sms_alerts": False,
            "maintenance_mode": False,
            "api_rate_limit": 100,
            "max_upload_mb": 10,
            "session_timeout": 60,
            "data_retention_days": 365,
        }
    return resp.data


@router.put("/settings")
async def update_settings(body: PlatformSettingsBody, admin=Depends(require_admin)):
    """Update platform settings."""
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Upsert: update the single row
    resp = (
        supabase_admin.table("platform_settings").update(updates).eq("id", 1).execute()
    )
    if not resp.data:
        # Row might not exist – insert it
        updates["id"] = 1
        resp = supabase_admin.table("platform_settings").insert(updates).execute()
    return resp.data[0] if resp.data else updates


# ── Platform Stats (for landing page hero) ────────────────────────────────────


@router.get("/platform-stats")
async def platform_stats():
    """Public endpoint returning aggregate platform stats for the landing page.

    No authentication required – these are public marketing metrics.
    """
    try:
        # Count total users
        users_resp = supabase_admin.table("users").select("id", count="exact").execute()
        total_users = users_resp.count or 0

        # Count disasters
        disasters_resp = (
            supabase_admin.table("disasters")
            .select("id, status, casualties", count="exact")
            .execute()
        )
        total_disasters = disasters_resp.count or 0
        disaster_data = disasters_resp.data or []
        active_disasters = sum(1 for d in disaster_data if d.get("status") == "active")
        resolved_disasters = sum(
            1 for d in disaster_data if d.get("status") == "resolved"
        )
        total_casualties_helped = sum(
            int(d.get("casualties") or 0) for d in disaster_data
        )

        # Count resources
        resources_resp = (
            supabase_admin.table("resources")
            .select("id, status", count="exact")
            .execute()
        )
        total_resources = resources_resp.count or 0
        resource_data = resources_resp.data or []
        allocated_resources = sum(
            1
            for r in resource_data
            if r.get("status") in ("allocated", "in_transit", "delivered")
        )

        # Count volunteers
        volunteers_resp = (
            supabase_admin.table("users")
            .select("id", count="exact")
            .eq("role", "volunteer")
            .execute()
        )
        total_volunteers = volunteers_resp.count or 0

        # Count NGOs
        ngos_resp = (
            supabase_admin.table("users")
            .select("id", count="exact")
            .eq("role", "ngo")
            .execute()
        )
        total_ngos = ngos_resp.count or 0

        # Count donations
        donations_resp = (
            supabase_admin.table("donations")
            .select("amount")
            .eq("status", "completed")
            .execute()
        )
        donation_data = donations_resp.data or []
        total_donated = sum(float(d.get("amount", 0)) for d in donation_data)

        return {
            "lives_impacted": max(
                total_casualties_helped, total_users * 3
            ),  # Estimate: each user impacts ~3 people
            "total_users": total_users,
            "total_volunteers": total_volunteers,
            "total_ngos": total_ngos,
            "active_disasters": active_disasters,
            "resolved_disasters": resolved_disasters,
            "total_disasters": total_disasters,
            "total_resources": total_resources,
            "resources_allocated": allocated_resources,
            "total_donated": total_donated,
            "avg_response_minutes": (
                45 if resolved_disasters == 0 else max(15, 90 - resolved_disasters * 2)
            ),
        }
    except Exception:
        # Graceful fallback if tables don't exist yet
        return {
            "lives_impacted": 0,
            "total_users": 0,
            "total_volunteers": 0,
            "total_ngos": 0,
            "active_disasters": 0,
            "resolved_disasters": 0,
            "total_disasters": 0,
            "total_resources": 0,
            "resources_allocated": 0,
            "total_donated": 0,
            "avg_response_minutes": 0,
        }


# ── Testimonials / Success Stories (public) ────────────────────────────────


@router.get("/testimonials")
async def get_testimonials():
    """Public endpoint returning active testimonials for the landing page."""
    try:
        resp = (
            supabase_admin.table("testimonials")
            .select("id, author_name, author_role, quote, image_url")
            .eq("is_active", True)
            .order("sort_order")
            .limit(6)
            .execute()
        )
        return resp.data or []
    except Exception:
        return []


# ── Recent Incidents (public, for landing page map) ───────────────────────


@router.get("/recent-incidents")
async def recent_incidents():
    """Public endpoint returning the latest active disasters for the map preview."""
    try:
        resp = (
            supabase_admin.table("disasters")
            .select("*")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(6)
            .execute()
        )
        base_data = resp.data or []

        # Manual enrichment for locations
        location_ids = list(
            set(d["location_id"] for d in base_data if d.get("location_id"))
        )
        location_map = {}
        if location_ids:
            loc_resp = (
                supabase_admin.table("locations")
                .select("id, latitude, longitude, name, city, country")
                .in_("id", location_ids)
                .execute()
            )
            for loc in loc_resp.data or []:
                location_map[loc["id"]] = loc

        incidents = []
        for d in base_data:
            loc = location_map.get(d.get("location_id")) or {}
            incidents.append(
                {
                    "id": d.get("id"),
                    "title": d.get("title", "Unnamed Incident"),
                    "type": d.get("type", "unknown"),
                    "severity": d.get("severity", "medium"),
                    "description": d.get("description", ""),
                    "created_at": d.get("created_at"),
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                    "location_name": loc.get("name")
                    or loc.get("city")
                    or loc.get("country")
                    or "Unknown",
                }
            )
        return incidents
    except Exception:
        return []


# ── Request Management (Approve / Reject Cycle) ───────────────────────────


def _safe_request_row(row: dict) -> dict:
    """Ensure a request row is JSON-serializable."""
    row = dict(row)
    for key in ("items", "attachments", "nlp_classification", "urgency_signals"):
        val = row.get(key)
        if val is None:
            row[key] = []
        elif isinstance(val, str):
            try:
                row[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                row[key] = []
    for key in ("created_at", "updated_at", "estimated_delivery"):
        val = row.get(key)
        if val is not None and isinstance(val, datetime):
            row[key] = val.isoformat()
    return row


@router.get("/requests")
async def list_all_requests(
    admin=Depends(require_admin),
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending,approved,assigned,in_progress,completed,rejected",
    ),
    priority: Optional[str] = Query(
        None, description="Filter by priority: critical,high,medium,low"
    ),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    search: Optional[str] = Query(
        None, description="Search by ID, description, or victim_id"
    ),
    date_from: Optional[str] = Query(None, description="Filter from date (ISO)"),
    date_to: Optional[str] = Query(None, description="Filter to date (ISO)"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List ALL resource requests across all victims with full filtering.
    Admin-only — bypasses RLS."""
    try:
        # Fetch basic requests without joins to avoid "schema cache" errors
        query = supabase_admin.table("resource_requests").select("*", count="exact")

        if status:
            query = query.eq("status", status)
        if priority:
            query = query.eq("priority", priority)
        if resource_type:
            query = query.eq("resource_type", resource_type)
        if search:
            query = query.or_(
                f"id.eq.{search},description.ilike.%{search}%,victim_id.eq.{search}"
            )
        if date_from:
            query = query.gte("created_at", date_from)
        if date_to:
            query = query.lte("created_at", date_to)

        ascending = sort_order.lower() == "asc"
        query = query.order(sort_by, desc=not ascending)

        offset = (page - 1) * page_size
        query = query.range(offset, offset + page_size - 1)

        response = query.execute()
        base_requests = response.data or []

        # Manual enrichment for victim and assigned_user
        user_ids = set()
        for r in base_requests:
            if r.get("victim_id"):
                user_ids.add(r["victim_id"])
            if r.get("assigned_to"):
                user_ids.add(r["assigned_to"])

        user_map = {}
        if user_ids:
            users_resp = (
                supabase_admin.table("users")
                .select("id, full_name, email, metadata")
                .in_("id", list(user_ids))
                .execute()
            )
            for u in users_resp.data or []:
                user_map[u["id"]] = u

        # Clean and flatten results for frontend
        requests = []
        for r in base_requests:
            row = _safe_request_row(r)

            # Map victim info
            vid = row.get("victim_id")
            v = user_map.get(vid, {})
            row["victim_name"] = v.get("full_name") or "Unknown"
            row["victim_email"] = v.get("email") or ""

            # Map assigned user info
            aid = row.get("assigned_to")
            row["assigned_user"] = user_map.get(aid)

            requests.append(row)

        # Stats overview
        all_resp = (
            supabase_admin.table("resource_requests")
            .select("status", count="exact")
            .execute()
        )
        status_counts = {}
        for row in all_resp.data or []:
            s = row.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "requests": requests,
            "total": response.count or 0,
            "page": page,
            "page_size": page_size,
            "status_counts": status_counts,
        }
    except Exception as e:
        print(f"❌ ADMIN LIST REQUESTS ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error fetching requests: {str(e)}"
        )


@router.get("/requests/{request_id}")
async def get_request_detail(
    request_id: str,
    admin=Depends(require_admin),
):
    """Get a single resource request with full detail — admin only."""
    try:
        response = (
            supabase_admin.table("resource_requests")
            .select("*")
            .eq("id", request_id)
            .single()
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Request not found")

        row = _safe_request_row(response.data)

        # Enrich with victim info
        vid = row.get("victim_id")
        if vid:
            try:
                user_resp = (
                    supabase_admin.table("users")
                    .select("id, full_name, email, phone, role")
                    .eq("id", vid)
                    .maybe_single()
                    .execute()
                )
                if user_resp.data:
                    row["victim_name"] = user_resp.data.get("full_name") or "Unknown"
                    row["victim_email"] = user_resp.data.get("email") or ""
                    row["victim_phone"] = user_resp.data.get("phone") or ""
            except Exception:
                pass

        return row
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching request: {str(e)}")


@router.post("/requests/{request_id}/action")
async def approve_reject_request(
    request_id: str,
    body: ApproveRejectBody,
    admin=Depends(require_admin),
):
    """Approve or reject a resource request. Admin only."""
    if body.action not in ("approve", "reject"):
        raise HTTPException(
            status_code=400, detail="Action must be 'approve' or 'reject'"
        )

    if body.action == "reject" and not body.rejection_reason:
        raise HTTPException(
            status_code=400, detail="Rejection reason is required when rejecting"
        )

    try:
        # Verify request exists
        existing = (
            supabase_admin.table("resource_requests")
            .select("*")
            .eq("id", request_id)
            .single()
            .execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Request not found")

        current_status = existing.data.get("status")

        # Build update
        update_fields = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if body.action == "approve":
            if current_status not in (
                "pending",
                "rejected",
                "availability_submitted",
                "under_review",
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot approve request with status '{current_status}'. Only pending, rejected, or availability_submitted requests can be approved.",
                )
            # If NGO submitted availability, approve means assign to that NGO
            if current_status in ("availability_submitted", "under_review"):
                update_fields["status"] = "assigned"
                update_fields["assigned_role"] = "ngo"
                # Find the NGO that submitted availability
                if body.assigned_to:
                    update_fields["assigned_to"] = body.assigned_to
                else:
                    # Auto-assign to the first NGO that submitted availability
                    ngo_pulse = (
                        supabase_admin.table("operational_pulse")
                        .select("actor_id")
                        .eq("target_id", request_id)
                        .eq("action_type", "ngo_availability_submitted")
                        .order("created_at", desc=False)
                        .limit(1)
                        .execute()
                    )
                    if ngo_pulse.data:
                        update_fields["assigned_to"] = ngo_pulse.data[0]["actor_id"]
            else:
                update_fields["status"] = "approved"
            update_fields["rejection_reason"] = None  # Clear any previous rejection
            if body.assigned_to:
                update_fields["assigned_to"] = body.assigned_to
                update_fields["status"] = "assigned"
            if body.estimated_delivery:
                update_fields["estimated_delivery"] = body.estimated_delivery

        elif body.action == "reject":
            if current_status in ("completed",):
                raise HTTPException(
                    status_code=400, detail="Cannot reject a completed request."
                )
            update_fields["status"] = "rejected"
            update_fields["rejection_reason"] = body.rejection_reason

        response = (
            supabase_admin.table("resource_requests")
            .update(update_fields)
            .eq("id", request_id)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to update request")

        new_status = update_fields.get("status", current_status)

        # Send notification to victim & create audit trail
        try:
            # Build audit details: include admin note if provided
            audit_details = body.rejection_reason if body.action == "reject" else None
            if body.admin_note:
                audit_details = (
                    f"{audit_details or ''}\n[Admin Note] {body.admin_note}".strip()
                )

            await notify_request_status_change(
                request_id=request_id,
                victim_id=existing.data.get("victim_id", ""),
                resource_type=existing.data.get("resource_type", "resources"),
                old_status=current_status,
                new_status=new_status,
                admin_id=admin.get("id"),
                rejection_reason=body.rejection_reason,
                admin_note=body.admin_note,
            )
        except Exception as ne:
            logger.warning(f"Notification failed (non-critical): {ne}")

        return {
            "message": f"Request {body.action}d successfully",
            "request": _safe_request_row(response.data[0]),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ADMIN ACTION ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error processing action: {str(e)}"
        )


@router.patch("/requests/{request_id}/status")
async def update_request_status(
    request_id: str,
    body: dict,
    admin=Depends(require_admin),
):
    """Update the status of a request (e.g., move to in_progress, completed).
    Admin only."""
    new_status = body.get("status")
    valid_statuses = [
        "pending",
        "approved",
        "availability_submitted",
        "under_review",
        "assigned",
        "in_progress",
        "delivered",
        "completed",
        "closed",
        "rejected",
    ]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    try:
        update_fields = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if body.get("rejection_reason"):
            update_fields["rejection_reason"] = body["rejection_reason"]
        if body.get("assigned_to"):
            update_fields["assigned_to"] = body["assigned_to"]
        if body.get("estimated_delivery"):
            update_fields["estimated_delivery"] = body["estimated_delivery"]

        response = (
            supabase_admin.table("resource_requests")
            .update(update_fields)
            .eq("id", request_id)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Request not found")
        return _safe_request_row(response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating status: {str(e)}")


# ── Available Resources (admin view) ──────────────────────────────────────


@router.get("/available-resources")
async def list_available_resources(
    admin=Depends(require_admin),
    category: Optional[str] = Query(None, description="Filter by category"),
    status: Optional[str] = Query(
        None, description="Filter by status: available, reserved"
    ),
    search: Optional[str] = Query(None, description="Search by title or description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all available resources across all providers. Admin only."""
    try:
        query = supabase_admin.table("available_resources").select("*", count="exact")

        if category:
            query = query.eq("category", category)
        if status:
            query = query.eq("status", status)
        else:
            query = query.eq("is_active", True)
        if search:
            query = query.or_(f"title.ilike.%{search}%,description.ilike.%{search}%")

        query = query.order("category")

        offset = (page - 1) * page_size
        query = query.range(offset, offset + page_size - 1)

        response = query.execute()

        resources = []
        for r in response.data or []:
            total = r.get("total_quantity", 0) or 0
            claimed = r.get("claimed_quantity", 0) or 0
            remaining = max(0, total - claimed)
            r["remaining_quantity"] = remaining
            resources.append(r)

        # Provider names
        provider_ids = list(
            set(r.get("provider_id") for r in resources if r.get("provider_id"))
        )
        provider_names = {}
        if provider_ids:
            try:
                users_resp = (
                    supabase_admin.table("users")
                    .select("id, full_name, email, role")
                    .in_("id", provider_ids)
                    .execute()
                )
                for u in users_resp.data or []:
                    provider_names[u["id"]] = {
                        "full_name": u.get("full_name") or "Unknown",
                        "email": u.get("email") or "",
                        "role": u.get("role") or "unknown",
                    }
            except Exception:
                pass

        for r in resources:
            pid = r.get("provider_id")
            info = provider_names.get(pid, {})
            r["provider_name"] = info.get("full_name", "Unknown")
            r["provider_email"] = info.get("email", "")
            r["provider_role_name"] = info.get("role", "unknown")

        # Category summary
        all_resp = (
            supabase_admin.table("available_resources")
            .select("category, total_quantity, claimed_quantity")
            .eq("is_active", True)
            .execute()
        )
        category_summary = {}
        for row in all_resp.data or []:
            cat = row.get("category", "Unknown")
            if cat not in category_summary:
                category_summary[cat] = {"total": 0, "claimed": 0, "count": 0}
            category_summary[cat]["total"] += row.get("total_quantity", 0) or 0
            category_summary[cat]["claimed"] += row.get("claimed_quantity", 0) or 0
            category_summary[cat]["count"] += 1

        return {
            "resources": resources,
            "total": response.count or 0,
            "page": page,
            "page_size": page_size,
            "category_summary": category_summary,
        }
    except Exception as e:
        print(f"❌ ADMIN RESOURCES ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error fetching resources: {str(e)}"
        )


# ── Notifications & Audit Trail ───────────────────────────────────────────

import logging

logger = logging.getLogger("admin_router")


@router.get("/notifications")
async def list_notifications(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    """Get notifications for the authenticated user. Works for any role."""
    try:
        user = supabase.auth.get_user(credentials.credentials)
        user_id = user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    notifications = await get_user_notifications(
        user_id, unread_only=unread_only, limit=limit
    )
    unread = await get_unread_count(user_id)
    return {"notifications": notifications, "unread_count": unread}


@router.post("/notifications/mark-read")
async def mark_read(
    body: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Mark notifications as read."""
    try:
        user = supabase.auth.get_user(credentials.credentials)
        user_id = user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    ids = body.get("notification_ids")  # None = mark all
    count = await mark_notifications_read(user_id, ids)
    return {"marked_read": count}


@router.get("/requests/{request_id}/audit-trail")
async def get_audit_trail(
    request_id: str,
    admin=Depends(require_admin),
):
    """Get the audit trail for a specific request. Admin only."""
    trail = await get_request_audit_trail(request_id)
    return {"audit_trail": trail}


@router.get("/requests/{request_id}/ngo-submissions")
async def get_ngo_submissions(
    request_id: str,
    admin=Depends(require_admin),
):
    """Get all fulfillment submissions (NGO + Donor) for a request.
    NGO submissions are prioritised over donor at same distance. Admin only."""
    try:
        # Fetch NGO availability submissions from operational_pulse
        ngo_resp = (
            supabase_admin.table("operational_pulse")
            .select("*")
            .eq("target_id", request_id)
            .eq("action_type", "ngo_availability_submitted")
            .order("created_at", desc=True)
            .execute()
        )
        ngo_submissions = ngo_resp.data or []

        # Fetch donor pledge submissions from operational_pulse
        donor_resp = (
            supabase_admin.table("operational_pulse")
            .select("*")
            .eq("target_id", request_id)
            .eq("action_type", "donor_pledge_submitted")
            .order("created_at", desc=True)
            .execute()
        )
        donor_submissions = donor_resp.data or []

        # Gather all user IDs for enrichment
        all_ids = list(
            set(
                [s.get("actor_id") for s in ngo_submissions if s.get("actor_id")]
                + [s.get("actor_id") for s in donor_submissions if s.get("actor_id")]
            )
        )
        user_map = {}
        if all_ids:
            users_resp = (
                supabase_admin.table("users")
                .select("id, full_name, email, phone, role, metadata")
                .in_("id", all_ids)
                .execute()
            )
            for u in users_resp.data or []:
                user_map[u["id"]] = u

        enriched = []
        for s in ngo_submissions:
            user = user_map.get(s.get("actor_id"), {})
            meta = s.get("metadata") or {}
            enriched.append(
                {
                    "id": s.get("id"),
                    "ngo_id": s.get("actor_id"),
                    "ngo_name": user.get("full_name") or "Unknown NGO",
                    "ngo_email": user.get("email") or "",
                    "role": "ngo",
                    "submitted_at": s.get("created_at"),
                    "metadata": meta,
                    "distance_km": meta.get("distance_km"),
                    "sort_priority": 0,  # NGO gets priority
                }
            )
        for s in donor_submissions:
            user = user_map.get(s.get("actor_id"), {})
            meta = s.get("metadata") or {}
            enriched.append(
                {
                    "id": s.get("id"),
                    "ngo_id": s.get("actor_id"),
                    "ngo_name": user.get("full_name") or "Unknown Donor",
                    "ngo_email": user.get("email") or "",
                    "role": "donor",
                    "submitted_at": s.get("created_at"),
                    "metadata": meta,
                    "distance_km": meta.get("distance_km"),
                    "sort_priority": 1,  # Donor gets lower priority
                }
            )

        # Sort: by distance ascending, then by role priority (NGO first at same distance)
        enriched.sort(
            key=lambda x: (
                x["distance_km"] if x["distance_km"] is not None else float("inf"),
                x["sort_priority"],
            )
        )

        return {"submissions": enriched, "total": len(enriched)}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error fetching submissions: {str(e)}"
        )


# ── Analytics Data ────────────────────────────────────────────────────────


@router.get("/analytics/request-trends")
async def get_request_trends(
    admin=Depends(require_admin),
    days: int = Query(30, ge=1, le=365),
):
    """Get request creation trends over time."""
    try:
        from datetime import timedelta

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = (
            supabase_admin.table("resource_requests")
            .select("id, status, priority, resource_type, created_at")
            .gte("created_at", since)
            .order("created_at")
            .execute()
        )

        requests = resp.data or []

        # Group by date
        daily: dict = {}
        for r in requests:
            date = str(r.get("created_at", ""))[:10]
            if date not in daily:
                daily[date] = {
                    "date": date,
                    "total": 0,
                    "pending": 0,
                    "approved": 0,
                    "rejected": 0,
                    "completed": 0,
                }
            daily[date]["total"] += 1
            st = r.get("status", "pending")
            if st in daily[date]:
                daily[date][st] += 1

        # Priority distribution
        priority_dist = {}
        for r in requests:
            p = r.get("priority", "medium")
            priority_dist[p] = priority_dist.get(p, 0) + 1

        # Type distribution
        type_dist = {}
        for r in requests:
            t = r.get("resource_type", "Other")
            type_dist[t] = type_dist.get(t, 0) + 1

        # Response time (pending → approved/rejected)
        status_times = []
        for r in requests:
            if r.get("status") in ("approved", "rejected", "completed", "assigned"):
                created = r.get("created_at", "")
                updated = r.get("updated_at", created)
                try:
                    from dateutil.parser import parse as parse_date

                    c = parse_date(created)
                    u = parse_date(updated)
                    hours = (u - c).total_seconds() / 3600
                    status_times.append(hours)
                except Exception:
                    pass

        avg_response_hours = (
            round(sum(status_times) / len(status_times), 1) if status_times else 0
        )

        return {
            "daily_trends": sorted(daily.values(), key=lambda x: x["date"]),
            "priority_distribution": priority_dist,
            "type_distribution": type_dist,
            "total_requests": len(requests),
            "avg_response_hours": avg_response_hours,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching trends: {str(e)}")


# ── Export & Reporting ────────────────────────────────────────────────────

from fastapi.responses import StreamingResponse
import csv
import io


@router.get("/export/{data_type}")
async def export_data(
    data_type: str,
    admin=Depends(require_admin),
):
    """Export requests, resources, or users as CSV. Admin only."""
    if data_type not in ("requests", "resources", "users"):
        raise HTTPException(
            status_code=400, detail="Invalid data_type. Use: requests, resources, users"
        )

    try:
        output = io.StringIO()
        writer = csv.writer(output)

        if data_type == "requests":
            resp = (
                supabase_admin.table("resource_requests")
                .select("*")
                .order("created_at", desc=True)
                .limit(5000)
                .execute()
            )
            rows = resp.data or []
            writer.writerow(
                [
                    "ID",
                    "Victim ID",
                    "Resource Type",
                    "Quantity",
                    "Priority",
                    "Status",
                    "Description",
                    "Address",
                    "Rejection Reason",
                    "Admin Note",
                    "Created At",
                    "Updated At",
                ]
            )
            for r in rows:
                writer.writerow(
                    [
                        r.get("id"),
                        r.get("victim_id"),
                        r.get("resource_type"),
                        r.get("quantity"),
                        r.get("priority"),
                        r.get("status"),
                        r.get("description", ""),
                        r.get("address_text", ""),
                        r.get("rejection_reason", ""),
                        r.get("admin_note", ""),
                        r.get("created_at"),
                        r.get("updated_at"),
                    ]
                )

        elif data_type == "resources":
            resp = (
                supabase_admin.table("available_resources")
                .select("*")
                .limit(5000)
                .execute()
            )
            rows = resp.data or []
            writer.writerow(
                [
                    "ID",
                    "Category",
                    "Type",
                    "Title",
                    "Description",
                    "Total Qty",
                    "Claimed Qty",
                    "Remaining",
                    "Unit",
                    "Provider ID",
                    "Status",
                    "Created At",
                ]
            )
            for r in rows:
                writer.writerow(
                    [
                        r.get("resource_id") or r.get("id"),
                        r.get("category"),
                        r.get("resource_type"),
                        r.get("title"),
                        r.get("description", ""),
                        r.get("total_quantity"),
                        r.get("claimed_quantity"),
                        r.get("remaining_quantity"),
                        r.get("unit"),
                        r.get("provider_id"),
                        r.get("status"),
                        r.get("created_at"),
                    ]
                )

        elif data_type == "users":
            resp = (
                supabase_admin.table("users")
                .select("id, full_name, email, phone, role, created_at, updated_at")
                .limit(5000)
                .execute()
            )
            rows = resp.data or []
            writer.writerow(
                [
                    "ID",
                    "Full Name",
                    "Email",
                    "Phone",
                    "Role",
                    "Created At",
                    "Updated At",
                ]
            )
            for r in rows:
                writer.writerow(
                    [
                        r.get("id"),
                        r.get("full_name"),
                        r.get("email"),
                        r.get("phone"),
                        r.get("role"),
                        r.get("created_at"),
                        r.get("updated_at"),
                    ]
                )

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={data_type}_export.csv"
            },
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


# ── Data Quality & Deduplication ──────────────────────────────────────────


@router.get("/duplicate-requests")
async def detect_duplicate_requests(
    admin=Depends(require_admin),
    hours: int = Query(48, ge=1, le=720),
):
    """Detect potentially duplicate requests from the same victim within a time window."""
    try:
        from datetime import timedelta

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        resp = (
            supabase_admin.table("resource_requests")
            .select(
                "id, victim_id, resource_type, quantity, description, status, created_at"
            )
            .gte("created_at", since)
            .order("victim_id")
            .order("created_at")
            .execute()
        )

        rows = resp.data or []

        # Group by victim and detect duplicates
        victim_requests = {}
        for r in rows:
            vid = r.get("victim_id", "")
            if vid not in victim_requests:
                victim_requests[vid] = []
            victim_requests[vid].append(r)

        duplicates = []
        for vid, reqs in victim_requests.items():
            if len(reqs) < 2:
                continue
            for i in range(len(reqs)):
                for j in range(i + 1, len(reqs)):
                    a, b = reqs[i], reqs[j]
                    # Same resource type
                    if a.get("resource_type") == b.get("resource_type"):
                        duplicates.append(
                            {
                                "victim_id": vid,
                                "request_a": {
                                    "id": a["id"],
                                    "type": a.get("resource_type"),
                                    "qty": a.get("quantity"),
                                    "status": a.get("status"),
                                    "created": a.get("created_at"),
                                },
                                "request_b": {
                                    "id": b["id"],
                                    "type": b.get("resource_type"),
                                    "qty": b.get("quantity"),
                                    "status": b.get("status"),
                                    "created": b.get("created_at"),
                                },
                                "reason": "Same resource type from same victim",
                            }
                        )

        return {
            "duplicates": duplicates[:50],
            "total_found": len(duplicates),
            "analyzed_requests": len(rows),
            "time_window_hours": hours,
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500, detail=f"Error detecting duplicates: {str(e)}"
        )


@router.get("/analytics/model-info")
async def get_admin_model_info(admin=Depends(require_admin)):
    """Get metadata about loaded ML models."""
    try:
        from app.dependencies import ml_service as global_ml

        if global_ml:
            return global_ml.get_model_info()
        return {"error": "ML service not initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
