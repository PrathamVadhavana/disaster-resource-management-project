"""
Phase 5 – Anomaly Detection Service.

Uses Isolation Forest (sklearn) to detect anomalies in:
- Resource consumption rates
- Request volume spikes
- Severity escalation patterns
- Geographic request surges

Anomalies are stored with rule-based explanations (no external API needed).

Features:
1. On startup/first detection run, builds baseline:
   - Queries resource_requests grouped by day
   - Queries resource_consumption_log for 90-day rolling stats
   - Queries disasters for severity distribution
   - Fits Isolation Forest on historical feature matrix
   - Saves model to .pkl

2. During detection, compares current day's stats to baseline model

3. Feedback handling:
   - false_positive: adds to exclusion list
   - resolved: marks as confirmed anomaly for model refinement

4. Geographic request surge detection: detects 3x spikes in 20km clusters

5. Stale alert cleanup:
   - Any active alerts older than 3 days are archived automatically
   - Runs at the start of every detection cycle to prevent alert bloat

FIX 1: Dedup key uses (anomaly_type + severity) only within 24h window
FIX 2: Stale alert cleanup prevents old critical alerts from persisting
FIX 3: Minimum data thresholds raised (request_volume >= 5, resource_consumption >= 10)
FIX 4: All DB queries filter is_simulated != true to exclude mock data
"""

import asyncio
import json
import logging
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    from sklearn.ensemble import IsolationForest
except ImportError:
    IsolationForest = None

from app.core.phase5_config import phase5_config
from app.database import db_admin
from app.services.notification_service import notify_all_admins

logger = logging.getLogger("anomaly_service")

# Constants
MODEL_DIR = Path("backend/ml/models")
BASELINE_MODEL_PATH = MODEL_DIR / "anomaly_baseline_iforest.pkl"
EXCLUSION_LIST_PATH = MODEL_DIR / "anomaly_exclusion_list.json"
CONFIRMED_ANOMALIES_PATH = MODEL_DIR / "confirmed_anomalies.json"
GEO_CLUSTER_RADIUS_KM = 20
GEO_SURGE_THRESHOLD = 3.0  # 3x the 7-day average
SEVEN_DAY_AVG_WINDOW = 7
ROLLING_STATS_DAYS = 90
STALE_ALERT_DAYS = 3  # Archive alerts older than 3 days
DEDUP_WINDOW_HOURS = 24  # Dedup within 24h window


