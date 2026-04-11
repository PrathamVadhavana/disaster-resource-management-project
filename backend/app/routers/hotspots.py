"""
Hotspot Clusters API Router — GeoJSON endpoint for the disaster map.

Serves active DBSCAN-detected hotspot clusters as a GeoJSON
FeatureCollection suitable for rendering as a heatmap / polygon
layer in Leaflet or Mapbox GL JS.

Also provides management endpoints for status updates, resource
assignment, alert dispatch, and AI-powered insights.
"""

import logging
import uuid
from collections import Counter
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import ingestion_config as cfg
from app.database import db_admin
from app.dependencies import get_current_user

logger = logging.getLogger("hotspots_router")

router = APIRouter()

# ── Pydantic schemas ─────────────────────────────────────────────────────────


class StatusUpdatePayload(BaseModel):
    status: str = Field(..., description="New status: active, monitoring, resolved")


class AssignResourcePayload(BaseModel):
    resource_type: str = Field(..., description="e.g. volunteers, supplies, ngo_team")
    quantity: int = Field(1, ge=1)
    assigned_to: str | None = Field(None, description="User/org ID to assign to")
    notes: str | None = None


class SendAlertPayload(BaseModel):
    channel: str = Field("in_app", description="in_app, email")
    recipient_role: str = Field("ngo", description="ngo, volunteer, admin")
    subject: str | None = None
    body: str | None = None
    severity: str = Field("high")


