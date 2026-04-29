"""
Notifications & Audit Trail service.
Handles creating notifications for users when request statuses change,
and recording audit trail entries for all request lifecycle events.
Provides cross-role notification helpers so every workflow handoff
triggers the right alerts.
"""

import logging
import random
import string
from datetime import UTC, datetime

from app.database import db_admin

logger = logging.getLogger("notification_service")


async def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "info",  # info, success, warning, error, request_update
    related_id: str | None = None,  # request_id, disaster_id, etc.
    related_type: str | None = None,  # request, disaster, resource
) -> dict | None:
    """Create a notification for a user. Stored in DB for persistence."""
    try:
        # Map notification_type to priority for the DB schema
        type_to_priority = {
            "info": "low",
            "success": "medium",
            "warning": "high",
            "error": "critical",
            "request_update": "medium",
        }
        record = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "priority": type_to_priority.get(notification_type, "medium"),
            "read": False,
            "data": {
                "type": notification_type,
                "related_id": related_id,
                "related_type": related_type,
            },
            "action_url": (f"/victim/requests/{related_id}" if related_id and related_type == "request" else None),
        }
        resp = await db_admin.table("notifications").insert(record).async_execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        # Table might not exist yet — that's OK, we log and continue
        logger.warning(f"Could not create notification (table may not exist): {e}")
        return None


