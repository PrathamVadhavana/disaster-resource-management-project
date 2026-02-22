"""
Mock Data Generator for all external feed services.

Produces realistic synthetic disaster data so the entire pipeline
(disaster auto-creation → ML predictions → anomaly detection → alerts)
works end-to-end without any external API keys.

Each generator matches the exact return format of the real service
so the orchestrator processes them identically.
"""

from __future__ import annotations

import math
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

logger = logging.getLogger("ingestion.mock")

# ────────────────────────────────────────────────────────────────
# 1. REAL-WORLD DISASTER-PRONE REGIONS
# ────────────────────────────────────────────────────────────────

# (name, lat, lon, country, likely disaster types)
DISASTER_REGIONS: List[Tuple[str, float, float, str, List[str]]] = [
    # Earthquake zones
    ("Tokyo, Japan", 35.6762, 139.6503, "Japan", ["earthquake", "tsunami"]),
    ("San Francisco, USA", 37.7749, -122.4194, "USA", ["earthquake", "wildfire"]),
    ("Kathmandu, Nepal", 27.7172, 85.3240, "Nepal", ["earthquake", "landslide"]),
    ("Istanbul, Turkey", 41.0082, 28.9784, "Turkey", ["earthquake"]),
    ("Lima, Peru", -12.0464, -77.0428, "Peru", ["earthquake", "tsunami"]),
    ("Santiago, Chile", -33.4489, -70.6693, "Chile", ["earthquake"]),
    ("Mexico City, Mexico", 19.4326, -99.1332, "Mexico", ["earthquake"]),
    ("Manila, Philippines", 14.5995, 120.9842, "Philippines", ["earthquake", "hurricane"]),
    # Hurricane / Cyclone zones
    ("Miami, USA", 25.7617, -80.1918, "USA", ["hurricane", "flood"]),
    ("Houston, USA", 29.7604, -95.3698, "USA", ["hurricane", "flood"]),
    ("Dhaka, Bangladesh", 23.8103, 90.4125, "Bangladesh", ["flood", "hurricane"]),
    ("Mumbai, India", 19.0760, 72.8777, "India", ["flood", "hurricane"]),
    ("Havana, Cuba", 23.1136, -82.3666, "Cuba", ["hurricane"]),
    # Flood zones
    ("Jakarta, Indonesia", -6.2088, 106.8456, "Indonesia", ["flood", "earthquake"]),
    ("Bangkok, Thailand", 13.7563, 100.5018, "Thailand", ["flood"]),
    ("Venice, Italy", 45.4408, 12.3155, "Italy", ["flood"]),
    ("Wuhan, China", 30.5928, 114.3055, "China", ["flood"]),
    # Wildfire zones
    ("Los Angeles, USA", 34.0522, -118.2437, "USA", ["wildfire", "earthquake"]),
    ("Sydney, Australia", -33.8688, 151.2093, "Australia", ["wildfire"]),
    ("Athens, Greece", 37.9838, 23.7275, "Greece", ["wildfire", "earthquake"]),
    ("Brasilia, Brazil", -15.8267, -47.9218, "Brazil", ["wildfire", "drought"]),
    # Volcano zones
    ("Reykjavik, Iceland", 64.1466, -21.9426, "Iceland", ["volcano", "earthquake"]),
    ("Naples, Italy", 40.8518, 14.2681, "Italy", ["volcano", "earthquake"]),
    ("Yogyakarta, Indonesia", -7.7956, 110.3695, "Indonesia", ["volcano", "earthquake"]),
    # Drought zones
    ("Nairobi, Kenya", -1.2921, 36.8219, "Kenya", ["drought"]),
    ("Cape Town, South Africa", -33.9249, 18.4241, "South Africa", ["drought", "wildfire"]),
]

# Severity distribution weights (realistic: most disasters are low-medium)
SEVERITY_WEIGHTS = {
    "low": 0.30,
    "medium": 0.35,
    "high": 0.25,
    "critical": 0.10,
}