async def _send_sendgrid_email(to_email: str, subject: str, body: str) -> dict:
    """Send a single email via SendGrid REST API."""
    if not cfg.SENDGRID_API_KEY:
        return {
            "status": "failed",
            "error": "SendGrid is not configured (missing SENDGRID_API_KEY).",
        }

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {
            "email": cfg.SENDGRID_FROM_EMAIL,
            "name": "Disaster Management Alerts",
        },
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": body},
            {
                "type": "text/html",
                "value": f'<pre style="white-space:pre-wrap;font-family:Arial">{body}</pre>',
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={
                    "Authorization": f"Bearer {cfg.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code in (200, 201, 202):
            return {
                "status": "sent",
                "message_id": resp.headers.get("X-Message-Id", ""),
            }
        return {"status": "failed", "error": resp.text[:300]}
    except Exception as exc:
        logger.error("SendGrid email send failed for %s: %s", to_email, exc)
        return {"status": "failed", "error": str(exc)}


# ── Existing endpoints ───────────────────────────────────────────────────────


@router.get(
    "",
    summary="Active hotspot clusters (GeoJSON)",
    response_class=JSONResponse,
)
async def get_hotspots(
    status: str | None = Query("active", description="Filter by cluster status"),
    min_priority: str | None = Query(
        None, description="Minimum priority label (low/medium/high/critical)"
    ),
    user: dict = Depends(get_current_user),
):
    """Return all hotspot clusters as a **GeoJSON FeatureCollection**.

    Each Feature contains:
    - ``geometry``: convex-hull polygon boundary of the cluster
    - ``properties``: centroid, request_count, total_people,
      dominant_type, avg_priority, priority_label, detected_at

    Query params:
    - ``status``: ``active`` (default), ``monitoring``, ``resolved``, or ``all``
    - ``min_priority``: only return clusters at or above this priority
    """
    from ml.clustering_service import build_geojson_feature_collection

    try:
        fc = build_geojson_feature_collection()
    except Exception as exc:
        logger.error("Failed to build GeoJSON: %s", exc)
        raise HTTPException(status_code=500, detail="Could not retrieve hotspot data")

    # Optional client-side filters (applied after fetch)
    priority_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}

    if status and status != "all":
        fc["features"] = [
            f for f in fc["features"] if f["properties"].get("status") == status
        ]

    if min_priority and min_priority in priority_order:
        threshold = priority_order[min_priority]
        fc["features"] = [
            f
            for f in fc["features"]
            if priority_order.get(f["properties"].get("priority_label", "low"), 0)
            >= threshold
        ]

    return JSONResponse(
        content=fc,
        media_type="application/geo+json",
    )


@router.get(
    "/{cluster_id}",
    summary="Single hotspot cluster detail",
)
async def get_hotspot_detail(
    cluster_id: str,
    user: dict = Depends(get_current_user),
):
    """Return a single hotspot cluster by ID with full request details."""
    try:
        resp = (
            await db_admin.table("hotspot_clusters")
            .select("*")
            .eq("id", cluster_id)
            .async_execute()
        )
        rows = resp.data or []
    except Exception as exc:
        logger.error("Failed to fetch cluster %s: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not retrieve cluster")

    if not rows:
        raise HTTPException(status_code=404, detail="Hotspot cluster not found")

    cluster = rows[0]

    # Optionally resolve the member request summaries
    request_ids = cluster.get("request_ids", [])
    member_requests = []
    if request_ids:
        try:
            for rid in request_ids[:50]:  # cap to avoid huge queries
                r_resp = (
                    await db_admin.table("resource_requests")
                    .select(
                        "id, resource_type, priority, status, latitude, longitude, head_count, description"
                    )
                    .eq("id", rid)
                    .async_execute()
                )
                if r_resp.data:
                    member_requests.append(r_resp.data[0])
        except Exception as exc:
            logger.warning("Could not fetch member requests: %s", exc)

    # Serialize datetimes
    for key in ("detected_at", "resolved_at", "created_at", "updated_at"):
        val = cluster.get(key)
        if val and hasattr(val, "isoformat"):
            cluster[key] = val.isoformat()

    cluster["member_requests"] = member_requests

    return JSONResponse(content=cluster)


@router.post(
    "/trigger",
    summary="Manually trigger DBSCAN clustering",
)
async def trigger_clustering(
    user: dict = Depends(get_current_user),
):
    """Admin/debug endpoint to manually trigger a clustering cycle."""
    if user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")

    from ml.clustering_service import run_clustering

    clusters = await run_clustering()
    return JSONResponse(
        content={
            "message": f"Clustering complete — {len(clusters)} hotspots detected",
            "cluster_count": len(clusters),
            "clusters": [
                {
                    "id": c.get("id"),
                    "centroid": [c["centroid_lat"], c["centroid_lon"]],
                    "request_count": c["request_count"],
                    "priority_label": c["priority_label"],
                }
                for c in clusters
            ],
        }
    )


# ── New management endpoints ─────────────────────────────────────────────────


@router.patch(
    "/{cluster_id}/status",
    summary="Update hotspot cluster status",
)
async def update_hotspot_status(
    cluster_id: str,
    payload: StatusUpdatePayload,
    user: dict = Depends(get_current_user),
):
    """Change a hotspot status (active → monitoring → resolved)."""
    if user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")

    valid_statuses = {"active", "monitoring", "resolved"}
    if payload.status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Status must be one of {valid_statuses}"
        )

    now_iso = datetime.now(UTC).isoformat()
    update_data: dict = {"status": payload.status, "updated_at": now_iso}
    if payload.status == "resolved":
        update_data["resolved_at"] = now_iso

    try:
        await (
            db_admin.table("hotspot_clusters")
            .update(update_data)
            .eq("id", cluster_id)
            .async_execute()
        )
    except Exception as exc:
        logger.error("Failed to update hotspot %s status: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not update hotspot status")

    return JSONResponse(
        content={"message": f"Hotspot {cluster_id} status updated to {payload.status}"}
    )


