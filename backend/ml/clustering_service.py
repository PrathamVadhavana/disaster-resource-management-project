"""
Geospatial Hotspot Detection Service — DBSCAN Clustering.

Clusters active victim resource requests using DBSCAN
(eps ≈ 500 m, min_samples = 3).  For each cluster the service
computes a centroid, dominant resource type, total affected
people, average priority score, and a GeoJSON polygon boundary
(convex hull of cluster points, or a buffered circle when < 3
unique points).

Results are persisted to the ``hotspot_clusters`` database
table and, when a new high-priority hotspot forms, the
three nearest available NGOs are alerted via
the ``ngo_alerts`` table so dashboards update in
real time.

The ``run_clustering`` coroutine is designed to be called every
5 minutes by the APScheduler job wired up in ``main.py``.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import numpy as np

try:
    from sklearn.cluster import DBSCAN
except ImportError:  # pragma: no cover
    DBSCAN = None  # type: ignore[assignment,misc]

from app.database import db_admin

logger = logging.getLogger("clustering_service")

# ── Constants ─────────────────────────────────────────────────────────────────

# DBSCAN parameters
_EPS_METERS: float = 500.0
_MIN_SAMPLES: int = 3

# Earth radius for Haversine (metres)
_EARTH_RADIUS_M: float = 6_371_000.0

# Priority string → numeric score mapping
_PRIORITY_SCORE: dict[str, float] = {
    "critical": 4.0,
    "high": 3.0,
    "medium": 2.0,
    "low": 1.0,
}

# Reverse lookup: score → label
_SCORE_LABEL: dict[str, str] = {
    "4": "critical",
    "3": "high",
    "2": "medium",
    "1": "low",
}

# Adaptive EPS based on density multipliers (Improvisation 4)
_DEFAULT_EPS_M = 500.0
_DENSE_EPS_M = 300.0
_SPARSE_EPS_M = 800.0


# ── Geo helpers ───────────────────────────────────────────────────────────────


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in **metres** between two WGS-84 points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _haversine_distance_matrix(coords: np.ndarray) -> np.ndarray:
    """Build an NxN pairwise Haversine distance matrix (metres)."""
    n = len(coords)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_m(coords[i, 0], coords[i, 1], coords[j, 0], coords[j, 1])
            matrix[i, j] = d
            matrix[j, i] = d
    return matrix


def _convex_hull_geojson(points: list[tuple[float, float]]) -> dict[str, Any]:
    """Return a GeoJSON Polygon for the convex hull of *points* (lat, lon).

    When < 3 unique points exist, fall back to a ~250 m buffered circle
    around the centroid so we always emit a valid polygon.
    """
    unique = list(set(points))
    if len(unique) < 3:
        # Degenerate case – create a small circle polygon
        clat = sum(p[0] for p in unique) / len(unique)
        clon = sum(p[1] for p in unique) / len(unique)
        return _buffered_circle(clat, clon, radius_m=250)

    # Simple gift-wrapping (Jarvis march) for convex hull
    pts = sorted(unique, key=lambda p: (p[1], p[0]))  # sort by lon then lat

    def cross(o: tuple, a: tuple, b: tuple) -> float:
        return (a[1] - o[1]) * (b[0] - o[0]) - (a[0] - o[0]) * (b[1] - o[1])

    lower: list = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    hull = lower[:-1] + upper[:-1]
    # GeoJSON uses [lon, lat] order and first == last for closing
    ring = [[p[1], p[0]] for p in hull]
    ring.append(ring[0])

    return {
        "type": "Polygon",
        "coordinates": [ring],
    }


def _buffered_circle(lat: float, lon: float, radius_m: float = 250, segments: int = 32) -> dict[str, Any]:
    """Generate a GeoJSON Polygon approximating a circle of *radius_m*."""
    coords = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        dlat = (radius_m / _EARTH_RADIUS_M) * math.cos(angle)
        dlon = (radius_m / _EARTH_RADIUS_M) * math.sin(angle) / math.cos(math.radians(lat))
        coords.append([lon + math.degrees(dlon), lat + math.degrees(dlat)])
    coords.append(coords[0])  # close ring
    return {"type": "Polygon", "coordinates": [coords]}


# ── Cluster computation ──────────────────────────────────────────────────────


def _priority_label(avg_score: float) -> str:
    if avg_score >= 3.5:
        return "critical"
    if avg_score >= 2.5:
        return "high"
    if avg_score >= 1.5:
        return "medium"
    return "low"


def _compute_clusters(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run DBSCAN over *requests* and return cluster descriptors.

    Each request dict must have at minimum:
        ``id``, ``latitude``, ``longitude``, ``resource_type``,
        ``priority``, ``head_count`` (defaults to 1).
    """
    if DBSCAN is None:
        logger.warning("scikit-learn not installed – skipping DBSCAN clustering")
        return []

    if len(requests) < _MIN_SAMPLES:
        logger.debug("Only %d requests – need at least %d for clustering", len(requests), _MIN_SAMPLES)
        return []

    coords = np.array([[r["latitude"], r["longitude"]] for r in requests])
    dist_matrix = _haversine_distance_matrix(coords)

    db = DBSCAN(eps=_EPS_METERS, min_samples=_MIN_SAMPLES, metric="precomputed")
    labels = db.fit_predict(dist_matrix)

    clusters: list[dict[str, Any]] = []
    unique_labels = set(labels)
    unique_labels.discard(-1)  # noise

    for label in sorted(unique_labels):
        indices = [i for i, lbl in enumerate(labels) if lbl == label]
        cluster_requests = [requests[i] for i in indices]

        lats = [r["latitude"] for r in cluster_requests]
        lons = [r["longitude"] for r in cluster_requests]
        centroid_lat = sum(lats) / len(lats)
        centroid_lon = sum(lons) / len(lons)

        type_counts = Counter(r.get("resource_type", "Other") for r in cluster_requests)
        dominant_type = type_counts.most_common(1)[0][0]

        total_people = sum(int(r.get("head_count", 1)) for r in cluster_requests)

        # ── Weighted Priority (Improvisation 3) ──────────────────────────────
        # Instead of simple average, we weight by head_count to highlight
        # mass-impact areas.
        weighted_sum = 0.0
        total_hc = 0
        for r in cluster_requests:
            hc = max(1, int(r.get("head_count", 1)))
            p_score = _PRIORITY_SCORE.get(str(r.get("priority", "medium")).lower(), 2.0)
            weighted_sum += p_score * hc
            total_hc += hc

        avg_score = weighted_sum / total_hc if total_hc > 0 else 2.0
        
        # ── Risk Score (Improvisation 6 - basic) ─────────────────────────────
        # Compute a 0-100 risk score based on density, headcount and severity.
        density_factor = min(1.0, len(cluster_requests) / 20.0)
        severity_factor = min(1.0, avg_score / 4.0)
        population_factor = min(1.0, total_hc / 50.0)
        risk_score = round((density_factor * 0.3 + severity_factor * 0.4 + population_factor * 0.3) * 100, 1)

        boundary = _convex_hull_geojson([(r["latitude"], r["longitude"]) for r in cluster_requests])

        clusters.append(
            {
                "centroid_lat": round(centroid_lat, 6),
                "centroid_lon": round(centroid_lon, 6),
                "request_count": len(cluster_requests),
                "total_people": total_people,
                "dominant_type": dominant_type,
                "avg_priority": round(avg_score, 2),
                "priority_label": _priority_label(avg_score),
                "boundary": boundary,
                "request_ids": [r["id"] for r in cluster_requests],
                "risk_score": risk_score,
            }
        )

    return clusters


