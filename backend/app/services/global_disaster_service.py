"""
Global Disaster Data Aggregation Service
Fetches REAL live disaster data from multiple free public APIs:
- USGS Earthquake Feed (M4.5+ past 30 days)
- NASA EONET (Earth Observatory Natural Event Tracker)
- GDACS (Global Disaster Alerting Coordination System)
- ReliefWeb API (UN OCHA disaster information)
"""

import asyncio
import logging
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Simple in-memory cache ────────────────────────────────────────────────

_cache: dict = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(key: str):
    entry = _cache.get(key)
    if entry and (datetime.now(timezone.utc) - entry["ts"]).total_seconds() < CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def _set_cached(key: str, data):
    _cache[key] = {"data": data, "ts": datetime.now(timezone.utc)}


# ── Severity Normalisation ────────────────────────────────────────────────

def _mag_to_severity(mag: float) -> str:
    if mag >= 7.0:
        return "critical"
    if mag >= 6.0:
        return "high"
    if mag >= 5.0:
        return "medium"
    return "low"


def _gdacs_severity(alert_level: str) -> str:
    mapping = {"Red": "critical", "Orange": "high", "Green": "medium"}
    return mapping.get(alert_level, "low")


def _reliefweb_severity(status: str) -> str:
    s = (status or "").lower()
    if "alert" in s or "emergency" in s:
        return "critical"
    if "ongoing" in s:
        return "high"
    return "medium"


# ── Fetchers ──────────────────────────────────────────────────────────────

async def _fetch_usgs(client: httpx.AsyncClient) -> list[dict]:
    """USGS M4.5+ earthquakes – past 30 days."""
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_month.geojson"
    try:
        r = await client.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = []
        for feat in data.get("features", []):
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [0, 0, 0])
            results.append({
                "id": f"usgs_{feat.get('id', '')}",
                "source": "USGS",
                "type": "earthquake",
                "title": props.get("title", "Earthquake"),
                "description": f"Magnitude {props.get('mag', '?')} earthquake - {props.get('place', 'Unknown')}",
                "severity": _mag_to_severity(props.get("mag", 0) or 0),
                "magnitude": props.get("mag"),
                "latitude": coords[1],
                "longitude": coords[0],
                "depth_km": coords[2] if len(coords) > 2 else None,
                "location_name": props.get("place", ""),
                "url": props.get("url", ""),
                "timestamp": datetime.utcfromtimestamp(props.get("time", 0) / 1000).isoformat() if props.get("time") else None,
                "updated": datetime.utcfromtimestamp(props.get("updated", 0) / 1000).isoformat() if props.get("updated") else None,
            })
        logger.info("USGS: fetched %d earthquakes", len(results))
        return results
    except Exception as e:
        logger.warning("USGS fetch failed: %s", e)
        return []


async def _fetch_eonet(client: httpx.AsyncClient) -> list[dict]:
    """NASA EONET – active natural events (wildfires, storms, volcanoes, etc.)."""
    url = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=200"
    try:
        r = await client.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        results = []
        category_map = {
            "wildfires": ("wildfire", "high"),
            "volcanoes": ("volcanic_eruption", "critical"),
            "severeStorms": ("cyclone", "high"),
            "floods": ("flood", "high"),
            "drought": ("drought", "medium"),
            "dustHaze": ("other", "low"),
            "earthquakes": ("earthquake", "high"),
            "landslides": ("landslide", "high"),
            "snow": ("other", "low"),
            "tempExtremes": ("other", "medium"),
            "waterColor": ("other", "low"),
            "seaLakeIce": ("other", "low"),
            "manmade": ("other", "medium"),
        }
        for event in data.get("events", []):
            cats = event.get("categories", [])
            cat_id = cats[0].get("id", "other") if cats else "other"
            dtype, default_sev = category_map.get(cat_id, ("other", "medium"))

            # Use latest geometry
            geometries = event.get("geometry", [])
            if not geometries:
                continue
            latest = geometries[-1]
            coords = latest.get("coordinates", [0, 0])
            if not coords or len(coords) < 2:
                continue

            results.append({
                "id": f"eonet_{event.get('id', '')}",
                "source": "NASA EONET",
                "type": dtype,
                "title": event.get("title", "Natural Event"),
                "description": f"{event.get('title', '')} — tracked by NASA Earth Observatory",
                "severity": default_sev,
                "latitude": coords[1],
                "longitude": coords[0],
                "location_name": event.get("title", ""),
                "url": event.get("link", ""),
                "timestamp": latest.get("date", ""),
            })
        logger.info("EONET: fetched %d events", len(results))
        return results
    except Exception as e:
        logger.warning("EONET fetch failed: %s", e)
        return []


