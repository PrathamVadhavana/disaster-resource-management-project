"""
Admin-only endpoints for user management, platform settings, platform stats,
request management (approve/reject), and available resources.

All endpoints verify the caller is an admin by checking their role
in the ``users`` table. The ``db_admin`` client (service-role key)
is used so that Row-Level-Security is bypassed.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import json
import logging
import traceback

logger = logging.getLogger("admin_router")

from app.database import db, db_admin
from app.dependencies import _verify_supabase_token
from app.services.notification_service import (
    notify_request_status_change,
    get_user_notifications,
    mark_notifications_read,
    get_unread_count,
    get_request_audit_trail,
    create_audit_entry,
    notify_all_by_role,
    notify_user,
)
from app.dependencies import require_admin

from app.services.event_sourcing_service import (
    emit_request_status_changed,
    emit_request_assigned,
)

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
    assigned_role: Optional[str] = Field(
        None, description="Role of the assignee: 'ngo' or 'donor'. Auto-detected if omitted."
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
        await db_admin.table("users")
        .select("*")
        .order("created_at", desc=True)
        .limit(500)
        .async_execute()
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
        await db_admin.table("users")
        .select("metadata")
        .eq("id", user_id)
        .maybe_single()
        .async_execute()
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

    resp = await db_admin.table("users").update(updates).eq("id", user_id).async_execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    # Also update Supabase auth metadata to keep role in sync
    try:
        from app.db_client import get_supabase_client
        sb = get_supabase_client()
        sb.auth.admin.update_user_by_id(user_id, {"app_metadata": {"role": body.role}})
    except Exception as e:
        print(f"Warning: Failed to sync Supabase auth metadata: {e}")

    return resp.data[0]


@router.post("/users/{user_id}/verify")
async def verify_user(user_id: str, body: VerifyUserBody, admin=Depends(require_admin)):
    """Verify or reject an NGO/Donor/Volunteer account."""
    logger.info("verify_user called: user_id=%s status=%s by admin=%s", user_id, body.status, admin.get("id"))

    if body.status not in ("verified", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")

    try:
        # 1. Update the Users table (both column and metadata for compatibility)
        metadata_resp = (
            await db_admin.table("users")
            .select("metadata")
            .eq("id", user_id)
            .maybe_single()
            .async_execute()
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

        logger.info("Updating user %s with verification_status=%s", user_id, body.status)
        resp = await db_admin.table("users").update(updates).eq("id", user_id).async_execute()
        if not resp.data:
            logger.error("User %s not found during verification update", user_id)
            raise HTTPException(status_code=404, detail="User not found")

        logger.info("User %s verification updated successfully in DB", user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update user %s verification in DB: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")

    # 2. Update Supabase auth metadata with verification status
    try:
        from app.db_client import get_supabase_client
        sb = get_supabase_client()
        sb.auth.admin.update_user_by_id(user_id, {
            "app_metadata": {"verification_status": body.status},
        })
        logger.info("Supabase auth metadata updated for user %s", user_id)
    except Exception as e:
        logger.warning("Failed to sync Supabase auth metadata for user %s: %s", user_id, e)

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

    resp = await db_admin.table("users").delete().eq("id", user_id).async_execute()
    return {"deleted": True}


# ── Platform Settings ─────────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(admin=Depends(require_admin)):
    """Get platform settings (single row)."""
    resp = (
        await db_admin.table("platform_settings")
        .select("*")
        .eq("id", 1)
        .maybe_single()
        .async_execute()
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
        await db_admin.table("platform_settings").update(updates).eq("id", 1).async_execute()
    )
    if not resp.data:
        # Row might not exist – insert it
        updates["id"] = 1
        resp = await db_admin.table("platform_settings").insert(updates).async_execute()
    return resp.data[0] if resp.data else updates


# ── Platform Stats (for landing page hero) ────────────────────────────────────


@router.get("/platform-stats")
async def platform_stats():
    """Public endpoint returning aggregate platform stats for the landing page.

    No authentication required – these are public marketing metrics.
    Cached for 5 minutes to minimize database reads.
    """
    from app.core.query_cache import (
        cache_get as mem_cache_get,
        cache_set as mem_cache_set,
        TTL_MEDIUM,
    )

    _cache_key = "admin:platform_stats"
    cached = mem_cache_get(_cache_key)
    if cached is not None:
        return cached

    try:
        # Count total users
        users_resp = await db_admin.table("users").select("id", count="exact").limit(5000).async_execute()
        total_users = users_resp.count or 0

        # Count disasters
        disasters_resp = (
            await db_admin.table("disasters")
            .select("id, status, casualties", count="exact")
            .limit(5000)
            .async_execute()
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
            await db_admin.table("resources")
            .select("id, status", count="exact")
            .limit(5000)
            .async_execute()
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
            await db_admin.table("users")
            .select("id", count="exact")
            .eq("role", "volunteer")
            .limit(5000)
            .async_execute()
        )
        total_volunteers = volunteers_resp.count or 0

        # Count NGOs
        ngos_resp = (
            await db_admin.table("users")
            .select("id", count="exact")
            .eq("role", "ngo")
            .limit(5000)
            .async_execute()
        )
        total_ngos = ngos_resp.count or 0

        # Count donations
        donations_resp = (
            await db_admin.table("donations")
            .select("amount")
            .eq("status", "completed")
            .limit(5000)
            .async_execute()
        )
        donation_data = donations_resp.data or []
        total_donated = sum(float(d.get("amount", 0)) for d in donation_data)

        result = {
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

        mem_cache_set(_cache_key, result, TTL_MEDIUM)
        return result
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
            await db_admin.table("testimonials")
            .select("id, author_name, author_role, quote, image_url")
            .eq("is_active", True)
            .order("sort_order")
            .limit(6)
            .async_execute()
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
            await db_admin.table("disasters")
            .select("*")
            .eq("status", "active")
            .order("created_at", desc=True)
            .limit(6)
            .async_execute()
        )
        base_data = resp.data or []

        # Manual enrichment for locations
        location_ids = list(
            set(d["location_id"] for d in base_data if d.get("location_id"))
        )
        location_map = {}
        if location_ids:
            loc_resp = (
                await db_admin.table("locations")
                .select("id, latitude, longitude, name, city, country")
                .in_("id", location_ids)
                .async_execute()
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
        query = db_admin.table("resource_requests").select("*", count="exact")

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

        response = await query.async_execute()
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
                await db_admin.table("users")
                .select("id, full_name, email, metadata")
                .in_("id", list(user_ids))
                .async_execute()
            )
            for u in users_resp.data or []:
                user_map[u["id"]] = u

        # Also collect provider IDs from fulfillment_entries for multi-contributor display
        fe_user_ids = set()
        for r in base_requests:
            for entry in (r.get("fulfillment_entries") or []):
                pid = entry.get("provider_id")
                if pid and pid not in user_ids:
                    fe_user_ids.add(pid)

        if fe_user_ids:
            fe_resp = (
                await db_admin.table("users")
                .select("id, full_name, email, metadata")
                .in_("id", list(fe_user_ids))
                .async_execute()
            )
            for u in fe_resp.data or []:
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

            # Build assigned_users list from fulfillment_entries (multi-contributor)
            contributors = []
            seen_ids = set()
            for entry in (row.get("fulfillment_entries") or []):
                pid = entry.get("provider_id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    u_info = user_map.get(pid, {})
                    contributors.append({
                        "id": pid,
                        "full_name": entry.get("provider_name") or u_info.get("full_name") or "Unknown",
                        "role": entry.get("provider_role") or "unknown",
                    })
            row["assigned_users"] = contributors

            requests.append(row)

        # Stats overview
        all_resp = (
            await db_admin.table("resource_requests")
            .select("status", count="exact")
            .limit(5000)
            .async_execute()
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
            await db_admin.table("resource_requests")
            .select("*")
            .eq("id", request_id)
            .single()
            .async_execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Request not found")

        row = _safe_request_row(response.data)

        # Enrich with victim info
        vid = row.get("victim_id")
        if vid:
            try:
                user_resp = (
                    await db_admin.table("users")
                    .select("id, full_name, email, phone, role")
                    .eq("id", vid)
                    .maybe_single()
                    .async_execute()
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
            await db_admin.table("resource_requests")
            .select("*")
            .eq("id", request_id)
            .single()
            .async_execute()
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
                    detail=f"Cannot approve request with status '{current_status}'. Only pending, rejected, under_review, or availability_submitted requests can be approved.",
                )
            # If NGO submitted availability, approve means assign to that NGO
            if current_status in ("availability_submitted", "under_review"):
                update_fields["status"] = "assigned"
                # Find the NGO that submitted availability
                if body.assigned_to:
                    update_fields["assigned_to"] = body.assigned_to
                    # Detect role of the assignee dynamically
                    if body.assigned_role:
                        update_fields["assigned_role"] = body.assigned_role
                    else:
                        try:
                            assignee = (
                                await db_admin.table("users")
                                .select("role")
                                .eq("id", body.assigned_to)
                                .maybe_single()
                                .async_execute()
                            )
                            update_fields["assigned_role"] = (assignee.data or {}).get("role", "ngo")
                        except Exception:
                            update_fields["assigned_role"] = "ngo"
                else:
                    # Auto-assign to the first NGO that submitted availability
                    ngo_pulse = (
                        await db_admin.table("operational_pulse")
                        .select("actor_id")
                        .eq("target_id", request_id)
                        .eq("action_type", "ngo_availability_submitted")
                        .order("created_at", desc=False)
                        .limit(1)
                        .async_execute()
                    )
                    if ngo_pulse.data:
                        update_fields["assigned_to"] = ngo_pulse.data[0]["actor_id"]
                        update_fields["assigned_role"] = "ngo"
            else:
                update_fields["status"] = "approved"
            update_fields["rejection_reason"] = None  # Clear any previous rejection
            if body.assigned_to:
                update_fields["assigned_to"] = body.assigned_to
                update_fields["status"] = "assigned"
                # Detect assigned role dynamically
                if body.assigned_role:
                    update_fields["assigned_role"] = body.assigned_role
                elif "assigned_role" not in update_fields:
                    try:
                        assignee = (
                            await db_admin.table("users")
                            .select("role")
                            .eq("id", body.assigned_to)
                            .maybe_single()
                            .async_execute()
                        )
                        update_fields["assigned_role"] = (assignee.data or {}).get("role", "ngo")
                    except Exception:
                        update_fields["assigned_role"] = "ngo"
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
            await db_admin.table("resource_requests")
            .update(update_fields)
            .eq("id", request_id)
            .async_execute()
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

            resource_type = existing.data.get("resource_type", "resources")

            # ── Notify NGOs & Donors when a request is approved ──
            if new_status == "approved":
                await notify_all_by_role(
                    role="ngo",
                    title="🆕 New Approved Request",
                    message=f"A {existing.data.get('priority', 'medium')} priority request for {resource_type} has been approved and needs fulfillment.",
                    notification_type="info",
                    related_id=request_id,
                    related_type="request",
                )
                await notify_all_by_role(
                    role="donor",
                    title="🆕 New Approved Request",
                    message=f"A {existing.data.get('priority', 'medium')} priority request for {resource_type} has been approved. You can pledge support.",
                    notification_type="info",
                    related_id=request_id,
                    related_type="request",
                )
                # ── Notify volunteers when a "Volunteers" request is approved ──
                if resource_type == "Volunteers":
                    await notify_all_by_role(
                        role="volunteer",
                        title="🙋 Volunteers Needed",
                        message=f"A {existing.data.get('priority', 'medium')} priority request for volunteers has been approved. Check your dashboard for available assignments.",
                        notification_type="warning",
                        related_id=request_id,
                        related_type="request",
                    )

            # ── Notify the assigned NGO when request is assigned ──
            assigned_to = update_fields.get("assigned_to")
            if new_status == "assigned" and assigned_to:
                await notify_user(
                    user_id=assigned_to,
                    title="📦 Request Assigned to You",
                    message=f"You have been assigned a {existing.data.get('priority', 'medium')} priority request for {resource_type}. Please begin fulfillment.",
                    notification_type="warning",
                    related_id=request_id,
                    related_type="request",
                )

        except Exception as ne:
            logger.warning(f"Notification failed (non-critical): {ne}")

        # ── Emit event sourcing events ──
        try:
            await emit_request_status_changed(
                request_id=request_id,
                old_status=current_status,
                new_status=new_status,
                changed_by=admin.get("id"),
                reason=body.admin_note or body.rejection_reason,
            )
            assigned_to = update_fields.get("assigned_to")
            if new_status == "assigned" and assigned_to:
                await emit_request_assigned(
                    request_id=request_id,
                    assigned_to=assigned_to,
                    assigned_by=admin.get("id"),
                    assigned_role=update_fields.get("assigned_role", "ngo"),
                )
        except Exception as ee:
            logger.warning(f"Event sourcing failed (non-critical): {ee}")

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
            await db_admin.table("resource_requests")
            .update(update_fields)
            .eq("id", request_id)
            .async_execute()
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
        query = db_admin.table("available_resources").select("*", count="exact")

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

        response = await query.async_execute()

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
                    await db_admin.table("users")
                    .select("id, full_name, email, role")
                    .in_("id", provider_ids)
                    .async_execute()
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
            await db_admin.table("available_resources")
            .select("category, total_quantity, claimed_quantity")
            .eq("is_active", True)
            .async_execute()
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


@router.get("/notifications")
async def list_notifications(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    """Get notifications for the authenticated user. Works for any role."""
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        user_id = decoded["uid"]
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
        decoded = _verify_supabase_token(credentials.credentials)
        user_id = decoded["uid"]
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
            await db_admin.table("operational_pulse")
            .select("*")
            .eq("target_id", request_id)
            .eq("action_type", "ngo_availability_submitted")
            .order("created_at", desc=True)
            .async_execute()
        )
        ngo_submissions = ngo_resp.data or []

        # Fetch donor pledge submissions from operational_pulse
        donor_resp = (
            await db_admin.table("operational_pulse")
            .select("*")
            .eq("target_id", request_id)
            .eq("action_type", "donor_pledge_submitted")
            .order("created_at", desc=True)
            .async_execute()
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
                await db_admin.table("users")
                .select("id, full_name, email, phone, role, metadata")
                .in_("id", all_ids)
                .async_execute()
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
            await db_admin.table("resource_requests")
            .select("id, status, priority, resource_type, created_at")
            .gte("created_at", since)
            .order("created_at")
            .async_execute()
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
                await db_admin.table("resource_requests")
                .select("*")
                .order("created_at", desc=True)
                .limit(5000)
                .async_execute()
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
                await db_admin.table("available_resources")
                .select("*")
                .limit(5000)
                .async_execute()
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
                await db_admin.table("users")
                .select("id, full_name, email, phone, role, created_at, updated_at")
                .limit(5000)
                .async_execute()
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
        resp = await (
            db_admin.table("resource_requests")
            .select(
                "id, victim_id, resource_type, quantity, description, status, created_at"
            )
            .gte("created_at", since)
            .order("victim_id")
            .order("created_at")
            .async_execute()
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


# ── Fairness Frontier ─────────────────────────────────────────────────────────


class FairnessApplyBody(BaseModel):
    """Body for applying a specific Pareto-frontier allocation plan."""

    plan_index: int = Field(..., ge=0, le=9, description="Index of the plan on the frontier (0–9)")
    disaster_id: Optional[str] = Field(None, description="Disaster to allocate for")


@router.get("/fairness-frontier")
async def get_fairness_frontier(
    disaster_id: Optional[str] = Query(None, description="Disaster ID to compute frontier for"),
    max_distance_km: float = Query(500.0, ge=1, description="Max resource distance in km"),
    admin=Depends(require_admin),
):
    """
    Return 10 allocation plans on the Pareto frontier between
    pure-efficiency (index 0) and pure-equity (index 9).

    Each plan includes efficiency_score, equity_score, gini,
    zone-level allocations, and any fairness adjustments applied.
    """
    try:
        from ml.fair_allocator import (
            compute_pareto_frontier,
            FairAllocationPlan,
        )
        from ml.fairness_metrics import (
            ZoneDemographics,
            ZoneAllocation,
            HistoricalRecord,
        )
        from app.services.allocation_engine import (
            AvailableResource,
            ResourceNeed,
            PriorityWeights,
        )
        from datetime import datetime, timezone

        # ── Fetch resources ──
        res_resp = await db_admin.table("resources").select("*").eq("status", "available").async_execute()
        resource_rows = res_resp.data or []

        # ── Fetch active needs (resource_requests with status pending/approved) ──
        needs_resp = (
            await db_admin.table("resource_requests")
            .select("*")
            .async_execute()
        )
        need_rows = [
            r for r in (needs_resp.data or [])
            if r.get("status") in ("pending", "approved", "in_progress")
        ]

        # If disaster_id given, filter
        if disaster_id:
            resource_rows = [
                r for r in resource_rows
                if r.get("disaster_id") == disaster_id or not r.get("disaster_id")
            ]
            need_rows = [
                r for r in need_rows
                if r.get("disaster_id") == disaster_id
            ]

        # ── Fetch locations for coordinate mapping ──
        loc_resp = await db_admin.table("locations").select("*").async_execute()
        loc_map = {l["id"]: l for l in (loc_resp.data or [])}

        # ── Build AvailableResource list ──
        resources = []
        for r in resource_rows:
            loc = loc_map.get(r.get("location_id", ""), {})
            exp_str = r.get("expiry_date")
            exp_date = None
            if exp_str:
                try:
                    exp_date = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                except Exception:
                    pass
            resources.append(
                AvailableResource(
                    id=r["id"],
                    resource_type=r.get("type", r.get("resource_type", "other")),
                    quantity=float(r.get("quantity", 0)),
                    priority=int(r.get("priority", 5)),
                    location_lat=float(loc.get("latitude", 0)),
                    location_lng=float(loc.get("longitude", 0)),
                    location_id=r.get("location_id", ""),
                    expiry_date=exp_date,
                )
            )

        # ── Build ResourceNeed list ──
        needs = []
        for n in need_rows:
            loc = loc_map.get(n.get("location_id", ""), {})
            needs.append(
                ResourceNeed(
                    need_type=n.get("resource_type", "other"),
                    quantity=float(n.get("quantity", 1)),
                    urgency=float(n.get("nlp_priority", n.get("urgency", 5))),
                    zone_lat=float(loc.get("latitude", 0)),
                    zone_lng=float(loc.get("longitude", 0)),
                )
            )

        # ── Build zone demographics from locations ──
        zones = []
        for loc in (loc_resp.data or []):
            meta = loc.get("metadata") or {}
            pop = int(loc.get("population", 0) or 0)
            zones.append(
                ZoneDemographics(
                    zone_id=loc["id"],
                    zone_name=loc.get("name", ""),
                    latitude=float(loc.get("latitude", 0)),
                    longitude=float(loc.get("longitude", 0)),
                    population=pop,
                    elderly_ratio=float(meta.get("elderly_ratio", 0.12)),
                    children_ratio=float(meta.get("children_ratio", 0.2)),
                    medical_needs_ratio=float(meta.get("medical_needs_ratio", 0.08)),
                    ngo_count_within_20km=int(meta.get("ngo_count_within_20km", 10)),
                    is_rural=bool(meta.get("is_rural", loc.get("type") == "region")),
                )
            )

        # ── Build historical records (best-effort from past allocations) ──
        hist_records: list = []
        try:
            alloc_log_resp = await db_admin.table("allocation_log").select("*").async_execute()
            for row in (alloc_log_resp.data or []):
                hist_records.append(
                    HistoricalRecord(
                        disaster_id=row.get("disaster_id", ""),
                        zone_id=row.get("zone_id", row.get("location_id", "")),
                        resources_received=float(row.get("quantity", 0)),
                        median_resources=float(row.get("median_quantity", 0)),
                    )
                )
        except Exception:
            pass  # table may not exist yet

        # ── Compute Pareto frontier ──
        frontier = compute_pareto_frontier(
            resources=resources,
            needs=needs,
            zones=zones,
            historical_records=hist_records,
            max_distance_km=max_distance_km,
            disaster_id=disaster_id,
        )

        return {
            "disaster_id": disaster_id,
            "total_resources": len(resources),
            "total_needs": len(needs),
            "total_zones": len(zones),
            "plans": [
                {
                    "plan_index": p.plan_index,
                    "equity_weight": p.equity_weight,
                    "efficiency_score": p.efficiency_score,
                    "equity_score": p.equity_score,
                    "gini": p.gini,
                    "allocation_count": len(p.allocations),
                    "zone_allocations": p.zone_allocations,
                    "adjustments_applied": p.adjustments_applied,
                    "allocations": p.allocations[:50],  # cap for response size
                }
                for p in frontier.plans
            ],
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to compute fairness frontier: {str(e)}")


@router.post("/fairness-frontier/apply")
async def apply_fairness_plan(
    body: FairnessApplyBody,
    admin=Depends(require_admin),
):
    """
    Execute the chosen Pareto-frontier allocation plan.

    Re-computes the frontier, selects the plan at ``plan_index``,
    and marks resources as allocated in the database.
    """
    try:
        from ml.fair_allocator import compute_pareto_frontier
        from ml.fairness_metrics import (
            ZoneDemographics,
            ZoneAllocation,
            HistoricalRecord,
        )
        from app.services.allocation_engine import AvailableResource, ResourceNeed
        from datetime import datetime, timezone

        # Re-fetch data (same logic as GET endpoint)
        res_resp = await db_admin.table("resources").select("*").eq("status", "available").async_execute()
        resource_rows = res_resp.data or []
        needs_resp = await db_admin.table("resource_requests").select("*").async_execute()
        need_rows = [
            r for r in (needs_resp.data or [])
            if r.get("status") in ("pending", "approved", "in_progress")
        ]
        if body.disaster_id:
            resource_rows = [
                r for r in resource_rows
                if r.get("disaster_id") == body.disaster_id or not r.get("disaster_id")
            ]
            need_rows = [
                r for r in need_rows
                if r.get("disaster_id") == body.disaster_id
            ]

        loc_resp = await db_admin.table("locations").select("*").async_execute()
        loc_map = {l["id"]: l for l in (loc_resp.data or [])}

        resources = []
        for r in resource_rows:
            loc = loc_map.get(r.get("location_id", ""), {})
            resources.append(
                AvailableResource(
                    id=r["id"],
                    resource_type=r.get("type", r.get("resource_type", "other")),
                    quantity=float(r.get("quantity", 0)),
                    priority=int(r.get("priority", 5)),
                    location_lat=float(loc.get("latitude", 0)),
                    location_lng=float(loc.get("longitude", 0)),
                    location_id=r.get("location_id", ""),
                )
            )

        needs = []
        for n in need_rows:
            loc = loc_map.get(n.get("location_id", ""), {})
            needs.append(
                ResourceNeed(
                    need_type=n.get("resource_type", "other"),
                    quantity=float(n.get("quantity", 1)),
                    urgency=float(n.get("nlp_priority", n.get("urgency", 5))),
                    zone_lat=float(loc.get("latitude", 0)),
                    zone_lng=float(loc.get("longitude", 0)),
                )
            )

        zones = []
        for loc in (loc_resp.data or []):
            meta = loc.get("metadata") or {}
            zones.append(
                ZoneDemographics(
                    zone_id=loc["id"],
                    zone_name=loc.get("name", ""),
                    latitude=float(loc.get("latitude", 0)),
                    longitude=float(loc.get("longitude", 0)),
                    population=int(loc.get("population", 0) or 0),
                    elderly_ratio=float(meta.get("elderly_ratio", 0.12)),
                    children_ratio=float(meta.get("children_ratio", 0.2)),
                    medical_needs_ratio=float(meta.get("medical_needs_ratio", 0.08)),
                    ngo_count_within_20km=int(meta.get("ngo_count_within_20km", 10)),
                    is_rural=bool(meta.get("is_rural", loc.get("type") == "region")),
                )
            )

        hist_records: list = []
        try:
            alloc_log_resp = await db_admin.table("allocation_log").select("*").async_execute()
            for row in (alloc_log_resp.data or []):
                hist_records.append(
                    HistoricalRecord(
                        disaster_id=row.get("disaster_id", ""),
                        zone_id=row.get("zone_id", row.get("location_id", "")),
                        resources_received=float(row.get("quantity", 0)),
                        median_resources=float(row.get("median_quantity", 0)),
                    )
                )
        except Exception:
            pass

        frontier = compute_pareto_frontier(
            resources=resources,
            needs=needs,
            zones=zones,
            historical_records=hist_records,
            disaster_id=body.disaster_id,
        )

        if body.plan_index >= len(frontier.plans):
            raise HTTPException(
                status_code=400,
                detail=f"Plan index {body.plan_index} out of range (0–{len(frontier.plans)-1})",
            )

        chosen = frontier.plans[body.plan_index]

        # Mark resources as allocated in DB
        applied = 0
        for alloc in chosen.allocations:
            rid = alloc.get("resource_id")
            if not rid:
                continue
            try:
                await db_admin.table("resources").update({
                    "status": "allocated",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", rid).async_execute()
                applied += 1
            except Exception as e:
                logger.warning("Failed to mark resource %s allocated: %s", rid, e)

        # Store fairness audit
        try:
            from ml.fair_allocator import generate_fairness_audit
            from ml.fairness_metrics import ZoneAllocation as ZA
            zone_allocs = [
                ZA(zone_id=zid, allocated_quantity=qty)
                for zid, qty in chosen.zone_allocations.items()
            ]
            audit = generate_fairness_audit(
                zones=zones,
                allocations=zone_allocs,
                historical_records=hist_records,
                disaster_id=body.disaster_id,
            )
            audit["plan_index"] = body.plan_index
            audit["applied_by"] = admin.get("id") if isinstance(admin, dict) else None
            audit["applied_at"] = datetime.now(timezone.utc).isoformat()
            await db_admin.table("fairness_audits").insert(audit).async_execute()
        except Exception as e:
            logger.warning("Failed to store fairness audit: %s", e)

        return {
            "status": "applied",
            "plan_index": body.plan_index,
            "resources_allocated": applied,
            "efficiency_score": chosen.efficiency_score,
            "equity_score": chosen.equity_score,
            "gini": chosen.gini,
            "adjustments_applied": chosen.adjustments_applied,
        }
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to apply plan: {str(e)}")


@router.get("/fairness-audit")
async def get_fairness_audit(
    disaster_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    admin=Depends(require_admin),
):
    """Retrieve stored fairness audit reports."""
    try:
        query = db_admin.table("fairness_audits").select("*").order("applied_at", desc=True).limit(limit)
        if disaster_id:
            query = query.eq("disaster_id", disaster_id)
        resp = await query.async_execute()
        return {"audits": resp.data or [], "count": len(resp.data or [])}
    except Exception as e:
        logger.warning("Failed to fetch fairness audits: %s", e)
        return {"audits": [], "count": 0}
