"""
Admin-only endpoints for user management, platform settings, platform stats,
request management (approve/reject), and available resources.

All endpoints verify the caller is an admin by checking their role
in the ``users`` table. The ``db_admin`` client (service-role key)
is used so that Row-Level-Security is bypassed.
"""

import json
import logging
import os
import traceback
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = logging.getLogger("admin_router")

from app.database import db_admin
from app.dependencies import _verify_supabase_token, require_admin
from app.services.event_sourcing_service import (
    emit_request_assigned,
    emit_request_status_changed,
)
from app.services.notification_service import (
    get_request_audit_trail,
    get_unread_count,
    get_user_notifications,
    mark_notifications_read,
    notify_all_by_role,
    notify_request_status_change,
    notify_user,
)
from app.services.unified_resource_service import unified_resource_service

router = APIRouter()
security = HTTPBearer()


# ── Schemas ───────────────────────────────────────────────────────────────────


class UpdateRoleBody(BaseModel):
    role: str
    reason: str | None = None


class VerifyUserBody(BaseModel):
    status: str  # verified, rejected, pending
    notes: str | None = None


class ReviewRoleSwitchBody(BaseModel):
    action: str = Field(..., description="'approve' or 'reject'")
    requested_role: str = Field(..., description="Requested target role")
    request_id: str | None = Field(None, description="Optional specific request id")
    reason: str | None = Field(None, description="Admin note")


class PlatformSettingsBody(BaseModel):
    platform_name: str | None = None
    support_email: str | None = None
    auto_sitrep: bool | None = None
    sitrep_interval: int | None = None
    auto_allocate: bool | None = None
    ingestion_enabled: bool | None = None
    ingestion_interval: int | None = None
    email_notifications: bool | None = None
    sms_alerts: bool | None = None
    maintenance_mode: bool | None = None
    api_rate_limit: int | None = None
    max_upload_mb: int | None = None
    session_timeout: int | None = None
    data_retention_days: int | None = None


class ApproveRejectBody(BaseModel):
    """Body for approving or rejecting a resource request."""

    action: str = Field(..., description="'approve', 'reject', 'reassign', or 'escalate'")
    rejection_reason: str | None = Field(None, description="Required when rejecting")
    admin_note: str | None = Field(None, description="Optional note from admin")
    assigned_to: str | None = Field(None, description="User ID to assign to (NGO/donor)")
    assigned_role: str | None = Field(
        None, description="Role of the assignee: 'ngo' or 'donor'. Auto-detected if omitted."
    )
    estimated_delivery: str | None = Field(None, description="ISO date for estimated delivery")