async def _fetch_gdacs(client: httpx.AsyncClient) -> list[dict]:
    """GDACS recent disasters – past 30 days via their GeoJSON API."""
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?alertlevel=Green;Orange;Red&eventlist=EQ;TC;FL;VO;DR;WF&fromDate={from_date}&toDate={to_date}&limit=100"
    from_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    to_date = datetime.utcnow().strftime("%Y-%m-%d")
    url = url.format(from_date=from_date, to_date=to_date)
    try:
        r = await client.get(url, timeout=20, headers={"Accept": "application/json"})
        r.raise_for_status()
        data = r.json()
        results = []
        type_map = {"EQ": "earthquake", "TC": "cyclone", "FL": "flood", "VO": "volcanic_eruption", "DR": "drought", "WF": "wildfire"}
        features = data.get("features", [])
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [0, 0])
            if isinstance(coords, list) and len(coords) >= 2:
                lon, lat = coords[0], coords[1]
            else:
                continue
            etype = type_map.get(props.get("eventtype", ""), "other")
            results.append({
                "id": f"gdacs_{props.get('eventid', '')}_{props.get('episodeid', '')}",
                "source": "GDACS",
                "type": etype,
                "title": props.get("htmldescription", props.get("name", "GDACS Alert")),
                "description": props.get("description", ""),
                "severity": _gdacs_severity(props.get("alertlevel", "Green")),
                "latitude": lat,
                "longitude": lon,
                "location_name": props.get("country", props.get("name", "")),
                "url": props.get("url", {}).get("report", "") if isinstance(props.get("url"), dict) else str(props.get("url", "")),
                "timestamp": props.get("fromdate", ""),
                "alert_level": props.get("alertlevel", ""),
                "affected_population": props.get("population", {}).get("value") if isinstance(props.get("population"), dict) else None,
            })
        logger.info("GDACS: fetched %d events", len(results))
        return results
    except Exception as e:
        logger.warning("GDACS fetch failed: %s", e)
        return []