# ── Database write helpers ──────────────────────────────────────────────────


def _write_hotspot_to_db(cluster: dict[str, Any], doc_id: str) -> None:
    """Write/overwrite a hotspot document in ``hotspot_clusters`` table."""
    from app.database import db_admin

    db_admin.table("hotspot_clusters").upsert(
        {
            "id": doc_id,
            "centroid": {"lat": cluster["centroid_lat"], "lon": cluster["centroid_lon"]},
            "boundary": cluster["boundary"],
            "request_count": cluster["request_count"],
            "total_people": cluster["total_people"],
            "dominant_type": cluster["dominant_type"],
            "avg_priority": cluster["avg_priority"],
            "priority_label": cluster["priority_label"],
            "request_ids": cluster["request_ids"],
            "status": "active",
            "detected_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    ).execute()
    logger.info("Hotspot doc written: %s", doc_id)


def _find_nearest_ngos(lat: float, lon: float, limit: int = 3, required_type: str | None = None) -> list[dict[str, Any]]:
    """Find the *limit* nearest NGOs with status 'active' / 'verified'.

    NGO user records are expected to have ``latitude`` and ``longitude``
    fields (set during onboarding).  Optional ``required_type`` filters for
    NGOs whose ``metadata.specialization`` matches the hotspot needs (Improvisation 1).
    """
    from app.core.query_cache import TTL_MEDIUM
    from app.core.query_cache import cache_get as mem_get
    from app.core.query_cache import cache_set as mem_set

    cache_key = f"clustering:ngo_list:{required_type or 'all'}"
    ngos = mem_get(cache_key)
    if ngos is None:
        try:
            resp = (
                db_admin.table("users")
                .select("id, email, full_name, organization, latitude, longitude, metadata")
                .eq("role", "ngo")
                .limit(500)
                .execute()
            )
            all_ngos = resp.data or []
            
            # Capability Filtering (Improvisation 1)
            if required_type:
                def matches(n):
                    meta = n.get("metadata") or {}
                    specialization = meta.get("specialization") or meta.get("category") or ""
                    if isinstance(specialization, list):
                        return required_type in specialization
                    return required_type.lower() in str(specialization).lower() or not specialization
                
                ngos = [n for n in all_ngos if matches(n)]
                # If no capable NGOs found, fall back to all active ones
                if not ngos:
                    logger.info("No specialized NGOs for %s, falling back to all", required_type)
                    ngos = all_ngos
            else:
                ngos = all_ngos
                
            mem_set(cache_key, ngos, TTL_MEDIUM)
        except Exception as exc:
            logger.error("Failed to query NGOs: %s", exc)
            return []

    # Filter to NGOs that have coordinates
    ngos_with_coords = [n for n in ngos if n.get("latitude") and n.get("longitude")]
    if not ngos_with_coords:
        logger.warning("No NGOs with coordinates found for nearest-neighbour search")
        return []

    # Sort by Haversine distance
    for n in ngos_with_coords:
        n["_distance_m"] = _haversine_m(lat, lon, float(n["latitude"]), float(n["longitude"]))

    ngos_with_coords.sort(key=lambda n: n["_distance_m"])
    return ngos_with_coords[:limit]


def _send_hotspot_alert(cluster: dict[str, Any], doc_id: str) -> None:
    """Push a ``hotspot_alert`` document to ``ngo_alerts/{ngo_id}`` for each
    of the nearest SUVs. Capability matching is applied via _find_nearest_ngos.
    """
    nearest = _find_nearest_ngos(
        cluster["centroid_lat"], 
        cluster["centroid_lon"], 
        limit=3,
        required_type=cluster["dominant_type"]
    )
    if not nearest:
        logger.info("No NGOs to alert for hotspot %s", doc_id)
        return

    alert_payload = {
        "hotspot_id": doc_id,
        "centroid": {"lat": cluster["centroid_lat"], "lon": cluster["centroid_lon"]},
        "dominant_type": cluster["dominant_type"],
        "request_count": cluster["request_count"],
        "total_people": cluster["total_people"],
        "avg_priority": cluster["avg_priority"],
        "priority_label": cluster["priority_label"],
        "status": "new",
        "created_at": datetime.now(UTC).isoformat(),
    }

    for ngo in nearest:
        ngo_id = ngo["id"]
        distance_km = round(ngo["_distance_m"] / 1000, 1)
        alert = {**alert_payload, "ngo_id": ngo_id, "distance_km": distance_km}
        try:
            db_admin.table("ngo_alerts").insert(alert).execute()
            logger.info("Alert sent to NGO %s (%.1f km away) for hotspot %s", ngo_id, distance_km, doc_id)
        except Exception as exc:
            logger.error("Failed to send alert to NGO %s: %s", ngo_id, exc)


# ── Persist cluster to database ──────────────────────────────────────────────


async def _persist_cluster(cluster: dict[str, Any]) -> str:
    """Save a cluster to ``hotspot_clusters`` table and return its doc ID."""
    doc_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    # ── Inject Metadata into JSONB Boundary ──
    # Since we can't easily add new columns to the DB, we leverage the existing
    # JSONB 'boundary' field to store our advanced clustering metadata.
    boundary = cluster["boundary"]
    if isinstance(boundary, dict):
        boundary["_meta"] = {
            "trend": cluster.get("trend", "stable"),
            "risk_score": cluster.get("risk_score", 0.0),
        }

    record = {
        "id": doc_id,
        "boundary": boundary,
        "centroid_lat": cluster["centroid_lat"],
        "centroid_lon": cluster["centroid_lon"],
        "request_count": cluster["request_count"],
        "total_people": cluster["total_people"],
        "dominant_type": cluster["dominant_type"],
        "avg_priority": cluster["avg_priority"],
        "priority_label": cluster["priority_label"],
        "status": "active",
        "request_ids": cluster["request_ids"],
        "synced": False,
        "detected_at": now,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await db_admin.table("hotspot_clusters").insert(record).async_execute()
        logger.info("Cluster %s persisted (%d requests, trend=%s)", doc_id, cluster["request_count"], record["trend"])
    except Exception as exc:
        logger.error("Failed to persist cluster: %s", exc)

    return doc_id


# ── Main entry point (called by scheduler) ───────────────────────────────────


async def run_clustering() -> list[dict[str, Any]]:
    """Fetch active requests, run DBSCAN, persist new clusters,
    and alert NGOs for high-priority hotspots.

    Returns the list of newly detected clusters (for testing / logging).
    """
    logger.info("Hotspot DBSCAN clustering cycle starting …")

    # 1. Fetch active (non-completed, non-rejected) resource requests with coordinates
    try:
        resp = await (
            db_admin.table("resource_requests")
            .select("id, latitude, longitude, resource_type, priority, head_count, status")
            .in_("status", ["pending", "approved", "assigned", "in_progress"])
            .limit(2000)
            .async_execute()
        )
        all_requests = resp.data or []
    except Exception as exc:
        logger.error("Failed to fetch resource requests: %s", exc)
        return []

    # Keep only requests that have coordinates
    requests = [r for r in all_requests if r.get("latitude") is not None and r.get("longitude") is not None]

    logger.info("Clustering %d geo-located active requests (of %d fetched)", len(requests), len(all_requests))

    if not requests:
        return []

    # 2. Run DBSCAN
    clusters = _compute_clusters(requests)
    logger.info("DBSCAN found %d clusters", len(clusters))

    if not clusters:
        return []

    # 3. Mark previously active clusters as 'resolved' if they are no
    #    longer detected (single batch query instead of N updates).
    old_clusters = []
    try:
        old_resp = await (
            db_admin.table("hotspot_clusters")
            .select("id, centroid_lat, centroid_lon, request_count, total_people")
            .eq("status", "active")
            .limit(500)
            .async_execute()
        )
        old_clusters = old_resp.data or []
        old_ids = [r["id"] for r in old_clusters]
        if old_ids:
            now_iso = datetime.now(UTC).isoformat()
            # Batch resolve: update all old clusters at once using in_ filter
            for batch_start in range(0, len(old_ids), 30):
                batch_ids = old_ids[batch_start : batch_start + 30]
                await (
                    db_admin.table("hotspot_clusters")
                    .update(
                        {
                            "status": "resolved",
                            "resolved_at": now_iso,
                        }
                    )
                    .in_("id", batch_ids)
                    .async_execute()
                )
    except Exception as exc:
        logger.warning("Could not expire old clusters: %s", exc)

    # 3.5 Temporal Trend Detection (Improvisation 2)
    # Compare each new cluster to the nearest old cluster to detect trend
    for cluster in clusters:
        cluster["trend"] = "new"  # default
        if not old_clusters:
            continue
            
        # Find nearest previous cluster within 1km
        closest = None
        min_dist = 1000.0
        for old in old_clusters:
            d = _haversine_m(cluster["centroid_lat"], cluster["centroid_lon"], old["centroid_lat"], old["centroid_lon"])
            if d < min_dist:
                min_dist = d
                closest = old
                
        if closest:
            if cluster["request_count"] > closest["request_count"]:
                cluster["trend"] = "growing"
            elif cluster["request_count"] < closest["request_count"]:
                cluster["trend"] = "receding"
            else:
                cluster["trend"] = "stable"

    # 4. Persist new clusters + NGO alerts
    new_clusters: list[dict[str, Any]] = []
    for cluster in clusters:
        doc_id = await _persist_cluster(cluster)

        # Upsert to database for real-time map layer
        try:
            import asyncio as _asyncio

            await _asyncio.to_thread(_write_hotspot_to_db, cluster, doc_id)
            await (
                db_admin.table("hotspot_clusters")
                .update(
                    {
                        "synced": True,
                    }
                )
                .eq("id", doc_id)
                .async_execute()
            )
        except Exception as exc:
            logger.error("Hotspot sync failed for %s: %s", doc_id, exc)

        # Alert NGOs for high-priority hotspots
        if cluster["priority_label"] in ("high", "critical"):
            try:
                import asyncio

                await asyncio.to_thread(_send_hotspot_alert, cluster, doc_id)
            except Exception as exc:
                logger.error("NGO alerting failed for %s: %s", doc_id, exc)

        cluster["id"] = doc_id
        new_clusters.append(cluster)

    logger.info("Clustering cycle complete — %d hotspots active", len(new_clusters))
    return new_clusters


# ── GeoJSON builder (used by the API endpoint) ───────────────────────────────


def build_geojson_feature_collection() -> dict[str, Any]:
    """Return all **active** hotspot clusters as a GeoJSON FeatureCollection.

    Each Feature carries the cluster statistics as ``properties`` and the
    convex-hull boundary as the ``geometry``.  A ``Point`` geometry is
    added as ``properties.centroid`` for convenience.
    """
    try:
        resp = (
            db_admin.table("hotspot_clusters")
            .select("*")
            .eq("status", "active")
            .order("detected_at", desc=True)
            .execute()
        )
        rows = resp.data or []
    except Exception as exc:
        logger.error("Failed to fetch hotspot clusters: %s", exc)
        rows = []

    features: list[dict[str, Any]] = []
    for row in rows:
        boundary = row.get("boundary", {})
        if isinstance(boundary, str):
            import json

            try:
                boundary = json.loads(boundary)
            except Exception:
                boundary = {"type": "Point", "coordinates": [row.get("centroid_lon", 0), row.get("centroid_lat", 0)]}

        # Extract metadata from JSONB if present
        meta = boundary.get("_meta", {}) if isinstance(boundary, dict) else {}
        trend = meta.get("trend") or row.get("trend", "stable")
        risk_score = meta.get("risk_score") or row.get("risk_score", 0.0)

        feature = {
            "type": "Feature",
            "id": row.get("id"),
            "geometry": boundary,
            "properties": {
                "id": row.get("id"),
                "centroid": {
                    "type": "Point",
                    "coordinates": [row.get("centroid_lon", 0), row.get("centroid_lat", 0)],
                },
                "request_count": row.get("request_count", 0),
                "total_people": row.get("total_people", 0),
                "dominant_type": row.get("dominant_type", "Unknown"),
                "avg_priority": row.get("avg_priority", 0),
                "priority_label": row.get("priority_label", "medium"),
                "trend": trend,
                "risk_score": risk_score,
                "detected_at": row.get("detected_at"),
                "status": row.get("status", "active"),
            },
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
    }
