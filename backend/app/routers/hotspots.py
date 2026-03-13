"""
Hotspot Clusters API Router — GeoJSON endpoint for the disaster map.

Serves active DBSCAN-detected hotspot clusters as a GeoJSON
FeatureCollection suitable for rendering as a heatmap / polygon
layer in Leaflet or Mapbox GL JS.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.database import db_admin
from app.dependencies import get_current_user

logger = logging.getLogger("hotspots_router")

router = APIRouter()


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
