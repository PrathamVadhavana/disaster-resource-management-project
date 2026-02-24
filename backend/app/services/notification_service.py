"""
Notifications & Audit Trail service.
Handles creating notifications for users when request statuses change,
and recording audit trail entries for all request lifecycle events.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict
import logging
import traceback

from app.database import supabase_admin

logger = logging.getLogger("notification_service")


async def create_notification(
    user_id: str,
    title: str,
    message: str,
    notification_type: str = "info",     # info, success, warning, error, request_update
    related_id: Optional[str] = None,    # request_id, disaster_id, etc.
    related_type: Optional[str] = None,  # request, disaster, resource
) -> Optional[Dict]:
    """Create a notification for a user. Stored in DB for persistence."""
    try:
        record = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "related_id": related_id,
            "related_type": related_type,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = supabase_admin.table("notifications").insert(record).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        # Table might not exist yet — that's OK, we log and continue
        logger.warning(f"Could not create notification (table may not exist): {e}")
        return None


async def create_audit_entry(
    request_id: str,
    action: str,
    actor_id: Optional[str] = None,
    actor_role: str = "system",
    old_status: Optional[str] = None,
    new_status: Optional[str] = None,
    details: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Optional[Dict]:
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
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = supabase_admin.table("request_audit_log").insert(record).execute()
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.warning(f"Could not create audit entry (table may not exist): {e}")
        return None


async def get_request_audit_trail(request_id: str) -> List[Dict]:
    """Get the full audit trail for a request."""
    try:
        resp = (
            supabase_admin.table("request_audit_log")
            .select("*")
            .eq("request_id", request_id)
            .order("created_at", desc=False)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning(f"Could not fetch audit trail: {e}")
        return []


async def get_user_notifications(
    user_id: str,
    unread_only: bool = False,
    limit: int = 50,
) -> List[Dict]:
    """Get notifications for a user."""
    try:
        query = (
            supabase_admin.table("notifications")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if unread_only:
            query = query.eq("is_read", False)
        resp = query.execute()
        return resp.data or []
    except Exception as e:
        logger.warning(f"Could not fetch notifications: {e}")
        return []


async def mark_notifications_read(user_id: str, notification_ids: Optional[List[str]] = None) -> int:
    """Mark notifications as read. If no IDs given, mark all as read."""
    try:
        query = supabase_admin.table("notifications").update({"is_read": True}).eq("user_id", user_id)
        if notification_ids:
            query = query.in_("id", notification_ids)
        resp = query.execute()
        return len(resp.data or [])
    except Exception as e:
        logger.warning(f"Could not mark notifications read: {e}")
        return 0


async def get_unread_count(user_id: str) -> int:
    """Get count of unread notifications."""
    try:
        resp = (
            supabase_admin.table("notifications")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("is_read", False)
            .execute()
        )
        return resp.count or 0
    except Exception as e:
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
    admin_id: Optional[str] = None,
    rejection_reason: Optional[str] = None,
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

    # Audit trail
    await create_audit_entry(
        request_id=request_id,
        action=f"status_changed_to_{new_status}",
        actor_id=admin_id,
        actor_role="admin" if admin_id else "system",
        old_status=old_status,
        new_status=new_status,
        details=rejection_reason if new_status == "rejected" else None,
    )
