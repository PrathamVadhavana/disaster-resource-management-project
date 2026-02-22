"""
Phase 4 – Ingestion configuration.

All settings are loaded from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class IngestionConfig:
    # ── OpenWeatherMap ──────────────────────────────────────────────
    OPENWEATHERMAP_API_KEY: str = os.getenv("OPENWEATHERMAP_API_KEY", "")
    OPENWEATHERMAP_BASE_URL: str = "https://api.openweathermap.org/data/2.5"
    WEATHER_POLL_INTERVAL_S: int = int(os.getenv("WEATHER_POLL_INTERVAL_S", "600"))

    # ── GDACS ───────────────────────────────────────────────────────
    GDACS_RSS_URL: str = "https://www.gdacs.org/xml/rss.xml"
    GDACS_POLL_INTERVAL_S: int = int(os.getenv("GDACS_POLL_INTERVAL_S", "900"))

    # ── USGS Earthquakes ────────────────────────────────────────────
    USGS_FEED_URL: str = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
    USGS_MIN_MAGNITUDE: float = float(os.getenv("USGS_MIN_MAGNITUDE", "4.0"))
    USGS_POLL_INTERVAL_S: int = int(os.getenv("USGS_POLL_INTERVAL_S", "300"))

    # ── NASA FIRMS ──────────────────────────────────────────────────
    FIRMS_API_KEY: str = os.getenv("FIRMS_API_KEY", "")
    FIRMS_BASE_URL: str = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
    FIRMS_SOURCE: str = os.getenv("FIRMS_SOURCE", "VIIRS_SNPP_NRT")
    FIRMS_POLL_INTERVAL_S: int = int(os.getenv("FIRMS_POLL_INTERVAL_S", "1800"))

    # ── Social Media (optional — requires paid Twitter API) ──────────
    TWITTER_BEARER_TOKEN: str = os.getenv("TWITTER_BEARER_TOKEN", "")
    SOCIAL_KEYWORDS: List[str] = field(default_factory=lambda: [
        "SOS", "help needed", "disaster", "earthquake", "flood",
        "rescue", "emergency relief", "trapped",
    ])
    SOCIAL_POLL_INTERVAL_S: int = int(os.getenv("SOCIAL_POLL_INTERVAL_S", "300"))

    # ── Notifications (SendGrid free tier — 100 emails/day) ──────
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = os.getenv("SENDGRID_FROM_EMAIL", "alerts@disaster-mgmt.org")
    ALERT_SEVERITY_THRESHOLD: str = os.getenv("ALERT_SEVERITY_THRESHOLD", "critical")

    # ── General ─────────────────────────────────────────────────────
    INGESTION_ENABLED: bool = os.getenv("INGESTION_ENABLED", "true").lower() == "true"
    MAX_EVENTS_PER_POLL: int = int(os.getenv("MAX_EVENTS_PER_POLL", "50"))


# Singleton
ingestion_config = IngestionConfig()
