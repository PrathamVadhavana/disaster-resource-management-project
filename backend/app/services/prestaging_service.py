"""
Predictive Resource Pre-Staging Service.

Uses ingested weather + GDACS data to predict likely disasters 24-48h ahead.
Automatically generates "pre-staging recommendations" — suggests moving resources
to warehouses near predicted impact zones before the disaster hits.
"""

import logging
import math
from datetime import UTC, datetime

from app.database import db_admin

logger = logging.getLogger("prestaging_service")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def generate_prestaging_recommendations() -> list[dict]:
    """Analyze predicted/monitoring disasters and generate resource pre-staging recommendations."""
    recommendations = []

    try:
        # Fetch predicted/active disasters
        disaster_resp = (
            await db_admin.table("disasters")
            .select(
                "id, title, type, severity, status, latitude, longitude, location_id, start_date, affected_population"
            )
            .in_("status", ["predicted", "active", "monitoring"])
            .order("created_at", desc=True)
            .limit(20)
            .async_execute()
        )
        disasters = disaster_resp.data or []

        # Get location coordinates
        loc_ids = [d["location_id"] for d in disasters if d.get("location_id")]
        loc_map = {}
        if loc_ids:
            loc_resp = (
                await db_admin.table("locations")
                .select("id, latitude, longitude, name, city")
                .in_("id", loc_ids)
                .async_execute()
            )
            for loc in loc_resp.data or []:
                loc_map[loc["id"]] = loc

        # Fetch available resources with location
        resources_resp = (
            await db_admin.table("resources")
            .select(
                "id, type, name, quantity, status, provider_id"
            )
            .eq("status", "available")
            .async_execute()
        )
        resources = resources_resp.data or []

        # Fetch ingested alerts (predicted events from weather/GDACS)
        try:
            from app.services.ingestion import memory_store

            ingested_alerts = memory_store.query_ingested_events(limit=50)
        except Exception:
            ingested_alerts = []

        # Severity weight for resource estimation
        severity_multiplier = {"low": 1.0, "medium": 2.0, "high": 4.0, "critical": 8.0}

        for d in disasters:
            d_lat = d.get("latitude")
            d_lon = d.get("longitude")
            if (d_lat is None or d_lon is None) and d.get("location_id"):
                loc = loc_map.get(d["location_id"], {})
                d_lat = loc.get("latitude")
                d_lon = loc.get("longitude")

            if d_lat is None or d_lon is None:
                continue

            sev = d.get("severity", "medium")
            pop = d.get("affected_population", 1000) or 1000
            multiplier = severity_multiplier.get(sev, 2.0)

            # Estimate resource needs based on disaster type and severity
            type_needs = _estimate_needs_by_type(d.get("type", "other"), pop, multiplier)

            # Find nearby resources
            nearby_resources = []
            for r in resources:
                r_lat = r.get("latitude")
                r_lon = r.get("longitude")
                if r_lat and r_lon:
                    dist = haversine_km(d_lat, d_lon, r_lat, r_lon)
                    if dist <= 200:  # within 200km
                        avail = (r.get("total_quantity", 0) or 0) - (r.get("claimed_quantity", 0) or 0)
                        if avail > 0:
                            nearby_resources.append(
                                {
                                    "resource_id": r["resource_id"],
                                    "category": r.get("category"),
                                    "title": r.get("title"),
                                    "available_quantity": avail,
                                    "distance_km": round(dist, 1),
                                    "location": r.get("address_text"),
                                }
                            )

            nearby_resources.sort(key=lambda x: x["distance_km"])

            # Check for resource gaps
            gaps = []
            for need_type, need_qty in type_needs.items():
                available = sum(
                    r["available_quantity"]
                    for r in nearby_resources
                    if r.get("category", "").lower() == need_type.lower()
                )
                if available < need_qty:
                    gaps.append(
                        {
                            "resource_type": need_type,
                            "needed": need_qty,
                            "available_nearby": available,
                            "shortfall": need_qty - available,
                        }
                    )

            # Find related ingested alerts
            related_alerts = []
            for alert in ingested_alerts:
                a_lat = alert.get("latitude")
                a_lon = alert.get("longitude")
                if a_lat and a_lon:
                    dist = haversine_km(d_lat, d_lon, a_lat, a_lon)
                    if dist <= 150:
                        related_alerts.append(
                            {
                                "source": alert.get("source"),
                                "title": alert.get("title"),
                                "severity": alert.get("severity"),
                                "distance_km": round(dist, 1),
                            }
                        )

            recommendations.append(
                {
                    "disaster_id": d["id"],
                    "disaster_title": d.get("title", "Unknown"),
                    "disaster_type": d.get("type"),
                    "severity": sev,
                    "status": d.get("status"),
                    "location": {"latitude": d_lat, "longitude": d_lon},
                    "estimated_needs": type_needs,
                    "nearby_resources": nearby_resources[:10],
                    "resource_gaps": gaps,
                    "related_alerts": related_alerts,
                    "recommendation": _generate_recommendation_text(d, gaps, nearby_resources),
                    "urgency": "critical" if sev in ("critical", "high") else "medium",
                    "generated_at": datetime.now(UTC).isoformat(),
                }
            )

    except Exception as e:
        logger.error("Pre-staging recommendation generation failed: %s", e)

    return recommendations


def _estimate_needs_by_type(disaster_type: str, population: int, multiplier: float) -> dict[str, int]:
    """Estimate resource needs by disaster type and affected population."""
    base_per_1000 = {
        "earthquake": {"Food": 500, "Water": 1000, "Medical": 200, "Shelter": 100},
        "flood": {"Food": 400, "Water": 1500, "Medical": 150, "Shelter": 200},
        "hurricane": {"Food": 600, "Water": 1200, "Medical": 250, "Shelter": 150},
        "wildfire": {"Food": 300, "Water": 800, "Medical": 100, "Shelter": 250},
        "tornado": {"Food": 400, "Water": 800, "Medical": 200, "Shelter": 100},
        "tsunami": {"Food": 500, "Water": 1500, "Medical": 300, "Shelter": 200},
    }
    base = base_per_1000.get(disaster_type, {"Food": 400, "Water": 800, "Medical": 150, "Shelter": 100})
    scale = max(1, population / 1000)
    return {k: int(v * scale * multiplier) for k, v in base.items()}


def _generate_recommendation_text(disaster: dict, gaps: list, nearby: list) -> str:
    """Generate human-readable recommendation text."""
    title = disaster.get("title", "the disaster area")
    if not gaps:
        return f"Resources near {title} appear adequate. Continue monitoring."

    gap_text = ", ".join(f"{g['shortfall']} units of {g['resource_type']}" for g in gaps[:3])
    return f"Pre-stage resources for {title}: shortfall detected for {gap_text}. Consider mobilizing from nearest supply points."