# ────────────────────────────────────────────────────────────────
# 2. WEATHER MOCK GENERATOR
# ────────────────────────────────────────────────────────────────

_WEATHER_CONDITIONS = [
    ("Clear", "clear sky"),
    ("Clouds", "scattered clouds"),
    ("Clouds", "overcast clouds"),
    ("Rain", "moderate rain"),
    ("Rain", "heavy intensity rain"),
    ("Thunderstorm", "thunderstorm with rain"),
    ("Snow", "light snow"),
    ("Drizzle", "light drizzle"),
    ("Mist", "mist"),
]


def generate_mock_weather(locations: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """
    Generate realistic weather observations.
    Returns data in the same format as WeatherService._fetch_current().
    """
    if not locations:
        # Pick 3-6 random disaster regions as locations
        count = random.randint(3, 6)
        sample = random.sample(DISASTER_REGIONS, min(count, len(DISASTER_REGIONS)))
        locations = [
            {"id": str(uuid4()), "name": r[0], "latitude": r[1], "longitude": r[2]}
            for r in sample
        ]

    observations = []
    now = datetime.now(timezone.utc)

    for loc in locations:
        lat = loc.get("latitude", 0)
        # Temperature based roughly on latitude (tropical = warmer)
        base_temp = 30 - abs(lat) * 0.4 + random.uniform(-5, 5)
        condition = random.choice(_WEATHER_CONDITIONS)

        # Increase precipitation for rain/storm
        precip = 0.0
        if "Rain" in condition[0] or "Thunderstorm" in condition[0]:
            precip = random.uniform(1.0, 25.0)
        elif "Snow" in condition[0]:
            precip = random.uniform(0.5, 8.0)
        elif "Drizzle" in condition[0]:
            precip = random.uniform(0.1, 2.0)

        obs = {
            "id": str(uuid4()),
            "location_id": loc.get("id"),
            "latitude": lat,
            "longitude": loc.get("longitude", 0),
            "temperature_c": round(base_temp, 1),
            "humidity_pct": random.randint(30, 95),
            "wind_speed_ms": round(random.uniform(0.5, 25.0), 1),
            "wind_deg": random.randint(0, 360),
            "pressure_hpa": random.randint(995, 1030),
            "precipitation_mm": round(precip, 1),
            "visibility_m": random.randint(2000, 10000),
            "weather_main": condition[0],
            "weather_desc": condition[1],
            "observed_at": now.isoformat(),
            "source": "mock_weather",
            "raw_payload": {
                "mock": True,
                "generator": "mock_data_service",
                "location_name": loc.get("name", "Unknown"),
            },
        }
        observations.append(obs)

    logger.info("Mock weather generated: %d observations", len(observations))
    return observations


# ────────────────────────────────────────────────────────────────
# 3. EARTHQUAKE (USGS) MOCK GENERATOR
# ────────────────────────────────────────────────────────────────

def generate_mock_earthquakes(count: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Generate realistic earthquake events in the same format
    as USGSService._parse_features() output.
    """
    if count is None:
        # 60% chance of 0 events (realistic), otherwise 1-3
        if random.random() < 0.6:
            count = 0
        else:
            count = random.randint(1, 3)

    if count == 0:
        return []

    # Filter to earthquake-prone regions
    eq_regions = [r for r in DISASTER_REGIONS if "earthquake" in r[4]]
    events = []
    now = datetime.now(timezone.utc)

    for _ in range(count):
        region = random.choice(eq_regions)
        # Add some jitter to coordinates (±0.5 degrees)
        lat = region[1] + random.uniform(-0.5, 0.5)
        lon = region[2] + random.uniform(-0.5, 0.5)

        magnitude = round(random.uniform(4.0, 8.5), 1)
        # Weight towards smaller earthquakes
        magnitude = round(4.0 + abs(random.gauss(0, 1.2)), 1)
        magnitude = min(magnitude, 9.0)
        depth_km = round(random.uniform(5, 300), 1)

        severity = _magnitude_to_severity(magnitude)
        place = f"{random.randint(5, 200)}km {'NSEW'[random.randint(0,3)]} of {region[0]}"
        usgs_id = f"mock{uuid4().hex[:10]}"

        events.append({
            "external_id": f"usgs-{usgs_id}",
            "event_type": "earthquake",
            "title": f"M{magnitude} - {place}",
            "description": f"M{magnitude} earthquake at {place}. Depth: {depth_km} km.",
            "severity": severity,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "location_name": place,
            "raw_payload": {
                "usgs_id": usgs_id,
                "magnitude": magnitude,
                "mag_type": "mww",
                "depth_km": depth_km,
                "place": place,
                "time": int(now.timestamp() * 1000),
                "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{usgs_id}",
                "tsunami": 1 if magnitude >= 7.0 else 0,
                "felt": random.randint(0, 500) if magnitude >= 5.0 else 0,
                "alert": severity if magnitude >= 5.5 else None,
                "status": "reviewed",
                "type": "earthquake",
                "mock": True,
            },
        })

    logger.info("Mock earthquakes generated: %d events", len(events))
    return events


def _magnitude_to_severity(mag: float) -> str:
    if mag >= 7.0:
        return "critical"
    elif mag >= 6.0:
        return "high"
    elif mag >= 5.0:
        return "medium"
    return "low"


# ────────────────────────────────────────────────────────────────
# 4. GDACS DISASTER MOCK GENERATOR
# ────────────────────────────────────────────────────────────────

_GDACS_DISASTER_TEMPLATES = [
    {
        "type": "hurricane",
        "gdacs_type": "TC",
        "title_tpl": "Tropical Cyclone {name} - Category {cat}",
        "desc_tpl": "Tropical Cyclone {name} with sustained winds of {wind}km/h affecting {region}. "
                    "Category {cat} storm. Population exposed: ~{pop:,}.",
        "params": lambda: {
            "name": random.choice([
                "Maria", "Irma", "Katrina", "Harvey", "Dorian", "Haiyan",
                "Amphan", "Nargis", "Sandy", "Michael", "Idai", "Winston",
            ]),
            "cat": random.randint(1, 5),
            "wind": random.randint(120, 300),
            "pop": random.randint(50000, 5000000),
        },
    },
    {
        "type": "flood",
        "gdacs_type": "FL",
        "title_tpl": "Flood Alert - {region}",
        "desc_tpl": "Severe flooding reported in {region}. Water level {level}m above normal. "
                    "Affected area: {area}km². Population exposed: ~{pop:,}.",
        "params": lambda: {
            "level": round(random.uniform(0.5, 8.0), 1),
            "area": random.randint(50, 5000),
            "pop": random.randint(10000, 2000000),
        },
    },
    {
        "type": "wildfire",
        "gdacs_type": "WF",
        "title_tpl": "Wildfire - {region}",
        "desc_tpl": "Active wildfire detected near {region}. Burning area: {area}ha. "
                    "Fire spread rate: {rate}ha/hr. Wind speed: {wind}km/h.",
        "params": lambda: {
            "area": random.randint(100, 50000),
            "rate": random.randint(5, 200),
            "wind": random.randint(10, 80),
        },
    },
    {
        "type": "volcano",
        "gdacs_type": "VO",
        "title_tpl": "Volcanic Activity - {region}",
        "desc_tpl": "Increased volcanic activity detected at {region}. "
                    "Alert level: {alert}. Ash plume height: {ash}km.",
        "params": lambda: {
            "alert": random.choice(["Warning", "Watch", "Advisory"]),
            "ash": round(random.uniform(1, 15), 1),
        },
    },
    {
        "type": "drought",
        "gdacs_type": "DR",
        "title_tpl": "Drought Alert - {region}",
        "desc_tpl": "Severe drought conditions in {region}. "
                    "Rainfall deficit: {deficit}% below average. Duration: {months} months.",
        "params": lambda: {
            "deficit": random.randint(40, 90),
            "months": random.randint(2, 18),
        },
    },
]

_ALERT_LEVELS = ["Green", "Orange", "Red"]
_ALERT_WEIGHTS = [0.35, 0.40, 0.25]
_SEVERITY_MAP = {"Red": "critical", "Orange": "high", "Green": "medium"}


def generate_mock_gdacs_events(count: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Generate realistic GDACS-style disaster alerts in the same
    format as GDACSService._parse_item() output.
    """
    if count is None:
        if random.random() < 0.5:
            count = 0
        else:
            count = random.randint(1, 3)

    if count == 0:
        return []

    events = []
    now = datetime.now(timezone.utc)

    for _ in range(count):
        template = random.choice(_GDACS_DISASTER_TEMPLATES)
        dtype = template["type"]

        # Pick a region appropriate for this disaster type
        matching_regions = [r for r in DISASTER_REGIONS if dtype in r[4]]
        if not matching_regions:
            matching_regions = DISASTER_REGIONS
        region = random.choice(matching_regions)

        lat = region[1] + random.uniform(-1.0, 1.0)
        lon = region[2] + random.uniform(-1.0, 1.0)

        params = template["params"]()
        params["region"] = region[0]

        alert_level = random.choices(_ALERT_LEVELS, weights=_ALERT_WEIGHTS, k=1)[0]
        severity = _SEVERITY_MAP[alert_level]
        event_id = str(random.randint(1000000, 9999999))

        title = template["title_tpl"].format(**params)
        description = template["desc_tpl"].format(**params)

        events.append({
            "external_id": f"gdacs-{template['gdacs_type']}-{event_id}",
            "event_type": "gdacs_alert",
            "title": title,
            "description": description,
            "severity": severity,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "location_name": region[0],
            "raw_payload": {
                "link": f"https://www.gdacs.org/report.aspx?eventid={event_id}",
                "pub_date": now.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                "gdacs_event_type": template["gdacs_type"],
                "gdacs_alert_level": alert_level,
                "gdacs_event_id": event_id,
                "gdacs_severity": str(params.get("cat", params.get("level", "N/A"))),
                "gdacs_population": str(params.get("pop", 0)),
                "disaster_type_mapped": dtype,
                "mock": True,
            },
        })

    logger.info("Mock GDACS events generated: %d events", len(events))
    return events


# ────────────────────────────────────────────────────────────────
# 5. FIRMS FIRE HOTSPOT MOCK GENERATOR
# ────────────────────────────────────────────────────────────────

def generate_mock_fire_hotspots(count: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Generate realistic satellite fire hotspot observations in the
    same format as FIRMSService._parse_csv() output.
    """
    if count is None:
        if random.random() < 0.4:
            count = 0
        else:
            count = random.randint(3, 15)

    if count == 0:
        return []

    fire_regions = [r for r in DISASTER_REGIONS if "wildfire" in r[4]]
    observations = []
    now = datetime.now(timezone.utc)

    for _ in range(count):
        region = random.choice(fire_regions)
        # Cluster hotspots around the region (±0.3 degrees)
        lat = region[1] + random.uniform(-0.3, 0.3)
        lon = region[2] + random.uniform(-0.3, 0.3)

        brightness = round(random.uniform(300, 500), 1)
        frp = round(random.uniform(5, 200), 1)
        confidence = random.choice(["low", "nominal", "high"])
        satellite = random.choice(["N20", "NOAA-20", "Suomi NPP"])
        acq_date = now.strftime("%Y-%m-%d")
        acq_time = f"{now.hour:02d}{now.minute:02d}"

        observations.append({
            "id": str(uuid4()),
            "source": "mock_firms",
            "external_id": f"firms-{lat:.4f}-{lon:.4f}-{acq_date}-{acq_time}-{uuid4().hex[:6]}",
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "brightness": brightness,
            "frp": frp,
            "confidence": confidence,
            "satellite": satellite,
            "instrument": "VIIRS",
            "acq_datetime": now.isoformat(),
            "daynight": random.choice(["D", "N"]),
            "raw_payload": {
                "mock": True,
                "brightness": brightness,
                "frp": frp,
                "region": region[0],
            },
        })

    logger.info("Mock fire hotspots generated: %d observations", len(observations))
    return observations


# ────────────────────────────────────────────────────────────────
# 6. SOCIAL MEDIA MOCK GENERATOR
# ────────────────────────────────────────────────────────────────

_SOCIAL_SOS_TEMPLATES = [
    "URGENT: Flooding in {region}, people trapped on rooftops. Need immediate rescue! #SOS #disaster",
    "Major earthquake just hit {region}. Buildings collapsed. Please send help! #earthquake #emergency",
    "Wildfire spreading rapidly near {region}. Evacuations underway. #wildfire #help",
    "Hurricane approaching {region}. Category {cat} winds. Seeking shelter. #hurricane",
    "Severe flooding in {region}. Roads washed out. Family of {fam} needs rescue. #flood #SOS",
    "Volcanic eruption near {region}! Ash cloud rising. Emergency evacuation needed. #volcano",
    "Landslide in {region} has buried homes. Multiple people missing. #landslide #rescue",
    "Critical water shortage in {region}. {days} days without clean water. Children sick. #drought #help",
    "Aftershock M{mag} in {region}. More buildings damaged. Urgent medical supplies needed.",
    "SOS from {region}: {fam} people stranded after flash flood. No food or water for {days} days.",
]


def generate_mock_social_signals(count: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Generate realistic social media SOS signals in the same
    format as SocialMediaService._tweets_to_events() output.
    """
    if count is None:
        if random.random() < 0.5:
            count = 0
        else:
            count = random.randint(1, 4)

    if count == 0:
        return []

    events = []
    now = datetime.now(timezone.utc)

    for _ in range(count):
        region = random.choice(DISASTER_REGIONS)
        template = random.choice(_SOCIAL_SOS_TEMPLATES)

        params = {
            "region": region[0],
            "cat": random.randint(1, 5),
            "fam": random.randint(2, 8),
            "days": random.randint(1, 7),
            "mag": round(random.uniform(4.0, 6.5), 1),
        }
        text = template.format(**params)
        tweet_id = str(random.randint(10**17, 10**18))

        lat = region[1] + random.uniform(-0.2, 0.2)
        lon = region[2] + random.uniform(-0.2, 0.2)

        severity = _estimate_social_severity(text)

        events.append({
            "external_id": f"twitter-{tweet_id}",
            "event_type": "social_sos",
            "title": f"Social SOS: {text[:80]}{'...' if len(text) > 80 else ''}",
            "description": text,
            "severity": severity,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "location_name": region[0],
            "raw_payload": {
                "tweet_id": tweet_id,
                "author_id": str(random.randint(10**8, 10**9)),
                "created_at": now.isoformat(),
                "text": text,
                "public_metrics": {
                    "retweet_count": random.randint(0, 5000),
                    "reply_count": random.randint(0, 500),
                    "like_count": random.randint(0, 10000),
                },
                "mock": True,
            },
        })

    logger.info("Mock social signals generated: %d events", len(events))
    return events


def _estimate_social_severity(text: str) -> str:
    text_lower = text.lower()
    critical_words = ["trapped", "dying", "urgent", "critical", "sos", "life threatening"]
    high_words = ["help needed", "rescue", "emergency", "injured", "flood", "earthquake"]
    c = sum(1 for w in critical_words if w in text_lower)
    h = sum(1 for w in high_words if w in text_lower)
    if c >= 2:
        return "critical"
    if c >= 1 or h >= 2:
        return "high"
    if h >= 1:
        return "medium"
    return "low"
