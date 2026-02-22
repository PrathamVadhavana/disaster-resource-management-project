"""
Phase 5 – Outcome Tracking & Model Feedback Loop Service.

Logs actual vs predicted outcomes, computes error metrics,
generates weekly evaluation reports, and triggers retraining when needed.
"""

import math
import logging
import asyncio
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

from app.database import supabase_admin
from app.core.phase5_config import phase5_config

logger = logging.getLogger("outcome_service")


class OutcomeTrackingService:
    """Tracks prediction accuracy and manages the model feedback loop."""

    def __init__(self):
        self.auto_retrain_mae = phase5_config.AUTO_RETRAIN_THRESHOLD_MAE
        self.auto_retrain_accuracy = phase5_config.AUTO_RETRAIN_THRESHOLD_ACCURACY

    # ── Outcome logging ────────────────────────────────────────────

    async def log_outcome(self, outcome_data: Dict) -> Optional[Dict]:
        """
        Log an actual outcome and compute error metrics vs prediction.

        outcome_data should include:
        - disaster_id (required)
        - prediction_id (optional — links to the prediction)
        - prediction_type (required)
        - actual_severity, actual_casualties, actual_damage_usd, actual_area_km2
        """
        disaster_id = outcome_data.get("disaster_id")
        prediction_id = outcome_data.get("prediction_id")
        prediction_type = outcome_data.get("prediction_type")

        if not disaster_id or not prediction_type:
            raise ValueError("disaster_id and prediction_type are required")

        # Fetch prediction data if prediction_id is provided
        predicted = {}
        model_version = None
        if prediction_id:
            try:
                resp = (
                    supabase_admin.table("predictions")
                    .select("*")
                    .eq("id", prediction_id)
                    .single()
                    .execute()
                )
                pred = resp.data
                if pred:
                    predicted = {
                        "predicted_severity": pred.get("predicted_severity"),
                        "predicted_casualties": pred.get("predicted_casualties"),
                        "predicted_damage_usd": pred.get("features", {}).get("predicted_damage_usd")
                            or pred.get("metadata", {}).get("predicted_damage_usd"),
                        "predicted_area_km2": pred.get("features", {}).get("predicted_area_km2")
                            or pred.get("affected_area_km"),
                    }
                    model_version = pred.get("model_version")
            except Exception as e:
                logger.error(f"Error fetching prediction {prediction_id}: {e}")

        # Compute error metrics
        record = {
            "disaster_id": disaster_id,
            "prediction_id": prediction_id,
            "prediction_type": prediction_type,
            "model_version": model_version,
            "logged_by": outcome_data.get("logged_by", "system"),
            "notes": outcome_data.get("notes"),

            # Predicted values
            "predicted_severity": predicted.get("predicted_severity"),
            "predicted_casualties": predicted.get("predicted_casualties"),
            "predicted_damage_usd": predicted.get("predicted_damage_usd"),
            "predicted_area_km2": predicted.get("predicted_area_km2"),

            # Actual values
            "actual_severity": outcome_data.get("actual_severity"),
            "actual_casualties": outcome_data.get("actual_casualties"),
            "actual_damage_usd": outcome_data.get("actual_damage_usd"),
            "actual_area_km2": outcome_data.get("actual_area_km2"),
        }

        # Severity match
        if record["predicted_severity"] and record["actual_severity"]:
            record["severity_match"] = record["predicted_severity"] == record["actual_severity"]

        # Casualty error
        if record["predicted_casualties"] is not None and record["actual_casualties"] is not None:
            pred_c = record["predicted_casualties"]
            actual_c = record["actual_casualties"]
            record["casualty_error"] = actual_c - pred_c
            if pred_c > 0:
                record["casualty_error_pct"] = round((actual_c - pred_c) / pred_c * 100, 2)

        # Damage error
        if record["predicted_damage_usd"] is not None and record["actual_damage_usd"] is not None:
            pred_d = record["predicted_damage_usd"]
            actual_d = record["actual_damage_usd"]
            record["damage_error"] = actual_d - pred_d
            if pred_d > 0:
                record["damage_error_pct"] = round((actual_d - pred_d) / pred_d * 100, 2)

        # Area error
        if record["predicted_area_km2"] is not None and record["actual_area_km2"] is not None:
            pred_a = record["predicted_area_km2"]
            actual_a = record["actual_area_km2"]
            record["area_error"] = actual_a - pred_a
            if pred_a > 0:
                record["area_error_pct"] = round((actual_a - pred_a) / pred_a * 100, 2)

        try:
            resp = supabase_admin.table("outcome_tracking").insert(record).execute()
            stored = resp.data[0] if resp.data else record
            logger.info(f"Outcome logged for disaster {disaster_id}, type {prediction_type}")
            return stored
        except Exception as e:
            logger.error(f"Failed to log outcome: {e}")
            raise

    # ── Automated outcome capturing ────────────────────────────────

    async def auto_capture_outcomes(self) -> List[Dict]:
        """
        Automatically capture outcomes from resolved disasters.
        Matches predictions to actual disaster data for resolved disasters
        that don't yet have outcome records.
        """
        captured = []

        try:
            # Get resolved disasters from the last 30 days
            since = (datetime.utcnow() - timedelta(days=30)).isoformat()
            disasters_resp = (
                supabase_admin.table("disasters")
                .select("id, type, severity, casualties, estimated_damage, start_date, end_date")
                .eq("status", "resolved")
                .gte("updated_at", since)
                .execute()
            )
            disasters = disasters_resp.data or []

            for disaster in disasters:
                disaster_id = disaster["id"]

                # Get predictions for this disaster
                pred_resp = (
                    supabase_admin.table("predictions")
                    .select("id, prediction_type, predicted_severity, predicted_casualties, affected_area_km, features, model_version")
                    .eq("disaster_id", disaster_id)
                    .execute()
                )
                predictions = pred_resp.data or []

                # Check if outcomes already exist
                existing_resp = (
                    supabase_admin.table("outcome_tracking")
                    .select("prediction_id")
                    .eq("disaster_id", disaster_id)
                    .execute()
                )
                existing_pred_ids = {r["prediction_id"] for r in (existing_resp.data or []) if r.get("prediction_id")}

                for pred in predictions:
                    if pred["id"] in existing_pred_ids:
                        continue

                    outcome_data = {
                        "disaster_id": disaster_id,
                        "prediction_id": pred["id"],
                        "prediction_type": pred["prediction_type"],
                        "actual_severity": disaster.get("severity"),
                        "actual_casualties": disaster.get("casualties"),
                        "actual_damage_usd": disaster.get("estimated_damage"),
                        "logged_by": "system",
                        "notes": "Auto-captured from resolved disaster data",
                    }

                    try:
                        result = await self.log_outcome(outcome_data)
                        if result:
                            captured.append(result)
                    except Exception as e:
                        logger.error(f"Failed to auto-capture outcome for prediction {pred['id']}: {e}")

            logger.info(f"Auto-captured {len(captured)} outcomes from {len(disasters)} resolved disasters")
        except Exception as e:
            logger.error(f"Auto-capture outcomes failed: {e}")

        return captured

    # ── Evaluation report generation ───────────────────────────────

    async def generate_evaluation_report(
        self,
        model_type: Optional[str] = None,
        period_days: int = 7,
    ) -> List[Dict]:
        """
        Generate model evaluation reports for each prediction type.

        Computes accuracy/MAE/RMSE/MAPE metrics from outcome tracking data.
        """
        since = (datetime.utcnow() - timedelta(days=period_days)).isoformat()
        types_to_evaluate = [model_type] if model_type else ["severity", "spread", "impact"]

        reports = []
        for ptype in types_to_evaluate:
            try:
                resp = (
                    supabase_admin.table("outcome_tracking")
                    .select("*")
                    .eq("prediction_type", ptype)
                    .gte("created_at", since)
                    .execute()
                )
                outcomes = resp.data or []

                if not outcomes:
                    logger.info(f"No outcomes for {ptype} in the last {period_days} days")
                    continue

                report = self._compute_metrics(ptype, outcomes)
                report["report_date"] = date.today().isoformat()
                report["report_period"] = "weekly" if period_days == 7 else "monthly"
                report["model_type"] = ptype
                report["total_predictions"] = len(outcomes)
                report["total_with_outcomes"] = len([o for o in outcomes if any([
                    o.get("actual_severity"),
                    o.get("actual_casualties") is not None,
                    o.get("actual_damage_usd") is not None,
                    o.get("actual_area_km2") is not None,
                ])])

                # Determine if retraining should be triggered
                retrain_triggered = self._should_retrain(ptype, report)
                report["retrain_triggered"] = retrain_triggered

                if report.get("model_version") is None:
                    versions = [o.get("model_version") for o in outcomes if o.get("model_version")]
                    report["model_version"] = versions[0] if versions else None

                # Store report
                db_record = {k: v for k, v in report.items()}
                try:
                    db_resp = supabase_admin.table("model_evaluation_reports").insert(db_record).execute()
                    stored = db_resp.data[0] if db_resp.data else db_record
                    reports.append(stored)
                except Exception as e:
                    logger.error(f"Failed to store evaluation report for {ptype}: {e}")
                    reports.append(report)

                # Trigger retraining if needed
                if retrain_triggered:
                    await self._trigger_retrain(ptype, report)

            except Exception as e:
                logger.error(f"Evaluation failed for {ptype}: {e}")

        logger.info(f"Generated {len(reports)} evaluation reports")
        return reports

    def _compute_metrics(self, ptype: str, outcomes: List[Dict]) -> Dict:
        """Compute accuracy metrics for a prediction type."""
        metrics = {
            "accuracy": None,
            "mae": None,
            "rmse": None,
            "mape": None,
            "r_squared": None,
            "metrics_breakdown": {},
            "recommendations": [],
        }

        if ptype == "severity":
            # Classification metrics
            matches = [o for o in outcomes if o.get("severity_match") is not None]
            if matches:
                correct = sum(1 for o in matches if o["severity_match"])
                metrics["accuracy"] = round(correct / len(matches), 4)

                # Confusion matrix
                severity_levels = ["low", "medium", "high", "critical"]
                confusion = {}
                for o in matches:
                    pred = o.get("predicted_severity", "unknown")
                    actual = o.get("actual_severity", "unknown")
                    key = f"{pred}_vs_{actual}"
                    confusion[key] = confusion.get(key, 0) + 1
                metrics["metrics_breakdown"]["confusion_matrix"] = confusion

                if metrics["accuracy"] < self.auto_retrain_accuracy:
                    metrics["recommendations"].append({
                        "action": "retrain_severity_model",
                        "reason": f"Accuracy {metrics['accuracy']:.1%} below threshold {self.auto_retrain_accuracy:.1%}",
                        "priority": "high",
                    })

        elif ptype == "impact":
            # Regression metrics for casualties
            casualty_errors = [o for o in outcomes if o.get("casualty_error") is not None]
            if casualty_errors:
                errors = [o["casualty_error"] for o in casualty_errors]
                abs_errors = [abs(e) for e in errors]
                metrics["mae"] = round(sum(abs_errors) / len(abs_errors), 2)
                metrics["rmse"] = round(math.sqrt(sum(e ** 2 for e in errors) / len(errors)), 2)

                pct_errors = [abs(o["casualty_error_pct"]) for o in casualty_errors if o.get("casualty_error_pct") is not None]
                if pct_errors:
                    metrics["mape"] = round(sum(pct_errors) / len(pct_errors), 2)

                metrics["metrics_breakdown"]["casualty_metrics"] = {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "count": len(casualty_errors),
                }

            # Damage metrics
            damage_errors = [o for o in outcomes if o.get("damage_error") is not None]
            if damage_errors:
                d_errors = [o["damage_error"] for o in damage_errors]
                d_abs = [abs(e) for e in d_errors]
                damage_mae = round(sum(d_abs) / len(d_abs), 2)
                damage_rmse = round(math.sqrt(sum(e ** 2 for e in d_errors) / len(d_errors)), 2)
                metrics["metrics_breakdown"]["damage_metrics"] = {
                    "mae": damage_mae,
                    "rmse": damage_rmse,
                    "count": len(damage_errors),
                }

        elif ptype == "spread":
            # Area prediction metrics
            area_errors = [o for o in outcomes if o.get("area_error") is not None]
            if area_errors:
                errors = [o["area_error"] for o in area_errors]
                abs_errors = [abs(e) for e in errors]
                metrics["mae"] = round(sum(abs_errors) / len(abs_errors), 2)
                metrics["rmse"] = round(math.sqrt(sum(e ** 2 for e in errors) / len(errors)), 2)

                pct_errors = [abs(o["area_error_pct"]) for o in area_errors if o.get("area_error_pct") is not None]
                if pct_errors:
                    metrics["mape"] = round(sum(pct_errors) / len(pct_errors), 2)

                metrics["metrics_breakdown"]["area_metrics"] = {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "count": len(area_errors),
                }

        return metrics

    def _should_retrain(self, ptype: str, report: Dict) -> bool:
        """Determine if auto-retraining should be triggered."""
        if ptype == "severity":
            accuracy = report.get("accuracy")
            if accuracy is not None and accuracy < self.auto_retrain_accuracy:
                return True
        else:
            mae = report.get("mae")
            if mae is not None and mae > self.auto_retrain_mae:
                return True
        return False

    async def _trigger_retrain(self, model_type: str, report: Dict):
        """Trigger model retraining via the existing retrain endpoint."""
        logger.info(f"Auto-retraining triggered for {model_type} model")
        try:
            # Call the retrain endpoint internally
            # The retrain router is available at /api/ml/retrain
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                base_url = "http://localhost:8000"
                resp = await client.post(
                    f"{base_url}/api/ml/retrain",
                    json={"model_type": model_type},
                )
                if resp.status_code == 200:
                    logger.info(f"Retraining started for {model_type}")
                else:
                    logger.warning(f"Retraining request failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"Failed to trigger retraining: {e}")

    # ── Retrieval ──────────────────────────────────────────────────

    async def get_outcomes(
        self,
        disaster_id: Optional[str] = None,
        prediction_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Get outcome tracking records."""
        query = (
            supabase_admin.table("outcome_tracking")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if disaster_id:
            query = query.eq("disaster_id", disaster_id)
        if prediction_type:
            query = query.eq("prediction_type", prediction_type)

        resp = query.execute()
        return resp.data or []

    async def get_evaluation_reports(
        self,
        model_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """Get model evaluation reports."""
        query = (
            supabase_admin.table("model_evaluation_reports")
            .select("*")
            .order("report_date", desc=True)
            .limit(limit)
        )
        if model_type:
            query = query.eq("model_type", model_type)

        resp = query.execute()
        return resp.data or []

    async def get_accuracy_summary(self) -> Dict:
        """Get a summary of model accuracy across all types."""
        summary = {}
        for ptype in ["severity", "spread", "impact"]:
            resp = (
                supabase_admin.table("model_evaluation_reports")
                .select("*")
                .eq("model_type", ptype)
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )
            if resp.data:
                latest = resp.data[0]
                summary[ptype] = {
                    "report_date": latest.get("report_date"),
                    "accuracy": latest.get("accuracy"),
                    "mae": latest.get("mae"),
                    "rmse": latest.get("rmse"),
                    "mape": latest.get("mape"),
                    "total_predictions": latest.get("total_predictions"),
                    "retrain_triggered": latest.get("retrain_triggered"),
                }
            else:
                summary[ptype] = {"status": "no_data"}

        return summary