@router.post(
    "/{cluster_id}/assign",
    summary="Assign resources to a hotspot",
)
async def assign_hotspot_resources(
    cluster_id: str,
    payload: AssignResourcePayload,
    user: dict = Depends(get_current_user),
):
    """Assign volunteers, NGOs, or supplies to a hotspot cluster.

    This endpoint:
    1. Verifies the cluster exists and fetches its member request_ids
    2. Updates all pending/approved resource_requests in the cluster to 'assigned'
    3. Logs the allocation to allocation_log
    4. Notifies affected victims and creates admin notifications
    """
    if user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")

    # ── Valid resource types for the resource_requests table ──
    _VALID_RT = {
        "Food", "Water", "Medical", "Shelter", "Clothing",
        "Financial Aid", "Evacuation", "Volunteers", "Custom", "Multiple",
    }
    _RT_ALIAS = {
        "Medical Team": "Medical", "Food Supplies": "Food",
        "Shelter Materials": "Shelter", "Evacuation Support": "Evacuation",
        "NGO Team": "Volunteers",
    }

    # Verify the cluster exists and get its request_ids
    try:
        resp = (
            await db_admin.table("hotspot_clusters")
            .select("id, centroid_lat, centroid_lon, dominant_type, request_ids")
            .eq("id", cluster_id)
            .async_execute()
        )
        cluster_rows = resp.data or []
        if not cluster_rows:
            raise HTTPException(status_code=404, detail="Hotspot cluster not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch hotspot %s: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not verify hotspot")

    cluster = cluster_rows[0]
    request_ids = cluster.get("request_ids") or []
    admin_id = user.get("id") or user.get("sub")
    now_iso = datetime.now(UTC).isoformat()

    # Resolve resource type to a valid DB value
    resolved_type = _RT_ALIAS.get(payload.resource_type, payload.resource_type)
    if resolved_type not in _VALID_RT:
        resolved_type = "Custom"

    # ── Log the allocation ──
    allocation_record = {
        "id": str(uuid.uuid4()),
        "resource_type": resolved_type,
        "quantity": payload.quantity,
        "created_at": now_iso,
    }

    try:
        await db_admin.table("allocation_log").insert(allocation_record).async_execute()
    except Exception as exc:
        logger.error("Failed to log allocation for hotspot %s: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not log resource allocation")

    # ── Update member resource_requests to 'assigned' status ──
    requests_updated = 0
    victims_notified = 0

    if request_ids:
        for rid in request_ids[:50]:  # cap to avoid huge operations
            try:
                # Fetch the request to check its current state
                r_resp = (
                    await db_admin.table("resource_requests")
                    .select("id, status, victim_id, resource_type, priority")
                    .eq("id", rid)
                    .maybe_single()
                    .async_execute()
                )
                if not r_resp.data:
                    continue

                req = r_resp.data
                current_status = req.get("status", "")

                # Only update requests that are pending or approved
                if current_status not in ("pending", "approved"):
                    continue

                # Build update fields
                update_fields = {
                    "status": "approved" if current_status == "pending" else "assigned",
                    "updated_at": now_iso,
                    "admin_note": (
                        f"Resources assigned via Hotspot #{cluster_id[:8]}: "
                        f"{payload.quantity}x {payload.resource_type}"
                        f"{(' — ' + payload.notes) if payload.notes else ''}"
                    ),
                }

                # If there's a specific assignee, assign to them
                if payload.assigned_to:
                    update_fields["status"] = "assigned"
                    update_fields["assigned_to"] = payload.assigned_to

                # Auto-update fulfillment_pct based on status
                _STATUS_PCT = {"approved": 10, "assigned": 25}
                update_fields["fulfillment_pct"] = _STATUS_PCT.get(
                    update_fields["status"], 0
                )

                # Sanitize resource_type if it's invalid
                existing_rt = req.get("resource_type", "Custom")
                if existing_rt not in _VALID_RT:
                    # Try keyword-based resolution
                    lower = existing_rt.lower()
                    _KW = {
                        "Food": ["rice", "wheat", "flour", "dal", "food", "meal", "ration"],
                        "Water": ["water", "drink", "purif"],
                        "Medical": ["medic", "first aid", "medicine", "health"],
                        "Shelter": ["shelter", "tent", "blanket"],
                        "Clothing": ["cloth", "garment", "shirt"],
                    }
                    fixed = "Custom"
                    for cat, kws in _KW.items():
                        if any(k in lower for k in kws):
                            fixed = cat
                            break
                    update_fields["resource_type"] = fixed

                await (
                    db_admin.table("resource_requests")
                    .update(update_fields)
                    .eq("id", rid)
                    .async_execute()
                )
                requests_updated += 1

                # ── Notify the victim ──
                victim_id = req.get("victim_id")
                if victim_id:
                    try:
                        notif = {
                            "id": str(uuid.uuid4()),
                            "user_id": victim_id,
                            "title": "📦 Resources Assigned to Your Request",
                            "message": (
                                f"An admin has assigned {payload.quantity}x {payload.resource_type} "
                                f"to your {req.get('priority', 'medium')} priority request. "
                                f"Your request status has been updated."
                            ),
                            "priority": "high",
                            "data": {
                                "type": "hotspot_resource_assignment",
                                "request_id": rid,
                                "hotspot_id": cluster_id,
                                "resource_type": resolved_type,
                                "quantity": payload.quantity,
                            },
                            "created_at": now_iso,
                        }
                        await db_admin.table("notifications").insert(notif).async_execute()
                        victims_notified += 1
                    except Exception as ne:
                        logger.warning("Failed to notify victim %s: %s", victim_id, ne)

                # ── Log to audit trail ──
                try:
                    audit = {
                        "id": str(uuid.uuid4()),
                        "request_id": rid,
                        "action": f"status_changed_to_{update_fields['status']}",
                        "actor_id": admin_id,
                        "actor_role": "admin",
                        "old_status": current_status,
                        "new_status": update_fields["status"],
                        "details": (
                            f"Resources assigned via hotspot cluster #{cluster_id[:8]}: "
                            f"{payload.quantity}x {payload.resource_type}"
                        ),
                        "created_at": now_iso,
                    }
                    await db_admin.table("request_audit_log").insert(audit).async_execute()
                except Exception as ae:
                    logger.warning("Failed to create audit log for request %s: %s", rid, ae)

            except Exception as exc:
                logger.warning("Failed to update request %s for hotspot %s: %s", rid, cluster_id, exc)

    # ── Create admin notification ──
    try:
        notif = {
            "id": str(uuid.uuid4()),
            "user_id": admin_id,
            "title": "Resources assigned to Hotspot",
            "message": (
                f"{payload.quantity}x {payload.resource_type} assigned to hotspot {cluster_id[:8]}. "
                f"{requests_updated} request(s) updated, {victims_notified} victim(s) notified."
            ),
            "priority": "high",
            "data": {
                "hotspot_id": cluster_id,
                "resource_type": resolved_type,
                "quantity": payload.quantity,
                "requests_updated": requests_updated,
            },
            "created_at": now_iso,
        }
        await db_admin.table("notifications").insert(notif).async_execute()
    except Exception as exc:
        logger.warning("Failed to create assignment notification: %s", exc)

    return JSONResponse(
        content={
            "message": (
                f"Assigned {payload.quantity}x {payload.resource_type} to hotspot {cluster_id[:8]}. "
                f"{requests_updated} request(s) updated, {victims_notified} victim(s) notified."
            ),
            "allocation_id": allocation_record["id"],
            "requests_updated": requests_updated,
            "victims_notified": victims_notified,
        }
    )


