"""
SLA (Service Level Agreement) Tracking & Auto-Escalation Service.

Monitors resource requests for time-based SLA violations:
- Approved requests with no NGO availability submission within configurable window → escalate priority
- Assigned requests not moved to in_progress within configurable window → alert admin
- Configurable SLA windows via platform_settings

Runs as a periodic background task (every 10 minutes).
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from app.database import db_admin
from app.services.notification_service import (
    notify_all_admins,
    notify_all_by_role,
    create_audit_entry,
)

logger = logging.getLogger("sla_service")

# Default SLA windows (hours) — overridden by platform_settings
DEFAULT_APPROVED_SLA_HOURS = 2.0
DEFAULT_ASSIGNED_SLA_HOURS = 4.0
DEFAULT_IN_PROGRESS_SLA_HOURS = 24.0

# Priority escalation order
PRIORITY_ESCALATION = {
    "low": "medium",
    "medium": "high",
    "high": "critical",
    "critical": "critical",  # can't escalate further
}


async def _get_sla_settings() -> Dict:
    """Fetch SLA configuration from platform_settings."""
    try:
        resp = (
            await db_admin.table("platform_settings")
            .select("*")
            .eq("id", 1)
            .maybe_single()
            .async_execute()
        )
        if resp.data:
            return {
                "approved_sla_hours": resp.data.get("approved_sla_hours", DEFAULT_APPROVED_SLA_HOURS),
                "assigned_sla_hours": resp.data.get("assigned_sla_hours", DEFAULT_ASSIGNED_SLA_HOURS),
                "in_progress_sla_hours": resp.data.get("in_progress_sla_hours", DEFAULT_IN_PROGRESS_SLA_HOURS),
                "sla_enabled": resp.data.get("sla_enabled", True),
            }
    except Exception as e:
        logger.warning("Could not fetch SLA settings: %s", e)
    return {
        "approved_sla_hours": DEFAULT_APPROVED_SLA_HOURS,
        "assigned_sla_hours": DEFAULT_ASSIGNED_SLA_HOURS,
        "in_progress_sla_hours": DEFAULT_IN_PROGRESS_SLA_HOURS,
        "sla_enabled": True,
    }


def _parse_dt(val) -> Optional[datetime]:
    """Parse a datetime from the database (string or datetime)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def check_sla_violations():
    """Check all active requests for SLA violations and take action."""
    settings = await _get_sla_settings()
    if not settings.get("sla_enabled", True):
        return

    now = datetime.now(timezone.utc)

    # 1. Check approved requests with no NGO response
    await _check_approved_sla(now, settings["approved_sla_hours"])

    # 2. Check assigned requests not moved to in_progress
    await _check_assigned_sla(now, settings["assigned_sla_hours"])

    # 3. Check in_progress requests stalled
    await _check_in_progress_sla(now, settings["in_progress_sla_hours"])