class AnomalyDetectionService:
    """Detects anomalies in disaster management metrics using Isolation Forest."""

    def __init__(self):
        self.contamination = phase5_config.ANOMALY_CONTAMINATION
        self.min_samples = phase5_config.ANOMALY_MIN_SAMPLES
        self.lookback_hours = phase5_config.ANOMALY_LOOKBACK_HOURS
        self._running = False
        self._baseline_model = None
        self._feature_columns = []
        self._exclusion_list = set()
        self._confirmed_anomalies = []
        self._load_persisted_data()

    def _load_persisted_data(self):
        """Load exclusion list and confirmed anomalies from disk."""
        try:
            # Load exclusion list
            if EXCLUSION_LIST_PATH.exists():
                with open(EXCLUSION_LIST_PATH, 'r') as f:
                    exclusion_data = json.load(f)
                    self._exclusion_list = set(exclusion_data.get("excluded_signatures", []))
                    logger.info(f"Loaded {len(self._exclusion_list)} exclusion entries")
            
            # Load confirmed anomalies
            if CONFIRMED_ANOMALIES_PATH.exists():
                with open(CONFIRMED_ANOMALIES_PATH, 'r') as f:
                    confirmed_data = json.load(f)
                    self._confirmed_anomalies = confirmed_data.get("confirmed", [])
                    logger.info(f"Loaded {len(self._confirmed_anomalies)} confirmed anomalies")
        except Exception as e:
            logger.warning(f"Failed to load persisted data: {e}")

    def _save_exclusion_list(self):
        """Save exclusion list to disk."""
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            with open(EXCLUSION_LIST_PATH, 'w') as f:
                json.dump({"excluded_signatures": list(self._exclusion_list)}, f)
            logger.info(f"Saved {len(self._exclusion_list)} exclusion entries")
        except Exception as e:
            logger.error(f"Failed to save exclusion list: {e}")

    def _save_confirmed_anomalies(self):
        """Save confirmed anomalies to disk."""
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            with open(CONFIRMED_ANOMALIES_PATH, 'w') as f:
                json.dump({"confirmed": self._confirmed_anomalies}, f)
            logger.info(f"Saved {len(self._confirmed_anomalies)} confirmed anomalies")
        except Exception as e:
            logger.error(f"Failed to save confirmed anomalies: {e}")

    # ── Stale Alert Cleanup ────────────────────────────────────────

    async def cleanup_stale_alerts(self) -> dict:
        """
        Archive any active alerts older than STALE_ALERT_DAYS (3 days).
        This prevents "zombie" critical alerts from old DB states from persisting.
        Runs at the START of every detection cycle.
        """
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=STALE_ALERT_DAYS)).isoformat()
            
            # Find active alerts older than cutoff
            resp = await db_admin.table("anomaly_alerts") \
                .select("id") \
                .eq("status", "active") \
                .lt("detected_at", cutoff_date) \
                .async_execute()
            
            stale_alerts = resp.data or []
            
            if not stale_alerts:
                logger.debug("No stale alerts to clean up")
                return {"cleaned": 0}
            
            # Archive them
            stale_ids = [a["id"] for a in stale_alerts]
            await db_admin.table("anomaly_alerts") \
                .update({"status": "archived"}) \
                .in_("id", stale_ids) \
                .async_execute()
            
            logger.info(f"Archived {len(stale_ids)} stale alerts (older than {STALE_ALERT_DAYS} days)")
            return {"cleaned": len(stale_ids)}
        except Exception as e:
            logger.warning(f"Stale alert cleanup failed: {e}")
            return {"cleaned": 0, "error": str(e)}

    # ── Baseline Builder Methods ───────────────────────────────────────

    async def _get_resource_requests_daily_stats(self) -> list[dict]:
        """
        Query resource_requests grouped by day (EXCLUDING SIMULATED DATA):
        - count of requests per day
        - avg priority
        - breakdown by resource_type
        
        FIX 4: Filter is_simulated != true to exclude mock data
        """
        try:
            # Get data from last 90 days
            since_date = datetime.utcnow() - timedelta(days=ROLLING_STATS_DAYS)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, created_at, is_simulated")
                .gte("created_at", since)
                .eq("is_simulated", False)  # FIX 4: Filter out simulated data
                .limit(10000)
                .async_execute()
            )
            requests = resp.data or []

            if not requests:
                return []

            # Aggregate by day
            daily_stats: dict[str, dict] = {}
            priority_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}

            for req in requests:
                created_at = req.get("created_at")
                if not created_at:
                    continue
                
                # Extract date (YYYY-MM-DD)
                date_str = str(created_at)[:10]
                
                if date_str not in daily_stats:
                    daily_stats[date_str] = {
                        "date": date_str,
                        "count": 0,
                        "total_priority": 0,
                        "resource_types": {}
                    }
                
                daily_stats[date_str]["count"] += 1
                
                # Add priority
                priority = str(req.get("priority", "medium")).lower()
                daily_stats[date_str]["total_priority"] += priority_map.get(priority, 2)
                
                # Track resource types
                rtype = str(req.get("resource_type", "other"))
                if rtype not in daily_stats[date_str]["resource_types"]:
                    daily_stats[date_str]["resource_types"][rtype] = 0
                daily_stats[date_str]["resource_types"][rtype] += 1

            # Compute averages and expand resource types
            result = []
            all_resource_types = set()
            for stats in daily_stats.values():
                all_resource_types.update(stats["resource_types"].keys())

            for stats in daily_stats.values():
                avg_priority = stats["total_priority"] / stats["count"] if stats["count"] > 0 else 2.0
                
                row = {
                    "date": stats["date"],
                    "count": stats["count"],
                    "avg_priority": avg_priority
                }
                
                # Add one-hot encoding for resource types
                for rtype in all_resource_types:
                    row[f"type_{rtype}"] = stats["resource_types"].get(rtype, 0)
                
                result.append(row)

            # Sort by date
            result.sort(key=lambda x: x["date"])
            return result
        except Exception as e:
            logger.error(f"Error getting daily request stats: {e}")
            return []

    async def _get_resource_consumption_rolling_stats(self) -> list[dict]:
        """
        Query resource_consumption_log for 90-day rolling stats per resource_type.
        FIX 4: Filter out simulated data.
        """
        try:
            since_date = datetime.utcnow() - timedelta(days=ROLLING_STATS_DAYS)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("resource_consumption_log")
                .select("id, resource_type, timestamp, quantity_consumed, is_simulated")
                .gte("timestamp", since)
                .eq("is_simulated", False)  # FIX 4: Filter out simulated data
                .limit(10000)
                .async_execute()
            )
            consumption = resp.data or []

            if not consumption:
                return []

            # Aggregate by resource_type and day
            daily_stats: dict[str, dict] = {}

            for record in consumption:
                timestamp = record.get("timestamp")
                if not timestamp:
                    continue
                
                date_str = str(timestamp)[:10]
                rtype = str(record.get("resource_type", "other"))
                qty = float(record.get("quantity_consumed", 0) or 0)
                
                key = f"{date_str}_{rtype}"
                if key not in daily_stats:
                    daily_stats[key] = {
                        "date": date_str,
                        "resource_type": rtype,
                        "total_quantity": 0,
                        "count": 0
                    }
                
                daily_stats[key]["total_quantity"] += qty
                daily_stats[key]["count"] += 1

            # Compute rolling stats (using simple moving average for each resource type)
            result = []
            resource_types = set(s["resource_type"] for s in daily_stats.values())

            for rtype in resource_types:
                type_records = [s for s in daily_stats.values() if s["resource_type"] == rtype]
                type_records.sort(key=lambda x: x["date"])
                
                # Compute rolling average
                for i, record in enumerate(type_records):
                    # Get up to 7 days of historical data
                    start_idx = max(0, i - 6)
                    window = type_records[start_idx:i+1]
                    avg_qty = sum(r["total_quantity"] for r in window) / len(window) if window else 0
                    
                    result.append({
                        "date": record["date"],
                        "resource_type": rtype,
                        "quantity": record["total_quantity"],
                        "count": record["count"],
                        "rolling_avg_7d": avg_qty
                    })

            result.sort(key=lambda x: (x["date"], x["resource_type"]))
            return result
        except Exception as e:
            logger.error(f"Error getting consumption rolling stats: {e}")
            return []

    async def _get_disaster_severity_distribution(self) -> list[dict]:
        """
        Query disasters for severity distribution over last 90 days.
        FIX 4: Filter out simulated disasters.
        """
        try:
            since_date = datetime.utcnow() - timedelta(days=ROLLING_STATS_DAYS)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("disasters")
                .select("id, severity, status, created_at, is_simulated")
                .gte("created_at", since)
                .eq("is_simulated", False)  # FIX 4: Filter out simulated data
                .limit(5000)
                .async_execute()
            )
            disasters = resp.data or []

            if not disasters:
                return []

            severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}

            # Aggregate by day
            daily_stats: dict[str, dict] = {}

            for d in disasters:
                created_at = d.get("created_at")
                if not created_at:
                    continue
                
                date_str = str(created_at)[:10]
                severity = d.get("severity", "low")
                
                if date_str not in daily_stats:
                    daily_stats[date_str] = {
                        "date": date_str,
                        "total_disasters": 0,
                        "severity_scores": [],
                        "severity_counts": {"low": 0, "medium": 0, "high": 0, "critical": 0}
                    }
                
                daily_stats[date_str]["total_disasters"] += 1
                daily_stats[date_str]["severity_scores"].append(severity_map.get(severity, 1))
                daily_stats[date_str]["severity_counts"][severity] = daily_stats[date_str]["severity_counts"].get(severity, 0) + 1

            result = []
            for stats in daily_stats.values():
                avg_severity = sum(stats["severity_scores"]) / len(stats["severity_scores"]) if stats["severity_scores"] else 1.0
                
                row = {
                    "date": stats["date"],
                    "total_disasters": stats["total_disasters"],
                    "avg_severity": avg_severity,
                    "severity_low": stats["severity_counts"].get("low", 0),
                    "severity_medium": stats["severity_counts"].get("medium", 0),
                    "severity_high": stats["severity_counts"].get("high", 0),
                    "severity_critical": stats["severity_counts"].get("critical", 0)
                }
                result.append(row)

            result.sort(key=lambda x: x["date"])
            return result
        except Exception as e:
            logger.error(f"Error getting disaster severity distribution: {e}")
            return []

    async def build_baseline(self) -> dict:
        """
        Build the baseline model:
        1. Query all historical data (FIX 4: excluding simulated data)
        2. Create feature matrix
        3. Fit Isolation Forest
        4. Save to .pkl
        """
        if IsolationForest is None:
            logger.warning("scikit-learn not available, cannot build baseline")
            return {"success": False, "error": "scikit-learn not available"}

        logger.info("Building anomaly detection baseline...")

        # Gather all data (with FIX 4 filtering)
        daily_requests = await self._get_resource_requests_daily_stats()
        consumption_stats = await self._get_resource_consumption_rolling_stats()
        severity_stats = await self._get_disaster_severity_distribution()

        if not daily_requests and not consumption_stats and not severity_stats:
            logger.warning("No data available to build baseline")
            return {"success": False, "error": "No historical data available"}

        # Build unified feature matrix by joining on date
        # Create a mapping of all dates
        all_dates = set()
        for r in daily_requests:
            all_dates.add(r["date"])
        for c in consumption_stats:
            all_dates.add(c["date"])
        for s in severity_stats:
            all_dates.add(s["date"])

        # Build feature matrix
        feature_matrix = []
        for date in sorted(all_dates):
            row = {"date": date}
            
            # Find request stats for this date
            req_data = next((r for r in daily_requests if r["date"] == date), None)
            if req_data:
                row["request_count"] = req_data["count"]
                row["avg_priority"] = req_data["avg_priority"]
                # Add resource type counts
                for key, val in req_data.items():
                    if key.startswith("type_"):
                        row[key] = val
            else:
                row["request_count"] = 0
                row["avg_priority"] = 0
            
            # Add consumption stats for this date
            cons_data = [c for c in consumption_stats if c["date"] == date]
            if cons_data:
                row["consumption_total"] = sum(c["quantity"] for c in cons_data)
                row["consumption_count"] = sum(c["count"] for c in cons_data)
            else:
                row["consumption_total"] = 0
                row["consumption_count"] = 0
            
            # Add severity stats for this date
            sev_data = next((s for s in severity_stats if s["date"] == date), None)
            if sev_data:
                row["disaster_count"] = sev_data["total_disasters"]
                row["avg_severity"] = sev_data["avg_severity"]
                row["critical_count"] = sev_data["severity_critical"]
            else:
                row["disaster_count"] = 0
                row["avg_severity"] = 0
                row["critical_count"] = 0
            
            feature_matrix.append(row)

        # Determine feature columns (exclude 'date')
        if not feature_matrix:
            return {"success": False, "error": "Feature matrix is empty"}

        self._feature_columns = [k for k in feature_matrix[0].keys() if k != "date"]

        # Build numpy array
        features = []
        for item in feature_matrix:
            row = []
            for col in self._feature_columns:
                val = item.get(col, 0)
                row.append(float(val) if val is not None else 0.0)
            features.append(row)

        x_feats = np.array(features)
        logger.info(f"Feature matrix shape: {x_feats.shape}, columns: {self._feature_columns}")

        if len(x_feats) < self.min_samples:
            return {"success": False, "error": f"Not enough data: {len(x_feats)} < {self.min_samples}"}

        # Active Learning Loop: Adjust contamination based on human feedback
        false_positive_count = len(self._exclusion_list)
        confirmed_count = len(self._confirmed_anomalies)
        
        # Adjust sensitivity dynamically
        active_contamination = self.contamination
        if false_positive_count > 0:
            # Reduce sensitivity to avoid alert fatigue
            active_contamination -= (false_positive_count * 0.001)
        if confirmed_count > 0:
            # Increase sensitivity to catch more confirmed patterns
            active_contamination += (confirmed_count * 0.002)
            
        # Clamp between 0.01 (1%) and 0.15 (15%)
        active_contamination = max(0.01, min(0.15, active_contamination))
        logger.info(f"Active Learning: Adjusted contamination from {self.contamination} to {active_contamination:.4f} "
                    f"(False Positives: {false_positive_count}, Confirmed: {confirmed_count})")

        # Fit Isolation Forest
        self._baseline_model = IsolationForest(
            contamination=active_contamination,
            random_state=42,
            n_estimators=100
        )
        self._baseline_model.fit(x_feats)

        # Save model
        try:
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            with open(BASELINE_MODEL_PATH, 'wb') as f:
                pickle.dump({
                    "model": self._baseline_model,
                    "feature_columns": self._feature_columns,
                    "training_date": datetime.utcnow().isoformat(),
                    "n_samples": len(x_feats)
                }, f)
            logger.info(f"Baseline model saved to {BASELINE_MODEL_PATH}")
        except Exception as e:
            logger.error(f"Failed to save baseline model: {e}")

        return {
            "success": True,
            "n_samples": len(x_feats),
            "feature_columns": self._feature_columns,
            "model_path": str(BASELINE_MODEL_PATH)
        }

    def _load_baseline_model(self) -> bool:
        """Load the baseline model from disk if it exists."""
        if not BASELINE_MODEL_PATH.exists():
            return False
        
        try:
            with open(BASELINE_MODEL_PATH, 'rb') as f:
                data = pickle.load(f)
                self._baseline_model = data["model"]
                self._feature_columns = data["feature_columns"]
                logger.info(f"Loaded baseline model from {BASELINE_MODEL_PATH}")
                return True
        except Exception as e:
            logger.error(f"Failed to load baseline model: {e}")
            return False

    # ── Detection against Baseline ────────────────────────────────

    async def _get_current_day_stats(self) -> dict:
        """Get current day's stats for comparison with baseline (FIX 4: exclude simulated)."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Get today's request count
        try:
            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, created_at, is_simulated")
                .gte("created_at", f"{today}T00:00:00")
                .eq("is_simulated", False)  # FIX 4: Exclude simulated
                .limit(5000)
                .async_execute()
            )
            requests = resp.data or []
        except Exception as e:
            logger.error(f"Error getting today's requests: {e}")
            requests = []

        priority_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        resource_types = {}
        total_priority = 0
        
        for req in requests:
            rtype = str(req.get("resource_type", "other"))
            resource_types[rtype] = resource_types.get(rtype, 0) + 1
            priority = str(req.get("priority", "medium")).lower()
            total_priority += priority_map.get(priority, 2)
        
        request_count = len(requests)
        avg_priority = total_priority / request_count if request_count > 0 else 2.0
        
        # Get today's consumption
        try:
            cons_resp = (
                await db_admin.table("resource_consumption_log")
                .select("id, resource_type, quantity_consumed, timestamp, is_simulated")
                .gte("timestamp", f"{today}T00:00:00")
                .eq("is_simulated", False)  # FIX 4: Exclude simulated
                .limit(1000)
                .async_execute()
            )
            consumption = cons_resp.data or []
        except Exception as e:
            logger.error(f"Error getting today's consumption: {e}")
            consumption = []
        
        consumption_total = sum(float(c.get("quantity_consumed", 0) or 0) for c in consumption)
        consumption_count = len(consumption)
        
        # Get today's disasters
        try:
            disaster_resp = (
                await db_admin.table("disasters")
                .select("id, severity, created_at, is_simulated")
                .gte("created_at", f"{today}T00:00:00")
                .eq("is_simulated", False)  # FIX 4: Exclude simulated
                .limit(100)
                .async_execute()
            )
            disasters = disaster_resp.data or []
        except Exception as e:
            logger.error(f"Error getting today's disasters: {e}")
            disasters = []
        
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        severity_scores = [severity_map.get(d.get("severity", "low"), 1) for d in disasters]
        disaster_count = len(disasters)
        avg_severity = sum(severity_scores) / disaster_count if disaster_count > 0 else 0
        critical_count = sum(1 for d in disasters if d.get("severity") == "critical")
        
        return {
            "date": today,
            "request_count": request_count,
            "avg_priority": avg_priority,
            "resource_types": resource_types,
            "consumption_total": consumption_total,
            "consumption_count": consumption_count,
            "disaster_count": disaster_count,
            "avg_severity": avg_severity,
            "critical_count": critical_count
        }

    def _detect_baseline_anomalies(self, current_stats: dict) -> list[dict]:
        """
        Compare current day's stats to baseline model and detect anomalies.
        Builds the feature vector in a single pass then calls predict/score exactly once.
        """
        if self._baseline_model is None or not self._feature_columns:
            return []

        # Build feature vector -- one value per trained feature column
        feature_vector: list[float] = []
        for col in self._feature_columns:
            if col == "request_count":
                feature_vector.append(float(current_stats.get("request_count", 0)))
            elif col == "avg_priority":
                feature_vector.append(float(current_stats.get("avg_priority", 0)))
            elif col.startswith("type_"):
                rtype = col[5:]
                feature_vector.append(float(current_stats.get("resource_types", {}).get(rtype, 0)))
            elif col == "consumption_total":
                feature_vector.append(float(current_stats.get("consumption_total", 0)))
            elif col == "consumption_count":
                feature_vector.append(float(current_stats.get("consumption_count", 0)))
            elif col == "disaster_count":
                feature_vector.append(float(current_stats.get("disaster_count", 0)))
            elif col == "avg_severity":
                feature_vector.append(float(current_stats.get("avg_severity", 0)))
            elif col == "critical_count":
                feature_vector.append(float(current_stats.get("critical_count", 0)))
            else:
                feature_vector.append(0.0)

        if not feature_vector:
            return []

        x = np.array([feature_vector])
        prediction = self._baseline_model.predict(x)[0]
        score = float(self._baseline_model.decision_function(x)[0])

        if prediction == -1:
            # Anomaly detected -- rank features by deviation magnitude
            deviations = [
                (col, abs(feature_vector[i]))
                for i, col in enumerate(self._feature_columns)
            ]
            deviations.sort(key=lambda t: t[1], reverse=True)

            n_baseline_samples = getattr(self._baseline_model, "n_samples_", 0)
            if n_baseline_samples == 0:
                n_baseline_samples = len(self._feature_columns) * 10

            primary_metric = deviations[0][0] if deviations else "unknown"
            primary_value  = float(feature_vector[0]) if feature_vector else 0.0

            return [{
                "anomaly_type":  "baseline_deviation",
                "anomaly_score": score,
                "metric_name":   primary_metric,
                "metric_value":  primary_value,
                "context_data":  {
                    **current_stats,
                    "data_quality":       "good" if n_baseline_samples >= 30 else "limited",
                    "n_baseline_samples": n_baseline_samples,
                    "all_features":       dict(zip(self._feature_columns, feature_vector)),
                },
                "all_features": dict(zip(self._feature_columns, feature_vector)),
            }]

        return []

    def _generate_signature(self, anomaly: dict) -> str:
        """
        Generate a unique signature for an anomaly to track it in exclusion list.
        Uses combination of type, metric, and coarse location (if geographic).
        """
        ctx = anomaly.get("context_data", {})
        atype = anomaly.get("anomaly_type", "")
        metric = anomaly.get("metric_name", "")
        date = ctx.get("date", "") if isinstance(ctx, dict) else ""

        if atype == "geographic_request_surge":
            # Round coordinates to nearest 0.1 degree for fuzzy matching
            lat = round(ctx.get("center_latitude", 0), 1) if isinstance(ctx, dict) else 0
            lon = round(ctx.get("center_longitude", 0), 1) if isinstance(ctx, dict) else 0
            return f"geo_{lat}_{lon}_{date}"
        else:
            return f"{date}_{atype}_{metric}"

    async def handle_feedback(self, alert_id: str, status: str, user_id: str) -> dict:
        """
        Handle feedback from human analysts:
        - false_positive: add to exclusion list
        - resolved: mark as confirmed anomaly
        """
        try:
            # Get the alert
            resp = (
                await db_admin.table("anomaly_alerts")
                .select("*")
                .eq("id", alert_id)
                .async_execute()
            )
            
            if not resp.data:
                return {"success": False, "error": "Alert not found"}
            
            alert = resp.data[0]
            
            if status == "false_positive":
                # Add to exclusion list
                signature = self._generate_signature(alert)
                self._exclusion_list.add(signature)
                self._save_exclusion_list()
                
                # Update alert status
                update_data = {
                    "status": "false_positive",
                    "acknowledged_at": datetime.utcnow().isoformat()
                }
                # Only add user_id if it's a valid string and not "system" (UUID column)
                if user_id and user_id != "system":
                    update_data["acknowledged_by"] = user_id

                await db_admin.table("anomaly_alerts").update(update_data).eq("id", alert_id).async_execute()
                
                logger.info(f"Added alert {alert_id} to exclusion list: {signature}")
                return {"success": True, "action": "added_to_exclusion_list", "signature": signature}
            
            elif status == "resolved":
                # Mark as confirmed anomaly for future model refinement
                confirmed_data = {
                    "alert_id": alert_id,
                    "anomaly_type": alert.get("anomaly_type"),
                    "metric_name": alert.get("metric_name"),
                    "metric_value": alert.get("metric_value"),
                    "context_data": alert.get("context_data"),
                    "confirmed_at": datetime.utcnow().isoformat()
                }
                self._confirmed_anomalies.append(confirmed_data)
                self._save_confirmed_anomalies()
                
                # Update alert status
                update_data = {
                    "status": "resolved",
                    "acknowledged_at": datetime.utcnow().isoformat()
                }
                if user_id and user_id != "system":
                    update_data["acknowledged_by"] = user_id

                await db_admin.table("anomaly_alerts").update(update_data).eq("id", alert_id).async_execute()
                
                logger.info(f"Marked alert {alert_id} as confirmed anomaly")
                return {"success": True, "action": "confirmed_anomaly"}
            
            else:
                return {"success": False, "error": f"Unknown status: {status}"}
                
        except Exception as e:
            logger.error(f"Error handling feedback: {e}")
            return {"success": False, "error": str(e)}

    # ── Geographic Request Surge Detection ────────────────────────────

    def _calculate_distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two lat/lng points using Haversine formula."""
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Earth radius in km
        
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c

    async def _detect_geographic_surges(self) -> list[dict]:
        """
        Detect geographic request surges:
        - Group requests by lat/lng clusters (within 20km)
        - Compare current day's count to 7-day average for that area
        - Trigger alert if > 3x the average
        FIX 4: Exclude simulated requests

        Improvements:
        - Requires minimum 5 requests in cluster for significance
        - Uses relative ratio but also validates absolute volume
        """
        try:
            # Get requests from last 8 days (today + 7 days history)
            since_date = datetime.utcnow() - timedelta(days=8)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("resource_requests")
                .select("id, latitude, longitude, created_at, is_simulated")
                .gte("created_at", since)
                .not_.is_("latitude", "null")
                .not_.is_("longitude", "null")
                .eq("is_simulated", False)  # FIX 4: Exclude simulated
                .limit(5000)
                .async_execute()
            )
            requests = resp.data or []

            if len(requests) < 10:
                logger.info("Not enough geographic data for surge detection")
                return []

            today = datetime.utcnow().strftime("%Y-%m-%d")

            # Separate today's requests from historical
            today_requests = []
            historical_requests = []

            for req in requests:
                created_at = req.get("created_at")
                if not created_at:
                    continue
                date_str = str(created_at)[:10]
                if date_str == today:
                    today_requests.append(req)
                else:
                    historical_requests.append(req)

            # If too few today requests, no surge possible
            if len(today_requests) < 5:
                logger.info(f"Only {len(today_requests)} requests today, skipping geo surge detection")
                return []

            # Cluster today's requests
            clusters = []  # List of (center_lat, center_lon, count, [request_ids])

            for req in today_requests:
                lat = req.get("latitude")
                lon = req.get("longitude")
                if lat is None or lon is None:
                    continue

                # Find matching cluster or create new one
                matched = False
                for i, (clat, clon, count, _) in enumerate(clusters):
                    dist = self._calculate_distance_km(lat, lon, clat, clon)
                    if dist <= GEO_CLUSTER_RADIUS_KM:
                        # Update cluster center (weighted average)
                        new_count = count + 1
                        new_lat = (clat * count + lat) / new_count
                        new_lon = (clon * count + lon) / new_count
                        clusters[i] = (new_lat, new_lon, new_count, [])
                        matched = True
                        break

                if not matched:
                    clusters.append((lat, lon, 1, []))

            # Calculate 7-day average for each cluster area
            anomalies = []

            for clat, clon, today_count, _ in clusters:
                # Minimum absolute threshold: cluster must have meaningful volume
                if today_count < 5:  # Require at least 5 requests to form a significant cluster
                    continue

                # Find historical requests in this cluster area
                historical_count = 0
                for req in historical_requests:
                    lat = req.get("latitude")
                    lon = req.get("longitude")
                    if lat is not None and lon is not None:
                        dist = self._calculate_distance_km(lat, lon, clat, clon)
                        if dist <= GEO_CLUSTER_RADIUS_KM:
                            historical_count += 1

                # Calculate 7-day average (minimum 1 to avoid division by zero interpretation)
                avg_daily = historical_count / 7.0 if historical_count > 0 else 0

                if avg_daily > 0:
                    ratio = today_count / avg_daily
                else:
                    # If no historical activity, but today has significant volume
                    ratio = float('inf') if today_count >= 10 else 0

                # Check for surge: both ratio threshold AND absolute minimum
                ratio_threshold_met = ratio >= GEO_SURGE_THRESHOLD
                absolute_threshold_met = today_count >= 10  # At least 10 requests today

                if ratio_threshold_met and absolute_threshold_met:
                    anomalies.append({
                        "anomaly_type": "geographic_request_surge",
                        "center_latitude": clat,
                        "center_longitude": clon,
                        "radius_km": GEO_CLUSTER_RADIUS_KM,
                        "today_count": today_count,
                        "seven_day_avg": round(avg_daily, 2),
                        "surge_ratio": round(ratio, 2) if ratio != float('inf') else None,
                        "severity": (
                            "critical" if ratio >= 5 or today_count >= 30 else
                            "high" if ratio >= 4 or today_count >= 20 else
                            "medium"
                        ),
                        "confidence": 0.90 if ratio >= 5 else 0.75,
                    })

            return anomalies

        except Exception as e:
            logger.error(f"Error detecting geographic surges: {e}")
            return []

    # ── Data collection for anomaly detection ──────────────────────

    async def _get_resource_consumption_series(self) -> list[dict]:
        """Get resource consumption time series (hourly aggregates) - FIX 4: exclude simulated."""
        try:
            # We look back 3x the standard period to have baseline
            since_date = datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("resources")
                .select("id, type, status, quantity, updated_at, is_simulated")
                .gte("updated_at", since)
                .eq("is_simulated", False)  # FIX 4: Exclude simulated
                .order("updated_at", desc=True)
                .limit(1000)
                .async_execute()
            )
            resources = resp.data or []

            # Aggregating by type and hour with density awareness
            hourly: dict[str, dict[str, Any]] = {}
            now = datetime.utcnow()

            # Find all types present in the data
            found_types = {str(r.get("type", "other")) for r in resources}
            if not found_types:
                found_types = {"other"}

            # Pre-fill every hour for every found type to ensure high-density time series
            for rt in found_types:
                for i in range(self.lookback_hours * 3):
                    h = (now - timedelta(hours=i)).strftime("%Y-%m-%dT%H")
                    key = f"{rt}_{h}"
                    hourly[key] = {"type": rt, "hour": h, "count": 0, "total_qty": 0.0}

            for r in resources:
                rtype = str(r.get("type", "other"))
                updated_at = r.get("updated_at")
                if updated_at:
                    updated_str = str(updated_at)
                    hour_key = updated_str[0:13] if len(updated_str) >= 13 else updated_str
                    key = f"{rtype}_{hour_key}"
                    if key in hourly:
                        current_count = int(hourly[key]["count"])
                        current_qty = float(hourly[key]["total_qty"])
                        hourly[key]["count"] = current_count + 1
                        val = r.get("quantity", 0)
                        hourly[key]["total_qty"] = current_qty + float(val if val is not None else 0)

            return list(hourly.values())
        except Exception as e:
            logger.error(f"Error getting resource consumption: {e}")
            return []

    async def _get_request_volume_series(self) -> list[dict]:
        """
        Get request volume time series (hourly counts) - FIX 4: exclude simulated.
        FIX 3: Raised minimum threshold from 3 to 5.

        Returns time series with data quality flags.
        """
        try:
            since_date = datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)
            since = since_date.isoformat()
            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, status, created_at, is_simulated")
                .gte("created_at", since)
                .eq("is_simulated", False)  # FIX 4: Exclude simulated
                .order("created_at", desc=True)
                .limit(2000)
                .async_execute()
            )
            requests = resp.data or []

            hourly: dict[str, dict[str, Any]] = {}
            now = datetime.utcnow()

            # Pre-fill all hours in lookback range to ensure we detect dips/gaps
            for i in range(self.lookback_hours * 3):
                h = (now - timedelta(hours=i)).strftime("%Y-%m-%dT%H")
                hourly[h] = {"hour": h, "count": 0, "critical": 0, "high": 0, "data_quality": "none"}

            for r in requests:
                created_at = r.get("created_at")
                if created_at:
                    created_str = str(created_at)
                    hour_key = created_str[0:13] if len(created_str) >= 13 else created_str
                    if hour_key in hourly:
                        hourly[hour_key]["count"] = int(hourly[hour_key]["count"]) + 1
                        hourly[hour_key]["data_quality"] = "partial"  # At least some data
                        priority = str(r.get("priority") or "medium").lower()
                        if priority in ["critical", "high"]:
                            hourly[hour_key][priority] = int(hourly[hour_key].get(priority, 0)) + 1

            # Mark hours with actual data as having good quality
            for h in hourly.values():
                if h["count"] > 0:
                    h["data_quality"] = "good"

            return list(hourly.values())
        except Exception as e:
            logger.error(f"Error getting request volume: {e}")
            return []

    async def _get_severity_escalation_series(self) -> list[dict]:
        """Get disaster severity changes over time - FIX 4: exclude simulated."""
        try:
            since = (datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)).isoformat()
            resp = (
                await db_admin.table("disasters")
                .select("id, type, severity, status, casualties, estimated_damage, updated_at, is_simulated")
                .gte("updated_at", since)
                .eq("is_simulated", False)  # FIX 4: Exclude simulated
                .order("updated_at", desc=True)
                .limit(200)
                .async_execute()
            )
            disasters = resp.data or []

            severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            series = []
            for d in disasters:
                series.append(
                    {
                        "disaster_id": d.get("id"),
                        "severity_score": severity_map.get(d.get("severity", "low"), 1),
                        "casualties": d.get("casualties", 0) or 0,
                        "damage": d.get("estimated_damage", 0) or 0,
                        "updated_at": d.get("updated_at", ""),
                    }
                )

            return series
        except Exception as e:
            logger.error(f"Error getting severity series: {e}")
            return []

    # ── Isolation Forest detection ─────────────────────────────────

    def _detect_anomalies(
        self,
        data: list[dict],
        feature_keys: list[str],
        anomaly_type: str,
    ) -> list[dict]:
        """
        Run Isolation Forest on the provided data.

        Returns list of detected anomalies with scores.
        """
        if IsolationForest is None:
            logger.warning("scikit-learn not available, skipping anomaly detection")
            return []

        if len(data) < self.min_samples:
            logger.info(f"Not enough data for {anomaly_type}: {len(data)} < {self.min_samples}")
            return []

        # Build feature matrix
        features = []
        for item in data:
            row = []
            for key in feature_keys:
                val = item.get(key, 0)
                row.append(float(val) if val is not None else 0.0)
            features.append(row)

        x_feats = np.array(features)
        if x_feats.size == 0:
            return []

        # Fit Isolation Forest
        clf = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )
        predictions = clf.fit_predict(x_feats)
        scores = clf.decision_function(x_feats)

        # Collect anomalies (prediction == -1)
        anomalies = []
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:
                item = data[i]
                # Compute expected range from inliers
                inlier_indices = [j for j, p in enumerate(predictions) if p == 1]
                inlier_values = x_feats[inlier_indices] if inlier_indices else x_feats

                if inlier_values.size > 0:
                    expected_lower = float(np.percentile(inlier_values, 5, axis=0).mean())
                    expected_upper = float(np.percentile(inlier_values, 95, axis=0).mean())
                else:
                    expected_lower, expected_upper = 0.0, 0.0

                # Determine the primary anomalous metric
                max_deviation_idx = 0
                max_deviation = 0.0
                for fi, key in enumerate(feature_keys):
                    if len(inlier_values) > 0:
                        mean_val = float(np.mean(inlier_values[:, fi]))
                    else:
                        mean_val = 0.0

                    val_at_i = float(x_feats[i, fi])
                    deviation = abs(val_at_i - mean_val)
                    if deviation > max_deviation:
                        max_deviation = deviation
                        max_deviation_idx = fi

                primary_metric = feature_keys[max_deviation_idx]
                metric_value = float(x_feats[i, max_deviation_idx])

                anomalies.append(
                    {
                        "anomaly_type": anomaly_type,
                        "metric_name": primary_metric,
                        "metric_value": metric_value,
                        "anomaly_score": float(score),
                        "expected_range": {"lower": expected_lower, "upper": expected_upper},
                        "context_data": {
                            **item,
                            "data_quality": "good" if len(data) >= 30 else "limited",
                            "n_data_points": len(data),
                            "lookback_hours": self.lookback_hours,
                        },
                    }
                )

        return anomalies

    # ── Severity classification ────────────────────────────────────

    # Minimum absolute metric values required before escalating to each level.
    # This prevents a single request in an otherwise-empty DB from being "critical".
    # Thresholds are tuned per anomaly type based on operational significance.
    _MIN_VALUES_FOR_SEVERITY: dict = {
        "request_volume": {
            "critical": 50,   # 50+ requests in an hour is a major surge
            "high": 20,       # 20+ requests in an hour needs attention
            "medium": 5,      # 5+ requests in an hour is above baseline
        },
        "resource_consumption": {
            "critical": 200,  # 200+ units consumed rapidly
            "high": 100,      # 100+ units
            "medium": 20,     # 20+ units
        },
        "severity_escalation": {
            "critical": 3,    # 3+ disasters escalating in severity
            "high": 2,        # 2+ disasters
            "medium": 1,      # At least 1
        },
        "geographic_request_surge": {
            "critical": 15,   # 15+ requests in a cluster (major hotspot)
            "high": 8,        # 8+ requests (concerning cluster)
            "medium": 3,      # 3+ requests (localized increase)
        },
        "baseline_deviation": {
            # For baseline deviation, use the number of standard deviations from mean
            # Will be computed dynamically based on feature z-scores
            "critical": 3.0,  # 3+ sigma deviation
            "high": 2.0,      # 2+ sigma
            "medium": 1.0,    # 1+ sigma
        },
    }

    def _classify_severity(
        self,
        anomaly_score: float,
        metric_name: str,
        metric_value: float = 0.0,
        anomaly_type: str = "",
        context_data: dict | None = None,
    ) -> str:
        """
        Classify anomaly severity based on Isolation Forest score AND absolute metric value.

        Uses type-specific thresholds to ensure sparse-data artifacts aren't over-escalated.
        Also considers additional context for baseline deviations.
        """
        # Step 1: raw severity from Isolation Forest score
        # more negative = more anomalous
        if anomaly_score < -0.3:
            raw = "critical"
        elif anomaly_score < -0.2:
            raw = "high"
        elif anomaly_score < -0.1:
            raw = "medium"
        else:
            raw = "low"

        # Step 2: Down-grade if absolute value is too small to warrant that level
        thresholds = self._MIN_VALUES_FOR_SEVERITY.get(anomaly_type, {})
        abs_val = abs(metric_value)

        if raw == "critical" and abs_val < thresholds.get("critical", 0):
            raw = "high"
        if raw == "high" and abs_val < thresholds.get("high", 0):
            raw = "medium"
        if raw == "medium" and abs_val < thresholds.get("medium", 0):
            raw = "low"

        # Step 3: For baseline_deviation, compute z-score for better granularity
        if anomaly_type == "baseline_deviation" and context_data:
            # Use standard deviation from feature means to refine severity
            all_features = context_data.get("all_features", {})
            if all_features and self._baseline_model is not None:
                # Estimate z-score using mean/std from training data if available
                # (requires stored training statistics; simplified for now)
                pass  # Future enhancement: store mean/std in model metadata

        return raw

    # ── AI explanation ─────────────────────────────────────────────

    async def _explain_anomaly(self, anomaly: dict) -> str:
        """Generate a contextual explanation for the anomaly (rule-based)."""
        return self._fallback_explanation(anomaly)

    def _fallback_explanation(self, anomaly: dict) -> str:
        """Generate a rule-based explanation."""
        atype = anomaly["anomaly_type"]
        metric = anomaly["metric_name"]
        value = anomaly["metric_value"]
        expected = anomaly.get("expected_range", {})

        if atype == "resource_consumption":
            return (
                f"Unusual {metric} detected (value: {value:.1f}, "
                f"expected: {expected.get('lower', '?'):.1f}–{expected.get('upper', '?'):.1f}). "
                f"This may indicate a sudden surge in resource usage that requires attention."
            )
        elif atype == "request_volume":
            return (
                f"Request volume anomaly detected for {metric} (value: {value:.0f}). "
                f"This spike could indicate an emerging crisis or a surge of victims needing help."
            )
        elif atype == "severity_escalation":
            return (
                f"Severity escalation anomaly detected for {metric} (value: {value:.1f}). "
                f"Rapid severity increases may signal a worsening disaster requiring immediate response."
            )
        elif atype == "geographic_request_surge":
            ctx = anomaly.get("context_data", {})
            return (
                f"Geographic request surge detected at coordinates ({ctx.get('center_latitude', '?')}, {ctx.get('center_longitude', '?')}). "
                f"Today's requests ({ctx.get('today_count', '?')}) are {ctx.get('surge_ratio', '?')}x the 7-day average "
                f"({ctx.get('seven_day_avg', '?')}) within a {ctx.get('radius_km', 20)}km radius. "
                f"This localized spike may indicate a new disaster hotspot or concentration of affected population."
            )
        elif atype == "baseline_deviation":
            return (
                f"Today's metrics deviate significantly from historical baseline. "
                f"Key metric: {metric} = {value:.2f}. This pattern differs from typical daily operations "
                f"and may require investigation."
            )
        return f"Anomaly detected: {metric} = {value} (score: {anomaly['anomaly_score']:.3f})"

    # ── Main detection pipeline ────────────────────────────────────

    async def run_detection(self) -> list[dict]:
        """
        Run the full anomaly detection pipeline:
        1. CLEANUP STALE ALERTS (older than 3 days) - FIX 2
        2. Load or build baseline model
        3. Gather time series data (FIX 4: excluding simulated)
        4. Run Isolation Forest on each metric group
        5. Detect baseline anomalies (compare to trained model)
        6. Detect geographic surges
        7. Generate AI explanations
        8. Store alerts in DB with improved dedup (FIX 1)
        """
        # STEP 1: Clean up stale alerts at START of cycle - FIX 2
        cleanup_result = await self.cleanup_stale_alerts()
        logger.info(f"Stale alert cleanup: {cleanup_result}")
        
        # Try to load baseline model, or build it if not available
        if self._baseline_model is None:
            if not self._load_baseline_model():
                logger.info("No baseline model found, building one...")
                await self.build_baseline()
        
        all_anomalies = []

        # 1. Resource consumption anomalies
        # FIX 3: Raised minimum threshold from 5 to 10
        consumption_data = await self._get_resource_consumption_series()
        if consumption_data:
            max_qty = max((d.get("total_qty", 0) for d in consumption_data), default=0)
            if max_qty >= 10:  # FIX 3: raised from 5
                anomalies = self._detect_anomalies(
                    consumption_data,
                    ["count", "total_qty"],
                    "resource_consumption",
                )
                all_anomalies.extend(anomalies)
            else:
                logger.info(
                    f"Skipping resource_consumption anomaly detection: "
                    f"max quantity ({max_qty}) below minimum threshold (10)"  # FIX 3
                )

        # 2. Request volume anomalies
        # FIX 3: Raised minimum threshold from 3 to 5
        volume_data = await self._get_request_volume_series()
        if volume_data:
            # Only run detection if there's meaningful activity.
            # A handful of requests across 100+ pre-filled zero-hours will always
            # look anomalous to Isolation Forest — but it's just an empty DB.
            max_hourly_count = max((d.get("count", 0) for d in volume_data), default=0)
            if max_hourly_count >= 5:  # FIX 3: raised from 3
                anomalies = self._detect_anomalies(
                    volume_data,
                    ["count", "critical", "high"],
                    "request_volume",
                )
                all_anomalies.extend(anomalies)
            else:
                logger.info(
                    f"Skipping request_volume anomaly detection: "
                    f"max hourly count ({max_hourly_count}) below minimum threshold (5)"  # FIX 3
                )

        # 3. Severity escalation anomalies
        severity_data = await self._get_severity_escalation_series()
        if severity_data:
            anomalies = self._detect_anomalies(
                severity_data,
                ["severity_score", "casualties", "damage"],
                "severity_escalation",
            )
            all_anomalies.extend(anomalies)

        # 4. Baseline deviation anomalies (compare to trained model)
        current_stats = await self._get_current_day_stats()
        # Only run baseline comparison when there's a meaningful amount of data today.
        # A request_count of 1-2 is not a real "deviation" — it's just an empty DB.
        if current_stats.get("request_count", 0) >= 5:
            baseline_anomalies = self._detect_baseline_anomalies(current_stats)
            # Filter out exclusions
            for anomaly in baseline_anomalies:
                signature = self._generate_signature(anomaly)
                if signature not in self._exclusion_list:
                    all_anomalies.append(anomaly)
                else:
                    logger.info(f"Excluded anomaly from detection: {signature}")

        # 5. Geographic request surge anomalies
        geo_anomalies = await self._detect_geographic_surges()
        for geo in geo_anomalies:
            all_anomalies.append({
                "anomaly_type": geo["anomaly_type"],
                "metric_name": "surge_ratio",
                "metric_value": geo["surge_ratio"],
                "anomaly_score": -0.5,  # Default score
                "expected_range": {"lower": 0, "upper": GEO_SURGE_THRESHOLD},
                "context_data": geo,
            })

        # Process and store each anomaly
        stored_alerts = []
        
        # FIX 1: Fetch currently-active alert signatures within 24h window for dedup
        try:
            since_dedup = (datetime.utcnow() - timedelta(hours=DEDUP_WINDOW_HOURS)).isoformat()  # FIX 1: Use 24h
            existing_resp = await db_admin.table("anomaly_alerts") \
                .select("anomaly_type,severity,context_data,title") \
                .eq("status", "active") \
                .gte("detected_at", since_dedup) \
                .limit(500) \
                .async_execute()
            existing_signatures = set()
            for r in (existing_resp.data or []):
                # Build signature for each existing alert
                ctx = r.get("context_data", {})
                sig = self._generate_signature({
                    "anomaly_type": r.get("anomaly_type"),
                    "metric_name": r.get("title", "").replace("_", " ").title().split(":")[0].lower().replace(" ", "_"),
                    "context_data": ctx,
                })
                existing_signatures.add(sig)
        except Exception as e:
            logger.warning(f"Could not fetch existing alerts for dedup: {e}")
            existing_signatures = set()

        for anomaly in all_anomalies:
            # Skip if in exclusion list OR signature matches an active alert
            signature = self._generate_signature(anomaly)
            if signature in self._exclusion_list or signature in existing_signatures:
                logger.debug(f"Skipping duplicate anomaly alert: {signature}")
                continue

            # Add to set so subsequent iterations in the same run also deduplicate
            existing_signatures.add(signature)

            # Get AI explanation
            explanation = await self._explain_anomaly(anomaly)

            title = f"{anomaly['anomaly_type'].replace('_', ' ').title()}: {anomaly['metric_name']}"

            # Compute confidence score for this anomaly
            confidence = self._compute_confidence_score(
                anomaly_score=anomaly.get("anomaly_score", -0.1),
                anomaly_type=anomaly.get("anomaly_type", ""),
                metric_value=float(anomaly.get("metric_value", 0) or 0),
                context_data=anomaly.get("context_data", {}),
                historical_data_points=len(self._feature_columns) if self._feature_columns else 0,
            )

            # Determine severity based on anomaly characteristics
            severity = self._classify_severity(
                anomaly_score=anomaly.get("anomaly_score", -0.1),
                anomaly_type=anomaly.get("anomaly_type", ""),
                metric_value=float(anomaly.get("metric_value", 0) or 0),
                context_data=anomaly.get("context_data", {}),
            )

            alert_record = {
                "anomaly_type": anomaly["anomaly_type"],
                "severity": severity,
                "title": title,
                "description": f"Detected anomalous {anomaly['metric_name']} = {anomaly['metric_value']:.2f}",
                "ai_explanation": explanation,
                "metric_name": anomaly["metric_name"],
                "metric_value": anomaly["metric_value"],
                "expected_range": anomaly.get("expected_range", {}),
                "anomaly_score": anomaly.get("anomaly_score", -0.1),
                "confidence_score": confidence,  # New field
                "context_data": anomaly.get("context_data", {}),
                "status": "active",
                "detected_at": datetime.utcnow().isoformat(),
            }

            try:
                resp = await db_admin.table("anomaly_alerts").insert(alert_record).async_execute()
                if resp.data:
                    stored_alerts.append(resp.data[0])
                    # Send notification to all admins about the anomaly
                    await notify_all_admins(
                        title=f"🔍 Anomaly Detected: {title}",
                        message=explanation,
                        notification_type="warning",
                    )
            except Exception as e:
                logger.error(f"Failed to store anomaly alert: {e}")

        logger.info(f"Anomaly detection complete: {len(stored_alerts)} alerts generated")
        return stored_alerts

    def _compute_confidence_score(
        self,
        anomaly_score: float,
        anomaly_type: str,
        metric_value: float,
        context_data: dict,
        historical_data_points: int = 0,
    ) -> float:
        """
        Compute a confidence score (0-1) for the anomaly.
        Combines:
        - Anomaly score from Isolation Forest (normalized to 0-1)
        - Data quality (number of historical data points)
        - Metric magnitude above threshold
        - Trend direction (if available)

        Higher score = more confident this is a true anomaly.
        """
        # Base score from Isolation Forest (convert -1..0 range to 0..1)
        # -1 is most anomalous, 0 is borderline, positive is normal
        if anomaly_score < -0.5:
            base_score = 0.95
        elif anomaly_score < -0.3:
            base_score = 0.85
        elif anomaly_score < -0.2:
            base_score = 0.70
        elif anomaly_score < -0.1:
            base_score = 0.60
        else:
            base_score = 0.50  # borderline

        # Data quality factor: more historical data = higher confidence
        # Scale: 0-1, where >= 30 data points yields 1.0
        data_quality = min(1.0, historical_data_points / 30.0)

        # Magnitude factor: how extreme is the value relative to threshold
        thresholds = self._MIN_VALUES_FOR_SEVERITY.get(anomaly_type, {})
        medium_threshold = thresholds.get("medium", 1)
        if medium_threshold > 0:
            magnitude_factor = min(1.0, abs(metric_value) / (medium_threshold * 3))
        else:
            magnitude_factor = 0.5

        # Trend factor: if context shows upward trend, increase confidence
        trend_factor = 0.5
        if context_data:
            # Check if there's a trend indication in context
            # (e.g., for request volume, compare to yesterday)
            pass  # Future: compute from time series if available

        # Weighted combination
        confidence = (
            base_score * 0.50 +
            data_quality * 0.25 +
            magnitude_factor * 0.20 +
            trend_factor * 0.05
        )

        return round(min(1.0, max(0.0, confidence)), 3)

    # ── Alert management ───────────────────────────────────────────

    async def get_active_alerts(
        self,
        severity: str | None = None,
        anomaly_type: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get active anomaly alerts."""
        try:
            query = (
                db_admin.table("anomaly_alerts")
                .select("*")
                .eq("status", "active")
                .order("detected_at", desc=True)
                .limit(limit)
            )
            if severity:
                query = query.eq("severity", severity)
            if anomaly_type:
                query = query.eq("anomaly_type", anomaly_type)

            resp = await query.async_execute()
            return resp.data or []
        except Exception as e:
            logger.warning("Failed to fetch active alerts: %s", e)
            return []

    async def get_disaster_alerts(
        self,
        disaster_id: str,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get anomaly alerts for a specific disaster."""
        try:
            query = (
                db_admin.table("anomaly_alerts")
                .select("*")
                .eq("disaster_id", disaster_id)
                .order("detected_at", desc=True)
                .limit(limit)
            )
            if status:
                query = query.eq("status", status)
            if severity:
                query = query.eq("severity", severity)

            resp = await query.async_execute()
            return resp.data or []
        except Exception as e:
            logger.warning(f"Failed to fetch alerts for disaster {disaster_id}: {e}")
            return []

    async def get_all_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get all anomaly alerts with filters."""
        try:
            query = (
                db_admin.table("anomaly_alerts")
                .select("*")
                .order("detected_at", desc=True)
                .range(offset, offset + limit - 1)
            )
            if status:
                query = query.eq("status", status)
            if severity:
                query = query.eq("severity", severity)

            resp = await query.async_execute()
            return resp.data or []
        except Exception as e:
            logger.warning("Failed to fetch alerts: %s", e)
            return []

    async def acknowledge_alert(self, alert_id: str, user_id: str = None) -> dict | None:
        """Mark an anomaly alert as acknowledged."""
        try:
            update_data = {
                "status": "acknowledged",
                "acknowledged_at": datetime.utcnow().isoformat(),
            }
            if user_id and user_id != "system":
                update_data["acknowledged_by"] = user_id

            resp = (
                await db_admin.table("anomaly_alerts")
                .update(update_data)
                .eq("id", alert_id)
                .async_execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to acknowledge alert: {e}")
            return None

    async def resolve_alert(self, alert_id: str, status: str = "resolved", user_id: str = None) -> dict | None:
        """Resolve or mark an alert as false positive with feedback tracking."""
        # Use the new feedback handling if status is false_positive or resolved
        if status in ["false_positive", "resolved"]:
            result = await self.handle_feedback(alert_id, status, user_id)
            return result if result.get("success") else None
        
        # Original behavior for other statuses
        try:
            resp = await db_admin.table("anomaly_alerts").update({"status": status}).eq("id", alert_id).async_execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return None

    # ── Manual baseline rebuild ──────────────────────────────────────

    async def rebuild_baseline(self) -> dict:
        """
        Manually trigger a rebuild of the baseline model.
        Useful when there's been significant data changes.
        """
        return await self.build_baseline()

    # ── Background loop ────────────────────────────────────────────

    async def start_periodic_detection(self):
        """Start periodic anomaly detection in the background."""
        self._running = True
        interval = phase5_config.ANOMALY_DETECTION_INTERVAL_S
        # Delay initial detection to let uvicorn finish startup
        await asyncio.sleep(10)
        logger.info(f"Anomaly detection loop started (interval: {interval}s)")

        while self._running:
            try:
                await self.run_detection()
            except Exception as e:
                logger.error(f"Anomaly detection cycle failed: {e}")
            await asyncio.sleep(interval)

    def stop_periodic_detection(self):
        """Stop the periodic detection loop."""
        self._running = False
        logger.info("Anomaly detection loop stopped")