@router.post(
    "/{cluster_id}/alert",
    summary="Send alert for a hotspot",
)
async def send_hotspot_alert(
    cluster_id: str,
    payload: SendAlertPayload,
    user: dict = Depends(get_current_user),
):
    """Send alert notifications to NGOs/volunteers about a hotspot."""
    if user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")

    # Fetch cluster for context
    try:
        resp = (
            await db_admin.table("hotspot_clusters")
            .select("*")
            .eq("id", cluster_id)
            .async_execute()
        )
        cluster_rows = resp.data or []
    except Exception as exc:
        logger.error("Failed to fetch hotspot %s for alerting: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not fetch hotspot data")

    if not cluster_rows:
        raise HTTPException(status_code=404, detail="Hotspot cluster not found")

    cluster = cluster_rows[0]

    # Build the alert subject/body
    subject = (
        payload.subject
        or f"⚠️ Hotspot Alert — {cluster.get('priority_label', 'high').upper()} priority zone"
    )
    body = payload.body or (
        f"A {cluster.get('priority_label', 'high')} priority hotspot with "
        f"{cluster.get('request_count', 0)} events affecting "
        f"{cluster.get('total_people', 0)} people has been flagged. "
        f"Dominant need: {cluster.get('dominant_type', 'Unknown')}. "
        f"Location: ({cluster.get('centroid_lat', 0):.4f}, {cluster.get('centroid_lon', 0):.4f})"
    )

    valid_roles = {"ngo", "volunteer", "admin"}
    if payload.recipient_role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"recipient_role must be one of {sorted(valid_roles)}",
        )

    valid_channels = {"in_app", "email"}
    if payload.channel not in valid_channels:
        raise HTTPException(
            status_code=400,
            detail=f"channel must be one of {sorted(valid_channels)}",
        )

    if payload.channel == "email" and not cfg.SENDGRID_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Email channel is not configured: missing SENDGRID_API_KEY.",
        )

    # Find recipients based on role
    try:
        user_resp = await (
            db_admin.table("users")
            .select("id, email, full_name, role")
            .eq("role", payload.recipient_role)
            .limit(50)
            .async_execute()
        )
        recipients = user_resp.data or []
    except Exception as exc:
        logger.error("Failed to fetch recipients: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to fetch recipients for alert"
        )

    if not recipients:
        raise HTTPException(
            status_code=404,
            detail=f"No recipients found for role '{payload.recipient_role}'.",
        )

    now_iso = datetime.now(UTC).isoformat()

    alerts_sent = 0
    notifications_created = 0
    ngo_alerts_created = 0

    selected_recipients = recipients[:20]

    if payload.channel == "email":
        recipients_with_email = [r for r in selected_recipients if r.get("email")]
        if not recipients_with_email:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No valid recipient emails found for role '{payload.recipient_role}'. "
                    "Please ensure users in this role have email addresses."
                ),
            )

    alert_rows = []
    email_failures = 0
    for recipient in selected_recipients:
        recipient_email = recipient.get("email")
        status = "sent"
        sent_at = now_iso
        error_message = None
        external_ref = None

        if payload.channel == "email":
            if not recipient_email:
                status = "failed"
                sent_at = None
                error_message = "Recipient has no email"
                email_failures += 1
            else:
                result = await _send_sendgrid_email(recipient_email, subject, body)
                status = result.get("status", "failed")
                if status != "sent":
                    sent_at = None
                    error_message = result.get("error")
                    email_failures += 1
                external_ref = result.get("message_id")

        alert_rows.append(
            {
                "id": str(uuid.uuid4()),
                "channel": payload.channel,
                "recipient": recipient_email or f"user:{recipient.get('id')}",
                "recipient_role": payload.recipient_role,
                "subject": subject,
                "body": body,
                "severity": payload.severity,
                "status": status,
                "external_ref": external_ref,
                "error_message": error_message,
                "sent_at": sent_at,
                "created_at": now_iso,
            }
        )

    try:
        alert_resp = (
            await db_admin.table("alert_notifications")
            .insert(alert_rows)
            .async_execute()
        )
        if payload.channel == "email":
            alerts_sent = len(
                [row for row in alert_rows if row.get("status") == "sent"]
            )
        else:
            alerts_sent = len(alert_resp.data or alert_rows)
    except Exception as exc:
        logger.error(
            "Failed to insert alert_notifications for hotspot %s: %s", cluster_id, exc
        )

    priority_map = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    notification_rows = []
    for recipient in selected_recipients:
        uid = recipient.get("id")
        if not uid:
            continue
        notification_rows.append(
            {
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "title": subject,
                "message": body,
                "priority": priority_map.get(payload.severity, "high"),
                "read": False,
                "data": {
                    "type": "hotspot_alert",
                    "hotspot_id": cluster_id,
                    "recipient_role": payload.recipient_role,
                    "channel": payload.channel,
                    "severity": payload.severity,
                },
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )

    if notification_rows:
        try:
            notif_resp = (
                await db_admin.table("notifications")
                .insert(notification_rows)
                .async_execute()
            )
            notifications_created = len(notif_resp.data or notification_rows)
        except Exception as exc:
            logger.error(
                "Failed to create in-app notifications for hotspot %s: %s",
                cluster_id,
                exc,
            )

    # Also push to ngo_alerts table for real-time dashboard updates
    if payload.recipient_role == "ngo":
        ngo_rows = []
        for recipient in recipients[:10]:
            ngo_id = recipient.get("id")
            if not ngo_id:
                continue
            ngo_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "ngo_id": ngo_id,
                    "hotspot_id": cluster_id,
                    "alert_type": "admin_hotspot_alert",
                    "title": subject,
                    "message": body,
                    "severity": payload.severity,
                    "latitude": cluster.get("centroid_lat"),
                    "longitude": cluster.get("centroid_lon"),
                    "dominant_type": cluster.get("dominant_type"),
                    "request_count": cluster.get("request_count"),
                    "total_people": cluster.get("total_people"),
                    "avg_priority": cluster.get("avg_priority"),
                    "priority_label": cluster.get("priority_label"),
                    "status": "active",
                    "created_at": now_iso,
                }
            )
        if ngo_rows:
            try:
                ngo_resp = (
                    await db_admin.table("ngo_alerts").insert(ngo_rows).async_execute()
                )
                ngo_alerts_created = len(ngo_resp.data or ngo_rows)
            except Exception as exc:
                logger.error(
                    "Failed to insert ngo_alerts for hotspot %s: %s", cluster_id, exc
                )

    if payload.channel == "email" and alerts_sent == 0:
        raise HTTPException(
            status_code=502,
            detail=(
                "Email dispatch failed for all recipients. "
                f"attempted={len(selected_recipients)}, failures={email_failures}. "
                "Check SendGrid API key/sender verification and recipient email addresses."
            ),
        )

    if alerts_sent == 0 and notifications_created == 0 and ngo_alerts_created == 0:
        raise HTTPException(
            status_code=500,
            detail="Alert dispatch failed: no alert records or notifications were created.",
        )

    return JSONResponse(
        content={
            "message": (
                f"Alert sent to {alerts_sent} {payload.recipient_role}(s); "
                f"in-app notifications created: {notifications_created}."
            ),
            "alerts_sent": alerts_sent,
            "email_failures": email_failures,
            "notifications_created": notifications_created,
            "ngo_alerts_created": ngo_alerts_created,
            "hotspot_id": cluster_id,
        }
    )


