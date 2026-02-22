"""
Phase 5 – Anomaly Detection Service.

Uses Isolation Forest (sklearn) to detect anomalies in:
- Resource consumption rates
- Request volume spikes
- Severity escalation patterns

Anomalies are stored with rule-based explanations (no external API needed).
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

import numpy as np

try:
    from sklearn.ensemble import IsolationForest
except ImportError:
    IsolationForest = None

from app.database import supabase_admin
from app.core.phase5_config import phase5_config

logger = logging.getLogger("anomaly_service")


class AnomalyDetectionService:
    """Detects anomalies in disaster management metrics using Isolation Forest."""

    def __init__(self):
        self.contamination = phase5_config.ANOMALY_CONTAMINATION
        self.min_samples = phase5_config.ANOMALY_MIN_SAMPLES
        self.lookback_hours = phase5_config.ANOMALY_LOOKBACK_HOURS
        self._running = False

    # ── Data collection for anomaly detection ──────────────────────

    async def _get_resource_consumption_series(self) -> List[Dict]:
        """Get resource consumption time series (hourly aggregates)."""
        try:
            since = (datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)).isoformat()
            resp = (
                supabase_admin.table("resources")
                .select("id, type, status, quantity, updated_at")
                .gte("updated_at", since)
                .order("updated_at", desc=True)
                .limit(500)
                .execute()
            )
            resources = resp.data or []

            # Aggregate by type and hour
            hourly = {}
            for r in resources:
                rtype = r.get("type", "other")
                updated = r.get("updated_at", "")
                if updated:
                    hour_key = updated[:13]  # YYYY-MM-DDTHH
                    key = f"{rtype}_{hour_key}"
                    if key not in hourly:
                        hourly[key] = {"type": rtype, "hour": hour_key, "count": 0, "total_qty": 0}
                    hourly[key]["count"] += 1
                    hourly[key]["total_qty"] += r.get("quantity", 0)

            return list(hourly.values())
        except Exception as e:
            logger.error(f"Error getting resource consumption: {e}")
            return []

    async def _get_request_volume_series(self) -> List[Dict]:
        """Get request volume time series (hourly counts)."""
        try:
            since = (datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)).isoformat()
            resp = (
                supabase_admin.table("resource_requests")
                .select("id, resource_type, priority, status, created_at")
                .gte("created_at", since)
                .order("created_at", desc=True)
                .limit(1000)
                .execute()
            )
            requests = resp.data or []

            hourly = {}
            for r in requests:
                created = r.get("created_at", "")
                if created:
                    hour_key = created[:13]
                    if hour_key not in hourly:
                        hourly[hour_key] = {"hour": hour_key, "count": 0, "critical": 0, "high": 0}
                    hourly[hour_key]["count"] += 1
                    priority = r.get("priority", "medium")
                    if priority in hourly[hour_key]:
                        hourly[hour_key][priority] += 1

            return list(hourly.values())
        except Exception as e:
            logger.error(f"Error getting request volume: {e}")
            return []

    async def _get_severity_escalation_series(self) -> List[Dict]:
        """Get disaster severity changes over time."""
        try:
            since = (datetime.utcnow() - timedelta(hours=self.lookback_hours * 3)).isoformat()
            resp = (
                supabase_admin.table("disasters")
                .select("id, type, severity, status, casualties, estimated_damage, updated_at")
                .gte("updated_at", since)
                .order("updated_at", desc=True)
                .limit(200)
                .execute()
            )
            disasters = resp.data or []

            severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            series = []
            for d in disasters:
                series.append({
                    "disaster_id": d.get("id"),
                    "severity_score": severity_map.get(d.get("severity", "low"), 1),
                    "casualties": d.get("casualties", 0) or 0,
                    "damage": d.get("estimated_damage", 0) or 0,
                    "updated_at": d.get("updated_at", ""),
                })

            return series
        except Exception as e:
            logger.error(f"Error getting severity series: {e}")
            return []

    # ── Isolation Forest detection ─────────────────────────────────

    def _detect_anomalies(
        self,
        data: List[Dict],
        feature_keys: List[str],
        anomaly_type: str,
    ) -> List[Dict]:
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

        X = np.array(features)

        # Fit Isolation Forest
        clf = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
        )
        predictions = clf.fit_predict(X)
        scores = clf.decision_function(X)

        # Collect anomalies (prediction == -1)
        anomalies = []
        for i, (pred, score) in enumerate(zip(predictions, scores)):
            if pred == -1:
                item = data[i]
                # Compute expected range from inliers
                inlier_indices = [j for j, p in enumerate(predictions) if p == 1]
                inlier_values = X[inlier_indices] if inlier_indices else X

                expected_lower = float(np.percentile(inlier_values, 5, axis=0).mean())
                expected_upper = float(np.percentile(inlier_values, 95, axis=0).mean())

                # Determine the primary anomalous metric
                max_deviation_idx = 0
                max_deviation = 0
                for fi, key in enumerate(feature_keys):
                    mean_val = float(np.mean(inlier_values[:, fi])) if len(inlier_values) > 0 else 0
                    deviation = abs(float(X[i, fi]) - mean_val)
                    if deviation > max_deviation:
                        max_deviation = deviation
                        max_deviation_idx = fi

                primary_metric = feature_keys[max_deviation_idx]
                metric_value = float(X[i, max_deviation_idx])

                anomalies.append({
                    "anomaly_type": anomaly_type,
                    "metric_name": primary_metric,
                    "metric_value": metric_value,
                    "anomaly_score": float(score),
                    "expected_range": {"lower": expected_lower, "upper": expected_upper},
                    "context_data": item,
                })

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

    async def _explain_anomaly(self, anomaly: Dict) -> str:
        """Generate a contextual explanation for the anomaly (rule-based)."""
        return self._fallback_explanation(anomaly)

    def _fallback_explanation(self, anomaly: Dict) -> str:
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
        return f"Anomaly detected: {metric} = {value} (score: {anomaly['anomaly_score']:.3f})"

    # ── Main detection pipeline ────────────────────────────────────

    async def run_detection(self) -> List[Dict]:
        """
        Run the full anomaly detection pipeline:
        1. Gather time series data
        2. Run Isolation Forest on each metric group
        3. Generate AI explanations
        4. Store alerts in DB
        """
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

        # Process and store each anomaly
        stored_alerts = []
        for anomaly in all_anomalies:
            severity = self._classify_severity(
                anomaly["anomaly_score"],
                anomaly["metric_name"],
            )

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
                "expected_range": anomaly["expected_range"],
                "anomaly_score": anomaly["anomaly_score"],
                "context_data": anomaly.get("context_data", {}),
                "status": "active",
            }

            try:
                resp = supabase_admin.table("anomaly_alerts").insert(alert_record).execute()
                if resp.data:
                    stored_alerts.append(resp.data[0])
            except Exception as e:
                logger.error(f"Failed to store anomaly alert: {e}")

        logger.info(f"Anomaly detection complete: {len(stored_alerts)} alerts generated")
        return stored_alerts

    # ── Alert management ───────────────────────────────────────────

    async def get_active_alerts(
        self,
        severity: Optional[str] = None,
        anomaly_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get active anomaly alerts."""
        query = (
            supabase_admin.table("anomaly_alerts")
            .select("*")
            .eq("status", "active")
            .order("detected_at", desc=True)
            .limit(limit)
        )
        if severity:
            query = query.eq("severity", severity)
        if anomaly_type:
            query = query.eq("anomaly_type", anomaly_type)

        resp = query.execute()
        return resp.data or []

    async def get_all_alerts(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Get all anomaly alerts with filters."""
        query = (
            supabase_admin.table("anomaly_alerts")
            .select("*")
            .order("detected_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if status:
            query = query.eq("status", status)
        if severity:
            query = query.eq("severity", severity)

        resp = query.execute()
        return resp.data or []

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> Optional[Dict]:
        """Mark an anomaly alert as acknowledged."""
        try:
            resp = (
                supabase_admin.table("anomaly_alerts")
                .update({
                    "status": "acknowledged",
                    "acknowledged_by": user_id,
                    "acknowledged_at": datetime.utcnow().isoformat(),
                })
                .eq("id", alert_id)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to acknowledge alert: {e}")
            return None

    async def resolve_alert(self, alert_id: str, status: str = "resolved") -> Optional[Dict]:
        """Resolve or mark an alert as false positive."""
        try:
            resp = (
                supabase_admin.table("anomaly_alerts")
                .update({"status": status})
                .eq("id", alert_id)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return None

    # ── Background loop ────────────────────────────────────────────

    async def start_periodic_detection(self):
        """Start periodic anomaly detection in the background."""
        self._running = True
        interval = phase5_config.ANOMALY_DETECTION_INTERVAL_S
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