async def _check_approved_sla(now: datetime, sla_hours: float):
    """Escalate priority of approved requests that haven't received NGO availability."""
    try:
        cutoff = (now - timedelta(hours=sla_hours)).isoformat()
        resp = (
            await db_admin.table("resource_requests")
            .select("id, priority, status, updated_at, resource_type, sla_escalated_at")
            .in_("status", ["approved"])
            .lte("updated_at", cutoff)
            .async_execute()
        )
        for req in resp.data or []:
            # Skip if already escalated in the last SLA window
            last_escalated = _parse_dt(req.get("sla_escalated_at"))
            if last_escalated and (now - last_escalated).total_seconds() < sla_hours * 3600:
                continue

            current_priority = req.get("priority", "medium")
            new_priority = PRIORITY_ESCALATION.get(current_priority, current_priority)

            if new_priority != current_priority:
                # Escalate priority
                await db_admin.table("resource_requests").update({
                    "priority": new_priority,
                    "sla_escalated_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }).eq("id", req["id"]).async_execute()

                logger.info(
                    "SLA escalation: request %s priority %s → %s (approved >%sh without NGO response)",
                    req["id"][:8], current_priority, new_priority, sla_hours,
                )

                # Re-notify NGOs/donors
                await notify_all_by_role(
                    role="ngo",
                    title="⚠️ SLA Escalation — Urgent Request",
                    message=f"Request for {req.get('resource_type', 'resources')} escalated to {new_priority} priority (no response in {sla_hours}h). Please review.",
                    notification_type="warning",
                    related_id=req["id"],
                    related_type="request",
                )
                await notify_all_by_role(
                    role="donor",
                    title="⚠️ SLA Escalation — Urgent Request",
                    message=f"Request for {req.get('resource_type', 'resources')} escalated to {new_priority} priority. Donor support needed.",
                    notification_type="warning",
                    related_id=req["id"],
                    related_type="request",
                )

                await create_audit_entry(
                    request_id=req["id"],
                    action="sla_priority_escalated",
                    actor_role="system",
                    old_status="approved",
                    new_status="approved",
                    details=f"Priority auto-escalated {current_priority} → {new_priority} (no NGO response in {sla_hours}h)",
                )
            else:
                # Already at critical — just alert admins
                await notify_all_admins(
                    title="🚨 Critical SLA Breach",
                    message=f"Critical-priority request for {req.get('resource_type', 'resources')} has been approved for >{sla_hours}h with no responder. Immediate action needed.",
                    notification_type="error",
                    related_id=req["id"],
                    related_type="request",
                )
    except Exception as e:
        logger.error("SLA check (approved) failed: %s", e)


async def _check_assigned_sla(now: datetime, sla_hours: float):
    """Alert admins when assigned requests haven't moved to in_progress."""
    try:
        cutoff = (now - timedelta(hours=sla_hours)).isoformat()
        resp = (
            await db_admin.table("resource_requests")
            .select("id, assigned_to, resource_type, updated_at, sla_admin_alerted")
            .eq("status", "assigned")
            .lte("updated_at", cutoff)
            .async_execute()
        )
        for req in resp.data or []:
            if req.get("sla_admin_alerted"):
                continue

            await db_admin.table("resource_requests").update({
                "sla_admin_alerted": True,
            }).eq("id", req["id"]).async_execute()

            await notify_all_admins(
                title="⏰ Assigned Request Stalled",
                message=f"Request {req['id'][:8]}... for {req.get('resource_type', 'resources')} has been assigned for >{sla_hours}h without moving to in_progress. Consider reassignment.",
                notification_type="warning",
                related_id=req["id"],
                related_type="request",
            )

            await create_audit_entry(
                request_id=req["id"],
                action="sla_assigned_stall_alert",
                actor_role="system",
                old_status="assigned",
                new_status="assigned",
                details=f"Admin alerted: assigned request stalled for >{sla_hours}h",
            )
    except Exception as e:
        logger.error("SLA check (assigned) failed: %s", e)


async def _check_in_progress_sla(now: datetime, sla_hours: float):
    """Alert admins when in_progress requests haven't been delivered."""
    try:
        cutoff = (now - timedelta(hours=sla_hours)).isoformat()
        resp = (
            await db_admin.table("resource_requests")
            .select("id, assigned_to, resource_type, updated_at, sla_delivery_alerted")
            .eq("status", "in_progress")
            .lte("updated_at", cutoff)
            .async_execute()
        )
        for req in resp.data or []:
            if req.get("sla_delivery_alerted"):
                continue

            await db_admin.table("resource_requests").update({
                "sla_delivery_alerted": True,
            }).eq("id", req["id"]).async_execute()

            await notify_all_admins(
                title="🚛 Delivery Overdue",
                message=f"Request {req['id'][:8]}... has been in_progress for >{sla_hours}h without delivery. Follow up with assigned responder.",
                notification_type="warning",
                related_id=req["id"],
                related_type="request",
            )
    except Exception as e:
        logger.error("SLA check (in_progress) failed: %s", e)


async def sla_check_loop(interval_minutes: int = 30):
    """Background loop that checks SLA violations periodically."""
    # Delay initial check to let uvicorn finish startup
    await asyncio.sleep(30)
    logger.info("SLA monitoring started (interval: %d min)", interval_minutes)
    while True:
        try:
            await check_sla_violations()
        except asyncio.CancelledError:
            logger.info("SLA monitoring stopped")
            break
        except Exception as e:
            logger.error("SLA check loop error: %s", e)
        await asyncio.sleep(interval_minutes * 60)
