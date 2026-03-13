"""
Phase 5 – Configuration for AI Dashboard.

All features use free, rule-based implementations.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Phase5Config:
    # ── Situation Reports ───────────────────────────────────────────
    SITREP_CRON_HOUR_UTC: int = int(os.getenv("SITREP_CRON_HOUR_UTC", "6"))  # 6 AM UTC daily
    SITREP_EMAIL_ENABLED: bool = os.getenv("SITREP_EMAIL_ENABLED", "false").lower() == "true"
    SITREP_ADMIN_EMAILS: list[str] = field(
        default_factory=lambda: [e.strip() for e in os.getenv("SITREP_ADMIN_EMAILS", "").split(",") if e.strip()]
    )

    # ── Natural Language Query ──────────────────────────────────────
    NL_QUERY_MAX_TOOL_CALLS: int = int(os.getenv("NL_QUERY_MAX_TOOL_CALLS", "5"))
    NL_QUERY_TIMEOUT_S: int = int(os.getenv("NL_QUERY_TIMEOUT_S", "30"))

    # ── Anomaly Detection ───────────────────────────────────────────
    ANOMALY_DETECTION_INTERVAL_S: int = int(os.getenv("ANOMALY_DETECTION_INTERVAL_S", "14400"))  # 4 hours
    ANOMALY_CONTAMINATION: float = float(os.getenv("ANOMALY_CONTAMINATION", "0.05"))  # 5% expected anomalies
    ANOMALY_MIN_SAMPLES: int = int(os.getenv("ANOMALY_MIN_SAMPLES", "20"))  # Min data points needed
    ANOMALY_LOOKBACK_HOURS: int = int(os.getenv("ANOMALY_LOOKBACK_HOURS", "48"))

    # ── Outcome Tracking ────────────────────────────────────────────
    EVALUATION_CRON_DAY: str = os.getenv("EVALUATION_CRON_DAY", "monday")  # Weekly on Monday
    EVALUATION_CRON_HOUR_UTC: int = int(os.getenv("EVALUATION_CRON_HOUR_UTC", "7"))
    EVALUATION_INTERVAL_HOURS: int = int(os.getenv("EVALUATION_INTERVAL_HOURS", "24"))
    EVALUATION_LOOKBACK_DAYS: int = int(os.getenv("EVALUATION_LOOKBACK_DAYS", "30"))
    AUTO_RETRAIN_THRESHOLD_MAE: float = float(os.getenv("AUTO_RETRAIN_THRESHOLD_MAE", "0.3"))
    AUTO_RETRAIN_THRESHOLD_ACCURACY: float = float(os.getenv("AUTO_RETRAIN_THRESHOLD_ACCURACY", "0.6"))

    # ── Internal API Base URL ───────────────────────────────────────
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")

    # ── SendGrid (free tier — 100 emails/day) ─────────────────────
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = os.getenv("SENDGRID_FROM_EMAIL", "reports@disaster-mgmt.org")


# Singleton
phase5_config = Phase5Config()
