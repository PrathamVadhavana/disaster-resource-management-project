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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

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
    channel: str = Field("in_app", description="in_app, email, sms")
    recipient_role: str = Field("ngo", description="ngo, volunteer, admin")
    subject: str | None = None
    body: str | None = None
    severity: str = Field("high")


# ── Existing endpoints ───────────────────────────────────────────────────────


@router.get(
    "",
    summary="Active hotspot clusters (GeoJSON)",
    response_class=JSONResponse,
)
async def get_hotspots(
    status: str | None = Query("active", description="Filter by cluster status"),
    min_priority: str | None = Query(None, description="Minimum priority label (low/medium/high/critical)"),
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
        fc["features"] = [f for f in fc["features"] if f["properties"].get("status") == status]

    if min_priority and min_priority in priority_order:
        threshold = priority_order[min_priority]
        fc["features"] = [
            f
            for f in fc["features"]
            if priority_order.get(f["properties"].get("priority_label", "low"), 0) >= threshold
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
        resp = await db_admin.table("hotspot_clusters").select("*").eq("id", cluster_id).async_execute()
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
                    .select("id, resource_type, priority, status, latitude, longitude, head_count, description")
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
        raise HTTPException(status_code=400, detail=f"Status must be one of {valid_statuses}")

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

    return JSONResponse(content={"message": f"Hotspot {cluster_id} status updated to {payload.status}"})


@router.post(
    "/{cluster_id}/assign",
    summary="Assign resources to a hotspot",
)
async def assign_hotspot_resources(
    cluster_id: str,
    payload: AssignResourcePayload,
    user: dict = Depends(get_current_user),
):
    """Assign volunteers, NGOs, or supplies to a hotspot cluster."""
    if user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")

    # Verify the cluster exists
    try:
        resp = await db_admin.table("hotspot_clusters").select("id, centroid_lat, centroid_lon, dominant_type").eq("id", cluster_id).async_execute()
        if not (resp.data or []):
            raise HTTPException(status_code=404, detail="Hotspot cluster not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch hotspot %s: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not verify hotspot")

    # Log the allocation
    allocation_record = {
        "id": str(uuid.uuid4()),
        "resource_type": payload.resource_type,
        "quantity": payload.quantity,
        "created_at": datetime.now(UTC).isoformat(),
    }

    try:
        await db_admin.table("allocation_log").insert(allocation_record).async_execute()
    except Exception as exc:
        logger.error("Failed to log allocation for hotspot %s: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not log resource allocation")

    # Create a notification for the admin
    try:
        notif = {
            "id": str(uuid.uuid4()),
            "user_id": user.get("id") or user.get("sub"),
            "title": f"Resources assigned to Hotspot",
            "message": f"{payload.quantity}x {payload.resource_type} assigned to hotspot {cluster_id[:8]}",
            "priority": "high",
            "data": {"hotspot_id": cluster_id, "resource_type": payload.resource_type, "quantity": payload.quantity},
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db_admin.table("notifications").insert(notif).async_execute()
    except Exception as exc:
        logger.warning("Failed to create assignment notification: %s", exc)

    return JSONResponse(content={
        "message": f"Assigned {payload.quantity}x {payload.resource_type} to hotspot {cluster_id[:8]}",
        "allocation_id": allocation_record["id"],
    })


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
        resp = await db_admin.table("hotspot_clusters").select("*").eq("id", cluster_id).async_execute()
        cluster_rows = resp.data or []
    except Exception as exc:
        logger.error("Failed to fetch hotspot %s for alerting: %s", cluster_id, exc)
        raise HTTPException(status_code=500, detail="Could not fetch hotspot data")

    if not cluster_rows:
        raise HTTPException(status_code=404, detail="Hotspot cluster not found")

    cluster = cluster_rows[0]

    # Build the alert subject/body
    subject = payload.subject or f"⚠️ Hotspot Alert — {cluster.get('priority_label', 'high').upper()} priority zone"
    body = payload.body or (
        f"A {cluster.get('priority_label', 'high')} priority hotspot with "
        f"{cluster.get('request_count', 0)} events affecting "
        f"{cluster.get('total_people', 0)} people has been flagged. "
        f"Dominant need: {cluster.get('dominant_type', 'Unknown')}. "
        f"Location: ({cluster.get('centroid_lat', 0):.4f}, {cluster.get('centroid_lon', 0):.4f})"
    )

    # Find recipients based on role
    alerts_sent = 0
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
        recipients = []

    now_iso = datetime.now(UTC).isoformat()

    for recipient in recipients[:20]:  # Cap at 20 recipients per alert
        try:
            alert_record = {
                "id": str(uuid.uuid4()),
                "channel": payload.channel,
                "recipient": recipient.get("email", ""),
                "recipient_role": payload.recipient_role,
                "subject": subject,
                "body": body,
                "severity": payload.severity,
                "status": "sent",
                "sent_at": now_iso,
                "created_at": now_iso,
            }
            await db_admin.table("alert_notifications").insert(alert_record).async_execute()
            alerts_sent += 1
        except Exception as exc:
            logger.warning("Failed to send alert to %s: %s", recipient.get("id"), exc)

    # Also push to ngo_alerts table for real-time dashboard updates
    if payload.recipient_role == "ngo":
        for recipient in recipients[:10]:
            try:
                ngo_alert = {
                    "id": str(uuid.uuid4()),
                    "ngo_id": recipient["id"],
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
                await db_admin.table("ngo_alerts").insert(ngo_alert).async_execute()
            except Exception as exc:
                logger.warning("Failed to insert ngo_alert for %s: %s", recipient.get("id"), exc)

    return JSONResponse(content={
        "message": f"Alert sent to {alerts_sent} {payload.recipient_role}(s)",
        "alerts_sent": alerts_sent,
        "hotspot_id": cluster_id,
    })


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
        resp = await db_admin.table("hotspot_clusters").select("*").eq("id", cluster_id).async_execute()
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
    priority_breakdown = [{"priority": p, "count": c} for p, c in prio_counts.most_common()]

    # Risk score (0-100)
    risk_score = min(100, int(
        (avg_priority / 4.0) * 40 +
        min(request_count / 20.0, 1.0) * 30 +
        min(total_people / 100.0, 1.0) * 30
    ))

    # Generate recommendations
    recommendations = []
    if priority_label in ("critical", "high"):
        recommendations.append({
            "action": "immediate_response",
            "title": "Deploy Emergency Response Team",
            "description": f"This hotspot has {priority_label} priority with {total_people} affected people. Immediate deployment recommended.",
            "urgency": "critical",
        })
    if dominant_type in ("Medical", "Evacuation"):
        recommendations.append({
            "action": "medical_support",
            "title": f"Prioritize {dominant_type} Resources",
            "description": f"Dominant need is {dominant_type}. Coordinate with health services and emergency responders.",
            "urgency": "high",
        })
    if request_count > 10:
        recommendations.append({
            "action": "scale_response",
            "title": "Scale Up Operations",
            "description": f"With {request_count} active requests, consider deploying additional NGO teams and volunteers.",
            "urgency": "high",
        })
    if total_people > 50:
        recommendations.append({
            "action": "mass_shelter",
            "title": "Activate Mass Shelter Protocol",
            "description": f"{total_people} people affected. Coordinate temporary shelter and supply distribution.",
            "urgency": "high" if total_people > 100 else "medium",
        })

    # Default recommendation
    if not recommendations:
        recommendations.append({
            "action": "monitor",
            "title": "Continue Monitoring",
            "description": "This hotspot is within normal parameters. Continue routine monitoring.",
            "urgency": "low",
        })

    # Situation summary
    summary = (
        f"Hotspot cluster with {request_count} events affecting {total_people} people. "
        f"Priority: {priority_label.upper()} (score {avg_priority:.1f}/4.0). "
        f"Dominant need: {dominant_type}. Risk score: {risk_score}/100."
    )

    return JSONResponse(content={
        "cluster_id": cluster_id,
        "summary": summary,
        "risk_score": risk_score,
        "risk_level": "critical" if risk_score >= 75 else "high" if risk_score >= 50 else "medium" if risk_score >= 25 else "low",
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
    })