class AdminNoteBody(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/users")
async def list_users(admin=Depends(require_admin)):
    """Return every user row (bypasses RLS via service-role client)."""
    resp = await db_admin.table("users").select("*").order("created_at", desc=True).limit(500).async_execute()
    return resp.data or []


@router.patch("/users/{user_id}/role")
async def update_user_role(user_id: str, body: UpdateRoleBody, admin=Depends(require_admin)):
    """Change a user's role with audit note."""
    from datetime import datetime

    updates = {"role": body.role, "updated_at": datetime.now(UTC).isoformat()}

    # Store history in metadata
    metadata_resp = await db_admin.table("users").select("metadata").eq("id", user_id).maybe_single().async_execute()
    existing_meta = (metadata_resp.data or {}).get("metadata") or {}

    history = existing_meta.get("role_history", [])
    history.append(
        {
            "changed_by": admin.get("id"),
            "timestamp": datetime.now(UTC).isoformat(),
            "new_role": body.role,
            "reason": body.reason or "No reason provided",
        }
    )
    existing_meta["role_history"] = history

    pending_requests = existing_meta.get("pending_role_switch_requests", [])
    for req in pending_requests:
        if req.get("status") == "pending" and req.get("requested_role") == body.role:
            req["status"] = "approved"
            req["reviewed_by"] = admin.get("id")
            req["reviewed_at"] = datetime.now(UTC).isoformat()
            req["review_note"] = body.reason or "Approved by admin"
            break
    existing_meta["pending_role_switch_requests"] = pending_requests

    existing_meta["latest_role_switch_request"] = {
        "requested_role": body.role,
        "status": "approved",
        "reviewed_by": admin.get("id"),
        "reviewed_at": datetime.now(UTC).isoformat(),
    }
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


@router.post("/users/{user_id}/role-request/review")
async def review_role_switch_request(user_id: str, body: ReviewRoleSwitchBody, admin=Depends(require_admin)):
    """Approve or reject a pending role switch request for a user."""
    if body.action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    metadata_resp = await db_admin.table("users").select("role, metadata").eq("id", user_id).maybe_single().async_execute()
    row = metadata_resp.data or {}
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    existing_meta = row.get("metadata") or {}
    pending_requests = existing_meta.get("pending_role_switch_requests", [])

    target_request = None
    for req in pending_requests:
        if req.get("status") != "pending":
            continue
        if req.get("requested_role") != body.requested_role:
            continue
        if body.request_id and req.get("request_id") != body.request_id:
            continue
        target_request = req
        break

    if not target_request:
        raise HTTPException(status_code=404, detail="Pending role switch request not found")

    now_iso = datetime.now(UTC).isoformat()
    target_request["status"] = "approved" if body.action == "approve" else "rejected"
    target_request["reviewed_by"] = admin.get("id")
    target_request["reviewed_at"] = now_iso
    target_request["review_note"] = body.reason or ("Approved by admin" if body.action == "approve" else "Rejected by admin")

    existing_meta["pending_role_switch_requests"] = pending_requests
    existing_meta["latest_role_switch_request"] = {
        "requested_role": body.requested_role,
        "status": target_request["status"],
        "reviewed_by": admin.get("id"),
        "reviewed_at": now_iso,
        "reason": body.reason,
    }

    history = existing_meta.get("role_history", [])
    history.append(
        {
            "changed_by": admin.get("id"),
            "timestamp": now_iso,
            "new_role": body.requested_role,
            "reason": body.reason or f"Role switch request {body.action}",
            "request_id": target_request.get("request_id"),
            "action": body.action,
        }
    )
    existing_meta["role_history"] = history

    updates: dict[str, object] = {
        "metadata": existing_meta,
        "updated_at": now_iso,
    }

    if body.action == "approve":
        updates["role"] = body.requested_role

    resp = await db_admin.table("users").update(updates).eq("id", user_id).async_execute()
    if not resp.data:
        raise HTTPException(status_code=404, detail="User not found")

    if body.action == "approve":
        try:
            from app.db_client import get_supabase_client

            sb = get_supabase_client()
            sb.auth.admin.update_user_by_id(user_id, {"app_metadata": {"role": body.requested_role}})
        except Exception as e:
            print(f"Warning: Failed to sync Supabase auth metadata: {e}")

    return {
        "message": f"Role switch request {body.action}d",
        "status": target_request["status"],
        "requested_role": body.requested_role,
        "user": resp.data[0],
    }


@router.post("/users/{user_id}/verify")
async def verify_user(user_id: str, body: VerifyUserBody, admin=Depends(require_admin)):
    """Verify or reject an NGO/Donor/Volunteer account."""
    logger.info("verify_user called: user_id=%s status=%s by admin=%s", user_id, body.status, admin.get("id"))

    if body.status not in ("verified", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")

    try:
        # 1. Update the Users table (both column and metadata for compatibility)
        metadata_resp = (
            await db_admin.table("users").select("metadata").eq("id", user_id).maybe_single().async_execute()
        )
        existing_meta = (metadata_resp.data or {}).get("metadata") or {}

        existing_meta["verification_status"] = body.status
        existing_meta["verification_notes"] = body.notes
        existing_meta["verified_at"] = datetime.now(UTC).isoformat() if body.status == "verified" else None
        existing_meta["verified_by"] = admin.get("id")

        updates = {
            "verification_status": body.status,  # Top-level column
            "metadata": existing_meta,  # JSONB metadata
            "updated_at": datetime.now(UTC).isoformat(),
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
        sb.auth.admin.update_user_by_id(
            user_id,
            {
                "app_metadata": {"verification_status": body.status},
            },
        )
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

    await db_admin.table("users").delete().eq("id", user_id).async_execute()
    return {"deleted": True}


# ── Platform Settings ─────────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(admin=Depends(require_admin)):
    """Get platform settings (single row)."""
    resp = await db_admin.table("platform_settings").select("*").eq("id", 1).maybe_single().async_execute()
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
    updates["updated_at"] = datetime.now(UTC).isoformat()

    # Upsert: update the single row
    resp = await db_admin.table("platform_settings").update(updates).eq("id", 1).async_execute()
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
        TTL_MEDIUM,
    )
    from app.core.query_cache import (
        cache_get as mem_cache_get,
    )
    from app.core.query_cache import (
        cache_set as mem_cache_set,
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
        resolved_disasters = sum(1 for d in disaster_data if d.get("status") == "resolved")
        total_casualties_helped = sum(int(d.get("casualties") or 0) for d in disaster_data)

        # Count resources
        resources_resp = (
            await db_admin.table("resources").select("id, status", count="exact").limit(5000).async_execute()
        )
        total_resources = resources_resp.count or 0
        resource_data = resources_resp.data or []
        allocated_resources = sum(
            1 for r in resource_data if r.get("status") in ("allocated", "in_transit", "delivered")
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
            await db_admin.table("users").select("id", count="exact").eq("role", "ngo").limit(5000).async_execute()
        )
        total_ngos = ngos_resp.count or 0

        # Count donations
        donations_resp = (
            await db_admin.table("donations").select("amount").eq("status", "completed").limit(5000).async_execute()
        )
        donation_data = donations_resp.data or []
        total_donated = sum(float(d.get("amount", 0)) for d in donation_data)

        result = {
            "lives_impacted": max(total_casualties_helped, total_users * 3),  # Estimate: each user impacts ~3 people
            "total_users": total_users,
            "total_volunteers": total_volunteers,
            "total_ngos": total_ngos,
            "active_disasters": active_disasters,
            "resolved_disasters": resolved_disasters,
            "total_disasters": total_disasters,
            "total_resources": total_resources,
            "resources_allocated": allocated_resources,
            "total_donated": total_donated,
            "avg_response_minutes": (45 if resolved_disasters == 0 else max(15, 90 - resolved_disasters * 2)),
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
        location_ids = list(set(d["location_id"] for d in base_data if d.get("location_id")))
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
                    "location_name": loc.get("name") or loc.get("city") or loc.get("country") or "Unknown",
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


async def _resolve_assignee_role(assignee_id: str | None, fallback: str = "ngo") -> str:
    if not assignee_id:
        return fallback
    try:
        assignee = await db_admin.table("users").select("role").eq("id", assignee_id).maybe_single().async_execute()
        role = (assignee.data or {}).get("role")
        return role or fallback
    except Exception:
        return fallback


@router.get("/requests")
async def list_all_requests(
    admin=Depends(require_admin),
    status: str | None = Query(
        None,
        description="Filter by status: pending,approved,assigned,in_progress,completed,rejected",
    ),
    priority: str | None = Query(None, description="Filter by priority: critical,high,medium,low"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    search: str | None = Query(None, description="Search by ID, description, or victim_id"),
    date_from: str | None = Query(None, description="Filter from date (ISO)"),
    date_to: str | None = Query(None, description="Filter to date (ISO)"),
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
            query = query.or_(f"id.eq.{search},description.ilike.%{search}%,victim_id.eq.{search}")
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
            for entry in r.get("fulfillment_entries") or []:
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
            for entry in row.get("fulfillment_entries") or []:
                pid = entry.get("provider_id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    u_info = user_map.get(pid, {})
                    contributors.append(
                        {
                            "id": pid,
                            "full_name": u_info.get("full_name") or entry.get("provider_name") or "Unknown",
                            "role": entry.get("provider_role") or "unknown",
                        }
                    )
            row["assigned_users"] = contributors

            requests.append(row)

        # Stats overview
        all_resp = await db_admin.table("resource_requests").select("status", count="exact").limit(5000).async_execute()
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
        raise HTTPException(status_code=500, detail=f"Error fetching requests: {str(e)}")


@router.get("/requests/{request_id}")
async def get_request_detail(
    request_id: str,
    admin=Depends(require_admin),
):
    """Get a single resource request with full detail — admin only."""
    try:
        response = await db_admin.table("resource_requests").select("*").eq("id", request_id).single().async_execute()
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
    if body.action not in ("approve", "reject", "reassign", "escalate"):
        raise HTTPException(status_code=400, detail="Action must be one of: approve, reject, reassign, escalate")

    if body.action == "reject" and not body.rejection_reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required when rejecting")

    if body.action == "reassign" and not body.assigned_to:
        raise HTTPException(status_code=400, detail="assigned_to is required when reassigning")

    try:
        # Verify request exists
        existing = await db_admin.table("resource_requests").select("*").eq("id", request_id).single().async_execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Request not found")

        current_status = existing.data.get("status")
        previous_assignee = existing.data.get("assigned_to")

        # Build update
        update_fields = {
            "updated_at": datetime.now(UTC).isoformat(),
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
                        update_fields["assigned_role"] = await _resolve_assignee_role(body.assigned_to, fallback="ngo")
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
                    update_fields["assigned_role"] = await _resolve_assignee_role(body.assigned_to, fallback="ngo")
            if body.estimated_delivery:
                update_fields["estimated_delivery"] = body.estimated_delivery

        elif body.action == "reject":
            if current_status in ("completed",):
                raise HTTPException(status_code=400, detail="Cannot reject a completed request.")
            update_fields["status"] = "rejected"
            update_fields["rejection_reason"] = body.rejection_reason
            update_fields["assigned_to"] = None
            update_fields["assigned_role"] = None

        elif body.action == "reassign":
            if current_status in ("completed", "closed", "rejected"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot reassign request with status '{current_status}'.",
                )

            update_fields["status"] = "assigned"
            update_fields["assigned_to"] = body.assigned_to
            update_fields["rejection_reason"] = None
            update_fields["assigned_role"] = body.assigned_role or await _resolve_assignee_role(body.assigned_to)

        elif body.action == "escalate":
            if current_status in ("completed", "closed", "rejected"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot escalate request with status '{current_status}'.",
                )

            current_priority = (existing.data.get("priority") or "medium").lower()
            escalation_map = {"low": "medium", "medium": "high", "high": "critical", "critical": "critical"}
            update_fields["priority"] = escalation_map.get(current_priority, "high")
            update_fields["sla_escalated_at"] = datetime.now(UTC).isoformat()

        response = await db_admin.table("resource_requests").update(update_fields).eq("id", request_id).async_execute()

        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to update request")

        new_status = update_fields.get("status", current_status)

        # Send notification to victim & create audit trail
        try:
            # Build audit details: include admin note if provided
            audit_details = body.rejection_reason if body.action == "reject" else None
            if body.admin_note:
                audit_details = f"{audit_details or ''}\n[Admin Note] {body.admin_note}".strip()

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
            if new_status == "assigned" and assigned_to and assigned_to != previous_assignee:
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
            if new_status == "assigned" and assigned_to and (assigned_to != previous_assignee or current_status != "assigned"):
                await emit_request_assigned(
                    request_id=request_id,
                    assigned_to=assigned_to,
                    assigned_by=admin.get("id"),
                    assigned_role=update_fields.get("assigned_role", "ngo"),
                )
        except Exception as ee:
            logger.warning(f"Event sourcing failed (non-critical): {ee}")

        action_messages = {
            "approve": "Request approved successfully",
            "reject": "Request rejected successfully",
            "reassign": "Request reassigned successfully",
            "escalate": "Request escalated successfully",
        }
        return {
            "message": action_messages.get(body.action, "Request updated successfully"),
            "request": _safe_request_row(response.data[0]),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ ADMIN ACTION ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing action: {str(e)}")


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
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    try:
        existing = (
            await db_admin.table("resource_requests")
            .select("id, status, assigned_to")
            .eq("id", request_id)
            .maybe_single()
            .async_execute()
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="Request not found")

        update_fields = {
            "status": new_status,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if body.get("rejection_reason"):
            update_fields["rejection_reason"] = body["rejection_reason"]
        if body.get("assigned_to"):
            update_fields["assigned_to"] = body["assigned_to"]
            update_fields["assigned_role"] = await _resolve_assignee_role(body["assigned_to"])
        elif new_status in ("pending", "approved", "availability_submitted", "under_review", "rejected"):
            update_fields["assigned_to"] = None
            update_fields["assigned_role"] = None
        if body.get("estimated_delivery"):
            update_fields["estimated_delivery"] = body["estimated_delivery"]

        if new_status == "assigned" and not update_fields.get("assigned_to") and not existing.data.get("assigned_to"):
            raise HTTPException(status_code=400, detail="assigned_to is required when status is set to 'assigned'")

        response = await db_admin.table("resource_requests").update(update_fields).eq("id", request_id).async_execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to update request status")
        return _safe_request_row(response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating status: {str(e)}")


# ── Available Resources (admin view) ──────────────────────────────────────


@router.get("/available-resources")
async def list_available_resources(
    admin=Depends(require_admin),
    category: str | None = Query(None, description="Filter by category"),
    status: str | None = Query(None, description="Filter by status: available, reserved"),
    search: str | None = Query(None, description="Search by title or description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all available resources across all providers using unified service. Admin only."""
    try:
        # Use the unified service to get resources
        status_filter = None
        if status:
            status_filter = status
        elif not status:
            # Default to available resources
            status_filter = "available"

        result = await unified_resource_service.get_unified_resources(
            category=category, status=status_filter, limit=page_size, offset=(page - 1) * page_size
        )

        resources = result["resources"]
        total = result["total"]
        category_summary = result["category_summary"]

        # Provider names enrichment (similar to original logic)
        provider_ids = list(set(r.get("provider_id") for r in resources if r.get("provider_id")))
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

        return {
            "resources": resources,
            "total": total,
            "page": page,
            "page_size": page_size,
            "category_summary": category_summary,
        }
    except Exception as e:
        print(f"❌ ADMIN RESOURCES ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching resources: {str(e)}")


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

    notifications = await get_user_notifications(user_id, unread_only=unread_only, limit=limit)
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
        raise HTTPException(status_code=500, detail=f"Error fetching submissions: {str(e)}")


# ── Analytics Data ────────────────────────────────────────────────────────


@router.get("/analytics/request-trends")
async def get_request_trends(
    admin=Depends(require_admin),
    days: int = Query(30, ge=1, le=365),
):
    """Get request creation trends over time."""
    try:
        from datetime import timedelta

        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
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

        avg_response_hours = round(sum(status_times) / len(status_times), 1) if status_times else 0

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

import csv
import io

from fastapi.responses import StreamingResponse


@router.get("/export/{data_type}")
async def export_data(
    data_type: str,
    admin=Depends(require_admin),
):
    """Export requests, resources, or users as CSV. Admin only."""
    if data_type not in ("requests", "resources", "users"):
        raise HTTPException(status_code=400, detail="Invalid data_type. Use: requests, resources, users")

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
            resp = await db_admin.table("resources").select("*").limit(5000).async_execute()
            rows = resp.data or []
            writer.writerow(
                [
                    "ID",
                    "Type",
                    "Name",
                    "Description",
                    "Quantity",
                    "Unit",
                    "Status",
                    "Provider ID",
                    "Location ID",
                    "Created At",
                ]
            )
            for r in rows:
                writer.writerow(
                    [
                        r.get("id"),
                        r.get("type"),
                        r.get("name"),
                        r.get("description", ""),
                        r.get("quantity"),
                        r.get("unit"),
                        r.get("status"),
                        r.get("provider_id"),
                        r.get("location_id"),
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
            headers={"Content-Disposition": f"attachment; filename={data_type}_export.csv"},
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

        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        resp = await (
            db_admin.table("resource_requests")
            .select("id, victim_id, resource_type, quantity, description, status, created_at")
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
        raise HTTPException(status_code=500, detail=f"Error detecting duplicates: {str(e)}")


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
    disaster_id: str | None = Field(None, description="Disaster to allocate for")


ACTIVE_FAIRNESS_REQUEST_STATUSES = {
    "pending",
    "under_review",
    "approved",
    "availability_submitted",
    "assigned",
    "in_progress",
    "delivered",
}

FAIRNESS_PRIORITY_SCORES = {
    "low": 2.0,
    "medium": 5.0,
    "high": 8.0,
    "critical": 10.0,
}


def _fairness_safe_float(value, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def _fairness_clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _fairness_priority_score(row: dict) -> float:
    priority = (row.get("manual_priority") or row.get("priority") or row.get("nlp_priority") or "medium").lower()
    return FAIRNESS_PRIORITY_SCORES.get(priority, 5.0)


def _fairness_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def _fairness_point_from_row(row: dict | None, location_map: dict[str, dict], disaster_map: dict[str, dict]) -> tuple[float | None, float | None]:
    if not row:
        return None, None

    if row.get("latitude") is not None and row.get("longitude") is not None:
        return _fairness_safe_float(row.get("latitude")), _fairness_safe_float(row.get("longitude"))

    location_id = row.get("location_id")
    if location_id and location_id in location_map:
        location = location_map[location_id]
        if location.get("latitude") is not None and location.get("longitude") is not None:
            return _fairness_safe_float(location.get("latitude")), _fairness_safe_float(location.get("longitude"))

    disaster_id = row.get("disaster_id") or row.get("linked_disaster_id")
    disaster = disaster_map.get(disaster_id) if disaster_id else None
    if disaster:
        return _fairness_point_from_row(disaster, location_map, disaster_map)

    return None, None


def _fairness_user_point(user: dict, location_map: dict[str, dict]) -> tuple[float | None, float | None]:
    metadata = user.get("metadata") or {}
    if metadata.get("latitude") is not None and metadata.get("longitude") is not None:
        return _fairness_safe_float(metadata.get("latitude")), _fairness_safe_float(metadata.get("longitude"))
    location_id = metadata.get("location_id")
    if location_id and location_id in location_map:
        location = location_map[location_id]
        if location.get("latitude") is not None and location.get("longitude") is not None:
            return _fairness_safe_float(location.get("latitude")), _fairness_safe_float(location.get("longitude"))
    return None, None


async def _build_fairness_inputs(disaster_id: str | None):
    from app.services.allocation_engine import AvailableResource, ResourceNeed
    from ml.fairness_metrics import HistoricalRecord, ZoneDemographics

    resource_resp = await db_admin.table("resources").select("*").eq("status", "available").async_execute()
    request_resp = await db_admin.table("resource_requests").select("*").limit(5000).async_execute()
    disaster_resp = await db_admin.table("disasters").select("*").limit(2000).async_execute()
    location_resp = (
        await db_admin.table("locations")
        .select("id, name, latitude, longitude, metadata, population, type")
        .limit(5000)
        .async_execute()
    )
    ngo_resp = await db_admin.table("users").select("id, metadata").eq("role", "ngo").limit(2000).async_execute()

    resource_rows = resource_resp.data or []
    request_rows = request_resp.data or []
    disaster_rows = disaster_resp.data or []
    location_rows = location_resp.data or []
    ngo_rows = ngo_resp.data or []

    disaster_map = {row["id"]: row for row in disaster_rows if row.get("id")}
    location_map = {row["id"]: row for row in location_rows if row.get("id")}

    def _matches_request(row: dict) -> bool:
        linked_disaster_id = row.get("disaster_id") or row.get("linked_disaster_id")
        if disaster_id:
            return linked_disaster_id == disaster_id
        return row.get("status") in ACTIVE_FAIRNESS_REQUEST_STATUSES

    filtered_requests = [row for row in request_rows if _matches_request(row)]
    if disaster_id:
        resource_rows = [
            row for row in resource_rows if row.get("disaster_id") in (None, "", disaster_id)
        ]

    resources = []
    for row in resource_rows:
        location = location_map.get(row.get("location_id"), {})
        expiry_date = None
        expiry_str = row.get("expiry_date")
        if expiry_str:
            try:
                expiry_date = datetime.fromisoformat(str(expiry_str).replace("Z", "+00:00"))
            except Exception:
                expiry_date = None
        resources.append(
            AvailableResource(
                id=row["id"],
                resource_type=row.get("type", row.get("resource_type", "other")),
                quantity=_fairness_safe_float(row.get("quantity"), 0.0),
                priority=int(_fairness_safe_float(row.get("priority"), 5.0)),
                location_lat=_fairness_safe_float(location.get("latitude"), 0.0),
                location_lng=_fairness_safe_float(location.get("longitude"), 0.0),
                location_id=row.get("location_id", ""),
                expiry_date=expiry_date,
            )
        )

    need_groups: dict[tuple[str, str], dict] = {}
    zone_aggregates: dict[str, dict] = {}
    for row in filtered_requests:
        zone_id = row.get("location_id") or row.get("disaster_id") or row.get("linked_disaster_id") or f"request:{row['id']}"
        lat, lon = _fairness_point_from_row(row, location_map, disaster_map)
        quantity = max(_fairness_safe_float(row.get("quantity"), 1.0), 1.0)
        head_count = max(int(row.get("head_count") or 1), 1)
        priority_score = _fairness_priority_score(row)
        resource_type = row.get("resource_type") or "other"

        zone = zone_aggregates.setdefault(
            zone_id,
            {
                "zone_id": zone_id,
                "lat": lat or 0.0,
                "lon": lon or 0.0,
                "request_count": 0,
                "urgent_count": 0,
                "head_count": 0,
                "medical_weight": 0,
                "survival_weight": 0,
                "verified_count": 0,
                "fulfillment_total": 0.0,
                "location": location_map.get(row.get("location_id"), {}),
            },
        )
        zone["request_count"] += 1
        zone["head_count"] += head_count
        zone["urgent_count"] += 1 if priority_score >= 8.0 else 0
        zone["verified_count"] += 1 if row.get("is_verified") or row.get("verification_status") == "verified" else 0
        zone["fulfillment_total"] += _fairness_safe_float(row.get("fulfillment_pct"), 0.0)
        lowered_type = resource_type.lower()
        if any(token in lowered_type for token in ("medical", "medicine", "oxygen", "ambulance", "insulin", "blood")):
            zone["medical_weight"] += 1
        if any(token in lowered_type for token in ("water", "food", "shelter", "blanket", "clothing", "baby", "hygiene")):
            zone["survival_weight"] += 1

        need_key = (zone_id, resource_type)
        grouped_need = need_groups.setdefault(
            need_key,
            {
                "zone_id": zone_id,
                "resource_type": resource_type,
                "quantity": 0.0,
                "urgency": 0.0,
                "lat": lat or 0.0,
                "lon": lon or 0.0,
                "request_id": row["id"],
                "victim_id": row.get("victim_id"),
                "head_count": head_count,
            },
        )
        grouped_need["quantity"] += quantity
        grouped_need["urgency"] = max(grouped_need["urgency"], _fairness_clamp(priority_score + min(head_count, 8) / 4.0, 1.0, 10.0))
        grouped_need["head_count"] = max(grouped_need["head_count"], head_count)

    needs = [
        ResourceNeed(
            need_type=entry["resource_type"],
            quantity=round(entry["quantity"], 2),
            urgency=round(entry["urgency"], 2),
            zone_lat=entry["lat"],
            zone_lng=entry["lon"],
            zone_id=entry["zone_id"],
            request_id=entry["request_id"],
            victim_id=entry["victim_id"],
            head_count=entry["head_count"],
        )
        for entry in need_groups.values()
    ]

    ngo_points = []
    for row in ngo_rows:
        lat, lon = _fairness_user_point(row, location_map)
        if lat is not None and lon is not None:
            ngo_points.append((lat, lon))

    zones = []
    for zone_id, zone_data in zone_aggregates.items():
        location = zone_data.get("location") or {}
        metadata = location.get("metadata") or {}
        request_count = max(zone_data["request_count"], 1)
        urgent_share = zone_data["urgent_count"] / request_count
        medical_share = zone_data["medical_weight"] / request_count
        survival_share = zone_data["survival_weight"] / request_count
        verified_share = zone_data["verified_count"] / request_count

        nearby_ngos = 0
        if ngo_points and (zone_data["lat"] or zone_data["lon"]):
            nearby_ngos = sum(
                1
                for ngo_lat, ngo_lon in ngo_points
                if _fairness_haversine_km(zone_data["lat"], zone_data["lon"], ngo_lat, ngo_lon) <= 20.0
            )

        elderly_ratio = _fairness_safe_float(
            metadata.get("elderly_ratio"),
            _fairness_clamp(0.08 + (urgent_share * 0.18) + (medical_share * 0.12), 0.05, 0.55),
        )
        children_ratio = _fairness_safe_float(
            metadata.get("children_ratio"),
            _fairness_clamp(0.10 + (survival_share * 0.20), 0.05, 0.60),
        )
        medical_needs_ratio = _fairness_safe_float(
            metadata.get("medical_needs_ratio"),
            _fairness_clamp(0.05 + (medical_share * 0.35) + ((1.0 - verified_share) * 0.10), 0.05, 0.85),
        )
        population = max(int(location.get("population") or 0), zone_data["head_count"] or 1)
        is_rural = bool(metadata.get("is_rural", location.get("type") == "region" or nearby_ngos == 0))

        zones.append(
            ZoneDemographics(
                zone_id=zone_id,
                zone_name=location.get("name", zone_id),
                latitude=zone_data["lat"],
                longitude=zone_data["lon"],
                population=population,
                elderly_ratio=elderly_ratio,
                children_ratio=children_ratio,
                medical_needs_ratio=medical_needs_ratio,
                ngo_count_within_20km=nearby_ngos,
                is_rural=is_rural,
            )
        )

    hist_records: list = []
    try:
        alloc_log_resp = await db_admin.table("allocation_log").select("*").limit(5000).async_execute()
        for row in alloc_log_resp.data or []:
            hist_records.append(
                HistoricalRecord(
                    disaster_id=row.get("disaster_id", ""),
                    zone_id=row.get("zone_id", row.get("location_id", "")),
                    resources_received=_fairness_safe_float(row.get("quantity"), 0.0),
                    median_resources=_fairness_safe_float(row.get("median_quantity"), 0.0),
                )
            )
    except Exception:
        pass

    summary = {
        "active_request_count": len(filtered_requests),
        "victims_impacted": sum(zone["head_count"] for zone in zone_aggregates.values()),
        "urgent_request_count": sum(zone["urgent_count"] for zone in zone_aggregates.values()),
        "zones_with_live_requests": len(zone_aggregates),
        "requested_resource_units": round(sum(item["quantity"] for item in need_groups.values()), 2),
        "available_resource_units": round(sum(_fairness_safe_float(row.get("quantity"), 0.0) for row in resource_rows), 2),
    }

    return resources, needs, zones, hist_records, summary


@router.get("/fairness-frontier")
async def get_fairness_frontier(
    disaster_id: str | None = Query(None, description="Disaster ID to compute frontier for"),
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
        )
        resources, needs, zones, hist_records, summary = await _build_fairness_inputs(disaster_id)

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
            "summary": summary,
            "derived_from": "Supabase victim requests, resources, locations, and NGO profiles",
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
        from ml.fairness_metrics import ZoneAllocation as ZA

        resources, needs, zones, hist_records, _summary = await _build_fairness_inputs(body.disaster_id)

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
                detail=f"Plan index {body.plan_index} out of range (0–{len(frontier.plans) - 1})",
            )

        chosen = frontier.plans[body.plan_index]

        # Mark resources as allocated in DB
        applied = 0
        for alloc in chosen.allocations:
            rid = alloc.get("resource_id")
            if not rid:
                continue
            try:
                await (
                    db_admin.table("resources")
                    .update(
                        {
                            "status": "allocated",
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    .eq("id", rid)
                    .async_execute()
                )
                applied += 1
            except Exception as e:
                logger.warning("Failed to mark resource %s allocated: %s", rid, e)

        # Store fairness audit
        try:
            from ml.fair_allocator import generate_fairness_audit

            zone_allocs = [ZA(zone_id=zid, allocated_quantity=qty) for zid, qty in chosen.zone_allocations.items()]
            audit = generate_fairness_audit(
                zones=zones,
                allocations=zone_allocs,
                historical_records=hist_records,
                disaster_id=body.disaster_id,
            )
            audit["plan_index"] = body.plan_index
            audit["applied_by"] = admin.get("id") if isinstance(admin, dict) else None
            audit["applied_at"] = datetime.now(UTC).isoformat()
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
    disaster_id: str | None = Query(None),
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


# ── Scheduled SitRep Configuration ──────────────────────────────────────────


class ScheduleSitRepBody(BaseModel):
    """Body for configuring the SitRep generation schedule."""

    interval_hours: int = Field(..., ge=1, le=24, description="Interval in hours (1–24)")


@router.post("/sitrep/schedule")
async def schedule_sitrep(
    body: ScheduleSitRepBody,
    admin=Depends(require_admin),
):
    """Configure the interval for automated SitRep generation.

    This updates the SITREP_CRON_HOUR_UTC in phase5_config.
    The interval is converted to a UTC hour (e.g., 6h -> hour 6).
    """
    try:
        # Update the config in memory (if mutable) or environment
        # Since phase5_config is frozen, we update the environment variable
        # and restart the cron task if needed.
        new_hour = body.interval_hours % 24  # Map interval to hour

        # Update environment variable for next restart
        os.environ["SITREP_CRON_HOUR_UTC"] = str(new_hour)

        # If the app supports runtime config reload, update the config object
        # For now, we log the change and note that a restart may be needed
        logger.info(f"Scheduled SitRep interval updated to {body.interval_hours}h (UTC hour {new_hour})")

        return {
            "message": f"Scheduled SitRep interval set to {body.interval_hours} hour(s).",
            "interval_hours": body.interval_hours,
            "utc_hour": new_hour,
            "note": "Changes take effect on next restart or when cron task is recreated.",
        }
    except Exception as e:
        logger.error(f"Failed to schedule SitRep: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule SitRep: {str(e)}")


@router.get("/sitrep/schedule")
async def get_sitrep_schedule(
    admin=Depends(require_admin),
):
    """Get the current SitRep generation schedule."""
    try:
        from app.core.phase5_config import phase5_config

        return {
            "interval_hours": phase5_config.SITREP_CRON_HOUR_UTC,
            "utc_hour": phase5_config.SITREP_CRON_HOUR_UTC,
            "description": f"Daily at {phase5_config.SITREP_CRON_HOUR_UTC}:00 UTC",
        }
    except Exception as e:
        logger.error(f"Failed to get SitRep schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")