@router.get(
    "/{cluster_id}/insights",
    summary="AI-powered hotspot insights",
)
async def get_hotspot_insights(
    cluster_id: str,
    user: dict = Depends(get_current_user),
):
    """Generate rule-based AI insights for a specific hotspot cluster.

    Returns resource recommendations, risk assessment, and suggested actions
    computed from the cluster's data and member requests.
    """
    # Fetch cluster
    try:
        resp = (
            await db_admin.table("hotspot_clusters")
            .select("*")
            .eq("id", cluster_id)
            .async_execute()
        )
        rows = resp.data or []
    except Exception as exc:
        logger.error("Failed to fetch hotspot %s for insights: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not retrieve hotspot data")

    if not rows:
        raise HTTPException(status_code=404, detail="Hotspot cluster not found")

    cluster = rows[0]
    request_ids = cluster.get("request_ids", [])

    # Fetch member requests for analysis
    member_requests = []
    if request_ids:
        try:
            for rid in request_ids[:50]:
                r_resp = (
                    await db_admin.table("resource_requests")
                    .select("id, resource_type, priority, status, head_count")
                    .eq("id", rid)
                    .async_execute()
                )
                if r_resp.data:
                    member_requests.append(r_resp.data[0])
        except Exception as exc:
            logger.warning("Could not fetch member requests for insights: %s", exc)

    # Compute insights
    avg_priority = cluster.get("avg_priority", 2.0)
    request_count = cluster.get("request_count", 0)
    total_people = cluster.get("total_people", 0)
    dominant_type = cluster.get("dominant_type", "Unknown")
    priority_label = cluster.get("priority_label", "medium")

    # Resource type breakdown
    type_counts = Counter(r.get("resource_type", "Other") for r in member_requests)
    resource_breakdown = [{"type": t, "count": c} for t, c in type_counts.most_common()]

    # Priority breakdown
    prio_counts = Counter(r.get("priority", "medium") for r in member_requests)
    priority_breakdown = [
        {"priority": p, "count": c} for p, c in prio_counts.most_common()
    ]

    # Risk score (0-100)
    risk_score = min(
        100,
        int(
            (avg_priority / 4.0) * 40
            + min(request_count / 20.0, 1.0) * 30
            + min(total_people / 100.0, 1.0) * 30
        ),
    )

    # Generate recommendations
    recommendations = []
    if priority_label in ("critical", "high"):
        recommendations.append(
            {
                "action": "immediate_response",
                "title": "Deploy Emergency Response Team",
                "description": f"This hotspot has {priority_label} priority with {total_people} affected people. Immediate deployment recommended.",
                "urgency": "critical",
            }
        )
    if dominant_type in ("Medical", "Evacuation"):
        recommendations.append(
            {
                "action": "medical_support",
                "title": f"Prioritize {dominant_type} Resources",
                "description": f"Dominant need is {dominant_type}. Coordinate with health services and emergency responders.",
                "urgency": "high",
            }
        )
    if request_count > 10:
        recommendations.append(
            {
                "action": "scale_response",
                "title": "Scale Up Operations",
                "description": f"With {request_count} active requests, consider deploying additional NGO teams and volunteers.",
                "urgency": "high",
            }
        )
    if total_people > 50:
        recommendations.append(
            {
                "action": "mass_shelter",
                "title": "Activate Mass Shelter Protocol",
                "description": f"{total_people} people affected. Coordinate temporary shelter and supply distribution.",
                "urgency": "high" if total_people > 100 else "medium",
            }
        )

    # Default recommendation
    if not recommendations:
        recommendations.append(
            {
                "action": "monitor",
                "title": "Continue Monitoring",
                "description": "This hotspot is within normal parameters. Continue routine monitoring.",
                "urgency": "low",
            }
        )

    # Situation summary
    summary = (
        f"Hotspot cluster with {request_count} events affecting {total_people} people. "
        f"Priority: {priority_label.upper()} (score {avg_priority:.1f}/4.0). "
        f"Dominant need: {dominant_type}. Risk score: {risk_score}/100."
    )

    return JSONResponse(
        content={
            "cluster_id": cluster_id,
            "summary": summary,
            "risk_score": risk_score,
            "risk_level": (
                "critical"
                if risk_score >= 75
                else (
                    "high"
                    if risk_score >= 50
                    else "medium" if risk_score >= 25 else "low"
                )
            ),
            "resource_breakdown": resource_breakdown,
            "priority_breakdown": priority_breakdown,
            "recommendations": recommendations,
            "stats": {
                "request_count": request_count,
                "total_people": total_people,
                "avg_priority": avg_priority,
                "priority_label": priority_label,
                "dominant_type": dominant_type,
            },
        }
    )
