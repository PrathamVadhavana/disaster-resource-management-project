"""
Automated Request-to-Disaster Linking Service.

Uses geospatial proximity (haversine) + time window matching to auto-link
incoming resource requests to active disasters. Enables per-disaster dashboards
showing demand vs. supply in real-time.
"""

import logging
import math
from datetime import UTC, datetime

from app.database import db_admin

logger = logging.getLogger("disaster_linking")

# Configuration
MAX_DISTANCE_KM = 100.0  # max km between request and disaster epicenter
TIME_WINDOW_HOURS = 168  # 7 days — request must be within this window of disaster start


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_dt(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=UTC)
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except Exception:
        return None


async def find_matching_disaster(
    req_lat: float,
    req_lon: float,
    req_created_at: str,
    max_distance_km: float = MAX_DISTANCE_KM,
    time_window_hours: float = TIME_WINDOW_HOURS,
) -> dict | None:
    """Find the closest active disaster to a request location within constraints.

    Returns the best-matching disaster dict or None.
    """
    try:
        # Fetch active/monitoring disasters
        resp = (
            await db_admin.table("disasters")
            .select("id, title, type, severity, status, latitude, longitude, start_date, location_id, created_at")
            .in_("status", ["active", "monitoring", "predicted"])
            .async_execute()
        )
        disasters = resp.data or []

        # Also fetch location coordinates for disasters that use location_id
        location_ids = [d["location_id"] for d in disasters if d.get("location_id")]
        loc_map = {}
        if location_ids:
            loc_resp = (
                await db_admin.table("locations")
                .select("id, latitude, longitude")
                .in_("id", location_ids)
                .async_execute()
            )
            for loc in loc_resp.data or []:
                loc_map[loc["id"]] = loc

        req_time = _parse_dt(req_created_at)
        if not req_time:
            req_time = datetime.now(UTC)

        best_match = None
        best_distance = float("inf")

        for d in disasters:
            # Get disaster coordinates
            d_lat = d.get("latitude")
            d_lon = d.get("longitude")
            if (d_lat is None or d_lon is None) and d.get("location_id"):
                loc = loc_map.get(d["location_id"], {})
                d_lat = loc.get("latitude")
                d_lon = loc.get("longitude")

            if d_lat is None or d_lon is None:
                continue

            # Check time window
            d_start = _parse_dt(d.get("start_date") or d.get("created_at"))
            if d_start and (req_time - d_start).total_seconds() > time_window_hours * 3600:
                continue

            # Check distance
            dist = haversine_km(req_lat, req_lon, d_lat, d_lon)
            if dist <= max_distance_km and dist < best_distance:
                best_distance = dist
                best_match = {
                    "disaster_id": d["id"],
                    "disaster_title": d.get("title", "Unknown"),
                    "disaster_type": d.get("type", "unknown"),
                    "disaster_severity": d.get("severity", "medium"),
                    "distance_km": round(dist, 2),
                }

        return best_match
    except Exception as e:
        logger.error("Disaster linking failed: %s", e)
        return None


async def link_request_to_disaster(request_id: str, disaster_id: str, distance_km: float):
    """Store the disaster link on the request document."""
    try:
        await (
            db_admin.table("resource_requests")
            .update(
                {
                    "linked_disaster_id": disaster_id,
                    "disaster_distance_km": distance_km,
                }
            )
            .eq("id", request_id)
            .async_execute()
        )
        logger.info("Linked request %s to disaster %s (%.1f km)", request_id[:8], disaster_id[:8], distance_km)
    except Exception as e:
        logger.error("Failed to link request %s to disaster: %s", request_id[:8], e)


async def auto_link_request(request_id: str, lat: float, lon: float, created_at: str) -> dict | None:
    """Auto-link a request to the nearest matching disaster. Called on request creation."""
    match = await find_matching_disaster(lat, lon, created_at)
    if match:
        await link_request_to_disaster(request_id, match["disaster_id"], match["distance_km"])
    return match


async def get_disaster_demand_supply(disaster_id: str) -> dict:
    """Get demand vs supply summary for a specific disaster."""
    try:
        # Demand: all linked requests
        req_resp = (
            await db_admin.table("resource_requests")
            .select("id, resource_type, quantity, priority, status, fulfillment_pct")
            .eq("linked_disaster_id", disaster_id)
            .async_execute()
        )
        requests = req_resp.data or []

        demand_by_type = {}
        for r in requests:
            rt = r.get("resource_type", "Other")
            if rt not in demand_by_type:
                demand_by_type[rt] = {"requested": 0, "fulfilled": 0, "pending": 0}
            qty = r.get("quantity", 1)
            pct = r.get("fulfillment_pct", 0)
            demand_by_type[rt]["requested"] += qty
            demand_by_type[rt]["fulfilled"] += int(qty * pct / 100)
            if r.get("status") in ("pending", "approved"):
                demand_by_type[rt]["pending"] += qty

        # Supply: resources allocated to this disaster
        res_resp = (
            await db_admin.table("resources")
            .select("type, quantity, status")
            .eq("disaster_id", disaster_id)
            .async_execute()
        )
        supply_by_type = {}
        for r in res_resp.data or []:
            rt = r.get("type", "other")
            if rt not in supply_by_type:
                supply_by_type[rt] = {"total": 0, "available": 0, "allocated": 0}
            qty = r.get("quantity", 0)
            supply_by_type[rt]["total"] += qty
            if r.get("status") == "available":
                supply_by_type[rt]["available"] += qty
            else:
                supply_by_type[rt]["allocated"] += qty

        return {
            "disaster_id": disaster_id,
            "total_requests": len(requests),
            "demand_by_type": demand_by_type,
            "supply_by_type": supply_by_type,
            "status_breakdown": {
                s: sum(1 for r in requests if r.get("status") == s)
                for s in ["pending", "approved", "assigned", "in_progress", "delivered", "completed"]
            },
        }
    except Exception as e:
        logger.error("Demand/supply fetch for disaster %s failed: %s", disaster_id, e)
        return {"disaster_id": disaster_id, "total_requests": 0, "demand_by_type": {}, "supply_by_type": {}}