async def create_audit_entry(
    request_id: str,
    action: str,
    actor_id: str | None = None,
    actor_role: str = "system",
    old_status: str | None = None,
    new_status: str | None = None,
    details: str | None = None,
    metadata: dict | None = None,
) -> dict | None:
    """Record an audit trail entry for a request lifecycle event."""
    try:
        record = {
            "request_id": request_id,
            "action": action,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "old_status": old_status,
            "new_status": new_status,
            "details": details,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        resp = await db_admin.table("request_audit_log").insert(record).async_execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.warning(f"Could not create audit entry (table may not exist): {e}")
        return None


async def get_request_audit_trail(request_id: str) -> list[dict]:
    """Get the full audit trail for a request."""
    try:
        resp = (
            await db_admin.table("request_audit_log")
            .select("*")
            .eq("request_id", request_id)
            .order("created_at", desc=False)
            .limit(200)
            .async_execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning(f"Could not fetch audit trail: {e}")
        return []


async def get_user_notifications(
    user_id: str,
    unread_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """Get notifications for a user."""
    try:
        query = (
            db_admin.table("notifications")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if unread_only:
            query = query.eq("read", False)
        resp = await query.async_execute()
        return resp.data or []
    except Exception as e:
        logger.warning(f"Could not fetch notifications: {e}")
        return []


async def mark_notifications_read(user_id: str, notification_ids: list[str] | None = None) -> int:
    """Mark notifications as read. If no IDs given, mark all as read."""
    try:
        query = (
            db_admin.table("notifications")
            .update({"read": True, "read_at": datetime.now(UTC).isoformat()})
            .eq("user_id", user_id)
        )
        if notification_ids:
            query = query.in_("id", notification_ids)
        resp = await query.async_execute()
        return len(resp.data or [])
    except Exception as e:
        logger.warning(f"Could not mark notifications read: {e}")
        return 0


async def get_unread_count(user_id: str) -> int:
    """Get count of unread notifications."""
    try:
        resp = (
            await db_admin.table("notifications")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("read", False)
            .async_execute()
        )
        return resp.count or 0
    except Exception:
        return 0


# ── Convenience: notify on request status change ──────────────────────────

NOTIFICATION_TEMPLATES = {
    "approved": {
        "title": "✅ Request Approved",
        "message": "Your request for {resource_type} has been approved by an administrator.",
        "type": "success",
    },
    "rejected": {
        "title": "❌ Request Rejected",
        "message": "Your request for {resource_type} has been rejected. Reason: {reason}",
        "type": "error",
    },
    "assigned": {
        "title": "👤 Request Assigned",
        "message": "Your request for {resource_type} has been assigned to a responder and is being processed.",
        "type": "info",
    },
    "in_progress": {
        "title": "🚚 Request In Progress",
        "message": "Your request for {resource_type} is now being fulfilled. Help is on the way!",
        "type": "info",
    },
    "completed": {
        "title": "🎉 Request Completed",
        "message": "Your request for {resource_type} has been completed. We hope this helped!",
        "type": "success",
    },
}


async def notify_request_status_change(
    request_id: str,
    victim_id: str,
    resource_type: str,
    old_status: str,
    new_status: str,
    admin_id: str | None = None,
    rejection_reason: str | None = None,
    admin_note: str | None = None,
    actor_role: str | None = None,
):
    """Send notification to victim and create audit trail entry for a status change."""
    template = NOTIFICATION_TEMPLATES.get(new_status)
    if template:
        msg = template["message"].format(
            resource_type=resource_type,
            reason=rejection_reason or "Not specified",
        )
        await create_notification(
            user_id=victim_id,
            title=template["title"],
            message=msg,
            notification_type=template["type"],
            related_id=request_id,
            related_type="request",
        )

    # Build audit details
    details = rejection_reason if new_status == "rejected" else None
    if admin_note:
        details = f"{details or ''}\n[Admin Note] {admin_note}".strip()

    # Resolve actor role: use explicit param, fall back to "admin" if admin_id, else "system"
    resolved_role = actor_role or ("admin" if admin_id else "system")

    # Audit trail
    await create_audit_entry(
        request_id=request_id,
        action=f"status_changed_to_{new_status}",
        actor_id=admin_id,
        actor_role=resolved_role,
        old_status=old_status,
        new_status=new_status,
        details=details,
    )


# ── Cross-role bulk notification helpers ──────────────────────────────────


async def _get_users_by_role(role: str) -> list[dict]:
    """Return list of user dicts (id, full_name) for the given role.
    Cached in-memory for 5 minutes to reduce database reads.
    """
    from app.core.query_cache import get_users_by_role_cached, set_users_by_role_cached

    cached = get_users_by_role_cached(role)
    if cached is not None:
        return cached

    try:
        resp = await db_admin.table("users").select("id, full_name").eq("role", role).limit(500).async_execute()
        result = resp.data or []
        set_users_by_role_cached(role, result)
        return result
    except Exception as e:
        logger.warning(f"Could not fetch {role} users: {e}")
        return []


async def notify_all_admins(
    title: str,
    message: str,
    notification_type: str = "info",
    related_id: str | None = None,
    related_type: str | None = None,
):
    """Send a notification to every admin user."""
    admins = await _get_users_by_role("admin")
    for admin in admins:
        await create_notification(
            user_id=admin["id"],
            title=title,
            message=message,
            notification_type=notification_type,
            related_id=related_id,
            related_type=related_type,
        )


async def notify_all_by_role(
    role: str,
    title: str,
    message: str,
    notification_type: str = "info",
    related_id: str | None = None,
    related_type: str | None = None,
):
    """Send a notification to every user of the given role (batch insert)."""
    users = await _get_users_by_role(role)
    if not users:
        return

    type_to_priority = {
        "info": "low",
        "success": "medium",
        "warning": "high",
        "error": "critical",
        "request_update": "medium",
    }

    records = []
    for u in users:
        records.append(
            {
                "user_id": u["id"],
                "title": title,
                "message": message,
                "priority": type_to_priority.get(notification_type, "medium"),
                "read": False,
                "data": {
                    "type": notification_type,
                    "related_id": related_id,
                    "related_type": related_type,
                },
                "action_url": f"/requests/{related_id}" if related_id else None,
            }
        )

    # Single batch insert instead of N individual writes
    if records:
        try:
            await db_admin.table("notifications").insert(records).async_execute()
        except Exception as e:
            logger.warning("Batch notification insert failed: %s", e)


async def notify_user(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "info",
    related_id: str | None = None,
    related_type: str | None = None,
):
    """Convenience wrapper – notify a single user."""
    await create_notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        related_id=related_id,
        related_type=related_type,
    )


def generate_delivery_code() -> str:
    """Generate a 6-character alphanumeric delivery confirmation code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
