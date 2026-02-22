"""
Alert & Notification service.

Dispatches critical-severity alerts to NGOs/admins via:
  - Email (SendGrid free tier — 100 emails/day)
  - Log-based fallback when no email provider is configured

Logs every notification attempt in the alert_notifications table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from app.core.config import ingestion_config as cfg
from app.database import supabase_admin

logger = logging.getLogger("ingestion.alerts")


class AlertNotificationService:
    """Dispatches critical-severity notifications via email (SendGrid free tier)."""

    # ── public API ──────────────────────────────────────────────────

    async def evaluate_and_notify(
        self,
        event: Dict[str, Any],
        disaster_id: Optional[str] = None,
        prediction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        If the event or prediction is critical, send notifications
        to all NGO/admin contacts and log them.
        """
        severity = event.get("severity", "low")
        if severity != cfg.ALERT_SEVERITY_THRESHOLD:
            return []

        recipients = await self._get_ngo_recipients()
        if not recipients:
            logger.warning("No NGO/admin recipients configured for alerts")
            return []

        notifications: List[Dict[str, Any]] = []
        for recip in recipients:
            notif = await self._send(
                event=event,
                disaster_id=disaster_id,
                prediction_id=prediction_id,
                recipient=recip,
            )
            notifications.append(notif)

        return notifications

    # ── private ─────────────────────────────────────────────────────

    async def _get_ngo_recipients(self) -> List[Dict[str, Any]]:
        """Query users with role ngo or admin who have email/phone."""
        resp = (
            supabase_admin.table("users")
            .select("id, email, phone, role, full_name")
            .in_("role", ["ngo", "admin"])
            .execute()
        )
        return resp.data or []

    async def _send(
        self,
        event: Dict[str, Any],
        disaster_id: Optional[str],
        prediction_id: Optional[str],
        recipient: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Attempt email dispatch for one recipient, with log fallback."""
        notif_id = str(uuid4())
        subject = f"🚨 CRITICAL ALERT: {event.get('title', 'Disaster Event')}"
        body = self._build_body(event)

        notif_base = {
            "id": notif_id,
            "event_id": event.get("id"),
            "disaster_id": disaster_id,
            "prediction_id": prediction_id,
            "recipient": recipient.get("email", ""),
            "recipient_role": recipient.get("role", "ngo"),
            "subject": subject,
            "body": body,
            "severity": event.get("severity", "critical"),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Try email via SendGrid (free tier: 100 emails/day)
        email = recipient.get("email")
        if email and cfg.SENDGRID_API_KEY:
            result = await self._send_email(email, subject, body)
            notif_base["channel"] = "email"
            notif_base["external_ref"] = result.get("message_id")
            notif_base["status"] = result.get("status", "failed")
            notif_base["error_message"] = result.get("error")
            if result.get("status") == "sent":
                notif_base["sent_at"] = datetime.now(timezone.utc).isoformat()
        else:
            # Log-based fallback — alert is persisted in DB for dashboard visibility
            notif_base["channel"] = "log"
            notif_base["status"] = "logged"
            notif_base["error_message"] = None
            logger.warning(
                "CRITICAL ALERT (log-only, no SendGrid key): %s — recipient: %s",
                subject, email or "(no email)",
            )

        # Persist notification log
        supabase_admin.table("alert_notifications").insert(notif_base).execute()
        return notif_base

    # ── Email via SendGrid ──────────────────────────────────────────

    async def _send_email(self, to_email: str, subject: str, body: str) -> Dict[str, Any]:
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {cfg.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": cfg.SENDGRID_FROM_EMAIL, "name": "Disaster Management Alerts"},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": body},
                {"type": "text/html", "value": self._html_body(subject, body)},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201, 202):
                msg_id = resp.headers.get("X-Message-Id", "")
                logger.info("Email sent to %s (msg_id=%s)", to_email, msg_id)
                return {"status": "sent", "message_id": msg_id}
            else:
                err = resp.text[:300]
                logger.error("SendGrid error %d: %s", resp.status_code, err)
                return {"status": "failed", "error": err}
        except Exception as exc:
            logger.exception("SendGrid request failed")
            return {"status": "failed", "error": str(exc)}

    # ── Body formatting ─────────────────────────────────────────────

    def _build_body(self, event: Dict[str, Any]) -> str:
        lines = [
            f"CRITICAL DISASTER ALERT",
            f"",
            f"Event: {event.get('title', 'Unknown')}",
            f"Severity: {event.get('severity', 'N/A').upper()}",
            f"Type: {event.get('event_type', 'N/A')}",
        ]
        if event.get("latitude") and event.get("longitude"):
            lines.append(f"Location: {event.get('latitude'):.4f}, {event.get('longitude'):.4f}")
        if event.get("location_name"):
            lines.append(f"Place: {event.get('location_name')}")
        if event.get("description"):
            lines.append(f"")
            lines.append(event["description"][:500])
        lines.append("")
        lines.append("Please log in to the Disaster Management Platform for full details.")
        return "\n".join(lines)

    def _html_body(self, subject: str, plain_body: str) -> str:
        escaped = plain_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #dc2626; color: white; padding: 16px; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0;">{subject}</h2>
            </div>
            <div style="background: #fef2f2; padding: 20px; border: 1px solid #fecaca; border-radius: 0 0 8px 8px;">
                <pre style="white-space: pre-wrap; font-family: Arial, sans-serif; font-size: 14px;">{escaped}</pre>
            </div>
        </div>
        """