async def _fetch_reliefweb(client: httpx.AsyncClient) -> list[dict]:
    """ReliefWeb disasters – recent from UN OCHA."""
    url = "https://api.reliefweb.int/v1/disasters"
    payload = {
        "appname": "hopein-chaos",
        "limit": 80,
        "sort": ["date.event:desc"],
        "fields": {
            "include": ["name", "description", "status", "date.event", "date.created",
                        "country.name", "country.iso3", "type.name", "primary_type.name",
                        "glide", "url"]
        },
        "filter": {
            "field": "date.event",
            "value": {
                "from": (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%dT00:00:00+00:00")
            }
        }
    }
    try:
        r = await client.post(url, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = []
        type_map = {
            "Earthquake": "earthquake", "Flood": "flood", "Tropical Cyclone": "cyclone",
            "Volcano": "volcanic_eruption", "Drought": "drought", "Epidemic": "epidemic",
            "Storm": "cyclone", "Flash Flood": "flood", "Wild Fire": "wildfire",
            "Cold Wave": "other", "Heat Wave": "other", "Insect Infestation": "other",
            "Tsunami": "tsunami", "Landslide": "landslide", "Mud Slide": "landslide",
            "Technological Disaster": "other", "Complex Emergency": "other",
        }
        # Country center coords (rough estimates for mapping)
        country_coords = {
            "AFG": (33.9, 67.7), "BGD": (23.7, 90.4), "BRA": (-14.2, -51.9),
            "CHN": (35.9, 104.2), "COL": (4.6, -74.1), "COD": (-4.0, 21.8),
            "ETH": (9.1, 40.5), "GTM": (15.8, -90.2), "HTI": (19.0, -72.4),
            "IND": (20.6, 78.9), "IDN": (-0.8, 113.9), "IRN": (32.4, 53.7),
            "IRQ": (33.2, 43.7), "JPN": (36.2, 138.3), "KEN": (-0.02, 37.9),
            "MEX": (23.6, -102.6), "MMR": (21.9, 95.9), "NPL": (28.4, 84.1),
            "NGA": (9.1, 8.7), "PAK": (30.4, 69.3), "PHL": (12.9, 121.8),
            "SOM": (5.2, 46.2), "LKA": (7.9, 80.8), "SDN": (12.9, 30.2),
            "SYR": (34.8, 38.9), "TUR": (38.9, 35.2), "UKR": (48.4, 31.2),
            "USA": (37.1, -95.7), "VNM": (14.1, 108.3), "YEM": (15.6, 48.5),
            "AUS": (-25.3, 133.8), "CHL": (-35.7, -71.5), "PER": (-9.2, -75.0),
            "ECU": (-1.8, -78.2), "NZL": (-40.9, 174.9), "FJI": (-17.7, 178.1),
            "MOZ": (-18.7, 35.5), "MDG": (-18.8, 46.9), "ZAF": (-30.6, 22.9),
            "TZA": (-6.4, 34.9), "UGA": (1.4, 32.3), "MWI": (-13.3, 34.3),
            "ZMB": (-13.1, 27.8), "ZWE": (-19.0, 29.2), "AGO": (-11.2, 17.9),
            "CMR": (7.4, 12.4), "GHA": (7.9, -1.0), "SEN": (14.5, -14.5),
            "MLI": (17.6, -4.0), "NER": (17.6, 8.1), "TCD": (15.5, 18.7),
            "CAF": (6.6, 20.9), "RWA": (-1.9, 29.9), "BDI": (-3.4, 29.9),
        }
        for item in data.get("data", []):
            fields = item.get("fields", {})
            countries = fields.get("country", [])
            iso = countries[0].get("iso3", "") if countries else ""
            country_name = countries[0].get("name", "Unknown") if countries else "Unknown"
            lat, lon = country_coords.get(iso, (0, 0))
            ptype = fields.get("primary_type", {})
            type_name = ptype.get("name", "") if isinstance(ptype, dict) else str(ptype)
            dtype = type_map.get(type_name, "other")
            status = fields.get("status", "")

            results.append({
                "id": f"rw_{item.get('id', '')}",
                "source": "ReliefWeb",
                "type": dtype,
                "title": fields.get("name", "Disaster"),
                "description": fields.get("description", ""),
                "severity": _reliefweb_severity(status),
                "latitude": lat,
                "longitude": lon,
                "location_name": country_name,
                "url": fields.get("url", ""),
                "timestamp": fields.get("date", {}).get("event", "") if isinstance(fields.get("date"), dict) else "",
                "disaster_type_name": type_name,
                "glide": fields.get("glide", ""),
            })
        logger.info("ReliefWeb: fetched %d disasters", len(results))
        return results
    except Exception as e:
        logger.warning("ReliefWeb fetch failed: %s", e)
        return []


# ── Public aggregator ─────────────────────────────────────────────────────

async def get_global_disasters(
    source: Optional[str] = None,
    disaster_type: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 500,
) -> dict:
    """Aggregate live global disasters from all free public APIs.

    Returns deduplicated, normalised disaster events with coordinates.
    Uses a 5-minute cache to avoid hammering upstream APIs.
    """
    cache_key = f"global_disasters_{source}_{disaster_type}_{severity}_{limit}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = []
        if not source or source == "usgs":
            tasks.append(_fetch_usgs(client))
        if not source or source == "eonet":
            tasks.append(_fetch_eonet(client))
        if not source or source == "gdacs":
            tasks.append(_fetch_gdacs(client))
        if not source or source == "reliefweb":
            tasks.append(_fetch_reliefweb(client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_events: list[dict] = []
    sources_status: dict = {}
    source_names = []
    if not source or source == "usgs":
        source_names.append("usgs")
    if not source or source == "eonet":
        source_names.append("eonet")
    if not source or source == "gdacs":
        source_names.append("gdacs")
    if not source or source == "reliefweb":
        source_names.append("reliefweb")

    for i, res in enumerate(results):
        name = source_names[i] if i < len(source_names) else f"source_{i}"
        if isinstance(res, Exception):
            sources_status[name] = {"status": "error", "count": 0, "error": str(res)}
        else:
            sources_status[name] = {"status": "ok", "count": len(res)}
            all_events.extend(res)

    # Filter by type
    if disaster_type:
        all_events = [e for e in all_events if e.get("type") == disaster_type]

    # Filter by severity
    if severity:
        all_events = [e for e in all_events if e.get("severity") == severity]

    # Filter out events without coordinates
    all_events = [e for e in all_events if e.get("latitude") and e.get("longitude")]

    # Sort by timestamp desc
    _DATETIME_MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)

    def sort_key(e):
        ts = e.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                # Ensure timezone-aware
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
        return _DATETIME_MIN_UTC

    all_events.sort(key=sort_key, reverse=True)
    all_events = all_events[:limit]

    # Compute summary stats
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for e in all_events:
        by_type[e.get("type", "other")] = by_type.get(e.get("type", "other"), 0) + 1
        by_severity[e.get("severity", "medium")] = by_severity.get(e.get("severity", "medium"), 0) + 1
        by_source[e.get("source", "unknown")] = by_source.get(e.get("source", "unknown"), 0) + 1

    result = {
        "events": all_events,
        "total": len(all_events),
        "sources": sources_status,
        "stats": {
            "by_type": by_type,
            "by_severity": by_severity,
            "by_source": by_source,
        },
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    _set_cached(cache_key, result)
    return result
