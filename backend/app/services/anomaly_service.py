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

    # ── Baseline Builder Methods ───────────────────────────────────────

    async def _get_resource_requests_daily_stats(self) -> list[dict]:
        """
        Query resource_requests grouped by day:
        - count of requests per day
        - avg priority
        - breakdown by resource_type
        """
        try:
            # Get data from last 90 days
            since_date = datetime.utcnow() - timedelta(days=ROLLING_STATS_DAYS)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, created_at")
                .gte("created_at", since)
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
        """
        try:
            since_date = datetime.utcnow() - timedelta(days=ROLLING_STATS_DAYS)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("resource_consumption_log")
                .select("id, resource_type, timestamp, quantity_consumed")
                .gte("timestamp", since)
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
        """
        try:
            since_date = datetime.utcnow() - timedelta(days=ROLLING_STATS_DAYS)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("disasters")
                .select("id, severity, status, created_at")
                .gte("created_at", since)
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
        1. Query all historical data
        2. Create feature matrix
        3. Fit Isolation Forest
        4. Save to .pkl
        """
        if IsolationForest is None:
            logger.warning("scikit-learn not available, cannot build baseline")
            return {"success": False, "error": "scikit-learn not available"}

        logger.info("Building anomaly detection baseline...")

        # Gather all data
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

        # Fit Isolation Forest
        self._baseline_model = IsolationForest(
            contamination=self.contamination,
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

    # ── Detection against Baseline ────────────────────────────────────

    async def _get_current_day_stats(self) -> dict:
        """Get current day's stats for comparison with baseline."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Get today's request count
        try:
            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, created_at")
                .gte("created_at", f"{today}T00:00:00")
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
                .select("id, resource_type, quantity_consumed, timestamp")
                .gte("timestamp", f"{today}T00:00:00")
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
                .select("id, severity, created_at")
                .gte("created_at", f"{today}T00:00:00")
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
        """
        if self._baseline_model is None or not self._feature_columns:
            return []
        
        # Build feature vector
        feature_vector = []
        for col in self._feature_columns:
            if col == "request_count":
                feature_vector.append(float(current_stats.get("request_count", 0)))
            elif col == "avg_priority":
                feature_vector.append(float(current_stats.get("avg_priority", 0)))
            elif col.startswith("type_"):
                rtype = col[5:]  # Remove 'type_' prefix
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
        
        x = np.array([feature_vector])
        prediction = self._baseline_model.predict(x)[0]
        score = self._baseline_model.decision_function(x)[0]
        
        if prediction == -1:
            # Anomaly detected
            # Determine which features contributed most
            deviations = []
            for i, col in enumerate(self._feature_columns):
                # Get mean and std from training data
                # For simplicity, we'll just report the raw values
                deviations.append((col, abs(feature_vector[i])))
            
            # Sort by deviation
            deviations.sort(key=lambda x: x[1], reverse=True)
            
            return [{
                "anomaly_type": "baseline_deviation",
                "anomaly_score": float(score),
                "metric_name": deviations[0][0] if deviations else "unknown",
                "metric_value": feature_vector[0] if feature_vector else 0,
                "context_data": current_stats,
                "all_features": dict(zip(self._feature_columns, feature_vector))
            }]
        
        return []

    # ── Feedback Handling ─────────────────────────────────────────────

    def _generate_signature(self, anomaly: dict) -> str:
        """Generate a unique signature for an anomaly to track it in exclusion list."""
        # Create a hash-like signature based on key features
        ctx = anomaly.get("context_data", {})
        if isinstance(ctx, dict):
            date = ctx.get("date", "")
            anomaly_type = anomaly.get("anomaly_type", "")
            metric = anomaly.get("metric_name", "")
            return f"{date}_{anomaly_type}_{metric}"
        return ""

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
                .single()
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
                await db_admin.table("anomaly_alerts").update({
                    "status": "false_positive",
                    "resolved_by": user_id,
                    "resolved_at": datetime.utcnow().isoformat()
                }).eq("id", alert_id).async_execute()
                
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
                await db_admin.table("anomaly_alerts").update({
                    "status": "resolved",
                    "resolved_by": user_id,
                    "resolved_at": datetime.utcnow().isoformat()
                }).eq("id", alert_id).async_execute()
                
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
        """
        try:
            # Get requests from last 8 days (today + 7 days history)
            since_date = datetime.utcnow() - timedelta(days=8)
            since = since_date.isoformat()
            
            resp = (
                await db_admin.table("resource_requests")
                .select("id, latitude, longitude, created_at")
                .gte("created_at", since)
                .not_.is_("latitude", "null")
                .not_.is_("longitude", "null")
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
            
            # Cluster today's requests
            clusters = []  # List of (center_lat, center_lon, count, [requests])
            
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
                if today_count < 3:  # Minimum threshold
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
                
                # Calculate 7-day average
                avg_daily = historical_count / 7.0
                
                if avg_daily > 0:
                    ratio = today_count / avg_daily
                else:
                    ratio = float('inf') if today_count > 0 else 0
                
                # Check for surge
                if ratio >= GEO_SURGE_THRESHOLD:
                    anomalies.append({
                        "anomaly_type": "geographic_request_surge",
                        "center_latitude": clat,
                        "center_longitude": clon,
                        "radius_km": GEO_CLUSTER_RADIUS_KM,
                        "today_count": today_count,
                        "seven_day_avg": round(avg_daily, 2),
                        "surge_ratio": round(ratio, 2),
                        "severity": "critical" if ratio >= 5 else "high" if ratio >= 4 else "medium"
                    })
            
            return anomalies
            
        except Exception as e:
            logger.error(f"Error detecting geographic surges: {e}")
            return []

    # ── Data collection for anomaly detection ──────────────────────

    async def _get_resource_consumption_series(self) -> list[dict]:
        """Get resource consumption time series (hourly aggregates)."""
        try:
            # We look back 3x the standard period to have baseline
            since_date = datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)
            since = since_date.isoformat()

            resp = (
                await db_admin.table("resources")
                .select("id, type, status, quantity, updated_at")
                .gte("updated_at", since)
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
        """Get request volume time series (hourly counts)."""
        try:
            since_date = datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)
            since = since_date.isoformat()
            resp = (
                await db_admin.table("resource_requests")
                .select("id, resource_type, priority, status, created_at")
                .gte("created_at", since)
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
                hourly[h] = {"hour": h, "count": 0, "critical": 0, "high": 0}

            for r in requests:
                created_at = r.get("created_at")
                if created_at:
                    created_str = str(created_at)
                    hour_key = created_str[0:13] if len(created_str) >= 13 else created_str
                    if hour_key in hourly:
                        hourly[hour_key]["count"] = int(hourly[hour_key]["count"]) + 1
                        priority = str(r.get("priority") or "medium").lower()
                        if priority in ["critical", "high"]:
                            hourly[hour_key][priority] = int(hourly[hour_key].get(priority, 0)) + 1

            return list(hourly.values())
        except Exception as e:
            logger.error(f"Error getting request volume: {e}")
            return []

    async def _get_severity_escalation_series(self) -> list[dict]:
        """Get disaster severity changes over time."""
        try:
            since = (datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)).isoformat()
            resp = (
                await db_admin.table("disasters")
                .select("id, type, severity, status, casualties, estimated_damage, updated_at")
                .gte("updated_at", since)
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
                        "context_data": item,
                    }
                )

        return anomalies

    # ── Severity classification ────────────────────────────────────

    def _classify_severity(self, anomaly_score: float, metric_name: str) -> str:
        """Classify anomaly severity based on score and metric type."""
        # Isolation Forest scores: more negative = more anomalous
        if anomaly_score < -0.3:
            return "critical"
        elif anomaly_score < -0.2:
            return "high"
        elif anomaly_score < -0.1:
            return "medium"
        return "low"

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
        1. Load or build baseline model
        2. Gather time series data
        3. Run Isolation Forest on each metric group
        4. Detect baseline anomalies (compare to trained model)
        5. Detect geographic surges
        6. Generate AI explanations
        7. Store alerts in DB
        """
        # Try to load baseline model, or build it if not available
        if self._baseline_model is None:
            if not self._load_baseline_model():
                logger.info("No baseline model found, building one...")
                await self.build_baseline()
        
        all_anomalies = []

        # 1. Resource consumption anomalies
        consumption_data = await self._get_resource_consumption_series()
        if consumption_data:
            anomalies = self._detect_anomalies(
                consumption_data,
                ["count", "total_qty"],
                "resource_consumption",
            )
            all_anomalies.extend(anomalies)

        # 2. Request volume anomalies
        volume_data = await self._get_request_volume_series()
        if volume_data:
            anomalies = self._detect_anomalies(
                volume_data,
                ["count", "critical", "high"],
                "request_volume",
            )
            all_anomalies.extend(anomalies)

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
        if current_stats.get("request_count", 0) > 0:
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
        for anomaly in all_anomalies:
            # Skip if in exclusion list
            signature = self._generate_signature(anomaly)
            if signature in self._exclusion_list:
                continue
            
            severity = self._classify_severity(
                anomaly.get("anomaly_score", -0.1),
                anomaly.get("metric_name", "unknown"),
            )
            
            # Override severity for geographic surges
            if anomaly.get("anomaly_type") == "geographic_request_surge":
                severity = anomaly.get("context_data", {}).get("severity", "high")

            # Get AI explanation
            explanation = await self._explain_anomaly(anomaly)

            title = f"{anomaly['anomaly_type'].replace('_', ' ').title()}: {anomaly['metric_name']}"

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
                "context_data": anomaly.get("context_data", {}),
                "status": "active",
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

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> dict | None:
        """Mark an anomaly alert as acknowledged."""
        try:
            resp = (
                await db_admin.table("anomaly_alerts")
                .update(
                    {
                        "status": "acknowledged",
                        "acknowledged_by": user_id,
                        "acknowledged_at": datetime.utcnow().isoformat(),
                    }
                )
                .eq("id", alert_id)
                .async_execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to acknowledge alert: {e}")
            return None

    async def resolve_alert(self, alert_id: str, status: str = "resolved", user_id: str = "system") -> dict | None:
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
