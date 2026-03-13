"""
Phase 5 – Outcome Tracking & Model Feedback Loop Service.

Logs actual vs predicted outcomes, computes error metrics,
generates weekly evaluation reports, and triggers retraining when needed.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any

from app.core.phase5_config import phase5_config
from app.database import db_admin

logger = logging.getLogger("outcome_service")


class OutcomeTrackingService:
    """Tracks prediction accuracy and manages the model feedback loop."""

    def __init__(self):
        self.auto_retrain_mae = phase5_config.AUTO_RETRAIN_THRESHOLD_MAE
        self.auto_retrain_accuracy = phase5_config.AUTO_RETRAIN_THRESHOLD_ACCURACY
        self.min_outcomes_for_retrain = 20
        self.severity_hard_floor = 0.50
        self.regression_hard_ceiling_mult = 1.75
        self.rmse_mae_ratio_ceiling = 2.2

    def _safe_round(self, value: Any, digits: int = 2) -> float:
        """Helper to round values safely, avoiding strict type checker issues."""
        try:
            if value is None:
                return 0.0
            return float(round(float(value), digits))
        except (ValueError, TypeError):
            return 0.0

    # ── Outcome logging ────────────────────────────────────────────

    async def log_outcome(self, outcome_data: dict) -> dict | None:
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
                resp = await db_admin.table("predictions").select("*").eq("id", prediction_id).single().async_execute()
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
        pred_c = record.get("predicted_casualties")
        actual_c = record.get("actual_casualties")
        if pred_c is not None and actual_c is not None:
            c_err = float(actual_c) - float(pred_c)
            record["casualty_error"] = c_err
            if float(pred_c) > 0:
                record["casualty_error_pct"] = self._safe_round(c_err / float(pred_c) * 100, 2)

        # Damage error
        pred_d = record.get("predicted_damage_usd")
        actual_d = record.get("actual_damage_usd")
        if pred_d is not None and actual_d is not None:
            d_err = float(actual_d) - float(pred_d)
            record["damage_error"] = d_err
            if float(pred_d) > 0:
                record["damage_error_pct"] = self._safe_round(d_err / float(pred_d) * 100, 2)

        # Area error
        pred_a = record.get("predicted_area_km2")
        actual_a = record.get("actual_area_km2")
        if pred_a is not None and actual_a is not None:
            a_err = float(actual_a) - float(pred_a)
            record["area_error"] = a_err
            if float(pred_a) > 0:
                record["area_error_pct"] = self._safe_round(a_err / float(pred_a) * 100, 2)

        try:
            resp = await db_admin.table("outcome_tracking").insert(record).async_execute()
            stored = resp.data[0] if resp.data else record

            # Detailed logging for feedback loop
            match_status = "MATCH" if record.get("severity_match") else "MISMATCH"
            logger.info(
                f"Outcome Feedback: disaster={disaster_id}, type={prediction_type}, "
                f"predicted={record.get('predicted_severity')}, actual={record.get('actual_severity')} -> {match_status}"
            )

            if record.get("casualty_error") is not None:
                logger.debug(f"Casualty Error: {record['casualty_error']} (actual={record['actual_casualties']})")

            return stored
        except Exception as e:
            logger.error(f"Failed to log outcome feedback: {e}")
            raise

    # ── Automated outcome capturing ────────────────────────────────

    async def auto_capture_outcomes(self) -> list[dict]:
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
                await db_admin.table("disasters")
                .select("id, type, severity, casualties, estimated_damage, start_date, end_date")
                .eq("status", "resolved")
                .gte("updated_at", since)
                .async_execute()
            )
            disasters = disasters_resp.data or []

            for disaster in disasters:
                disaster_id = disaster["id"]

                # Get predictions for this disaster
                pred_resp = (
                    await db_admin.table("predictions")
                    .select(
                        "id, prediction_type, predicted_severity, predicted_casualties, affected_area_km, features, model_version"
                    )
                    .eq("disaster_id", disaster_id)
                    .async_execute()
                )
                predictions = pred_resp.data or []

                # Check if outcomes already exist
                existing_resp = (
                    await db_admin.table("outcome_tracking")
                    .select("prediction_id")
                    .eq("disaster_id", disaster_id)
                    .async_execute()
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
        model_type: str | None = None,
        period_days: int = 7,
    ) -> list[dict]:
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
                    await db_admin.table("outcome_tracking")
                    .select("*")
                    .eq("prediction_type", ptype)
                    .gte("created_at", since)
                    .async_execute()
                )
                outcomes = resp.data or []

                if not outcomes:
                    logger.info(f"No outcomes for {ptype} in the last {period_days} days")
                    continue

                report = self._compute_metrics(ptype, outcomes)
                report["report_date"] = datetime.utcnow().date().isoformat()
                report["report_period"] = "weekly" if period_days == 7 else "monthly"
                report["model_type"] = ptype
                report["total_predictions"] = len(outcomes)
                report["total_with_outcomes"] = len(
                    [
                        o
                        for o in outcomes
                        if any(
                            [
                                o.get("actual_severity"),
                                o.get("actual_casualties") is not None,
                                o.get("actual_damage_usd") is not None,
                                o.get("actual_area_km2") is not None,
                            ]
                        )
                    ]
                )

                # Determine if retraining should be triggered
                retrain_triggered = self._should_retrain(ptype, report)
                report["retrain_triggered"] = retrain_triggered

                if report.get("model_version") is None:
                    versions = [o.get("model_version") for o in outcomes if o.get("model_version")]
                    report["model_version"] = versions[0] if versions else None

                # Store report
                db_record = {k: v for k, v in report.items()}
                try:
                    db_resp = await db_admin.table("model_evaluation_reports").insert(db_record).async_execute()
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

    def _compute_metrics(self, ptype: str, outcomes: list[dict]) -> dict:
        """Compute accuracy metrics for a prediction type."""
        metrics: dict[str, Any] = {
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
                metrics["accuracy"] = round(float(correct / len(matches)), 4)

                # Confusion matrix
                confusion = {}
                for o in matches:
                    pred = o.get("predicted_severity", "unknown")
                    actual = o.get("actual_severity", "unknown")
                    key = f"{pred}_vs_{actual}"
                    confusion[key] = confusion.get(key, 0) + 1
                metrics["metrics_breakdown"]["confusion_matrix"] = confusion

                if metrics["accuracy"] < self.auto_retrain_accuracy:
                    metrics["recommendations"].append(
                        {
                            "action": "retrain_severity_model",
                            "reason": f"Accuracy {metrics['accuracy']:.1%} below threshold {self.auto_retrain_accuracy:.1%}",
                            "priority": "high",
                        }
                    )

        elif ptype == "impact":
            # Regression metrics for casualties
            casualty_errors = [o for o in outcomes if o.get("casualty_error") is not None]
            if casualty_errors:
                errors = [float(o["casualty_error"]) for o in casualty_errors]
                abs_errors = [abs(e) for e in errors]
                metrics["mae"] = round(float(sum(abs_errors) / len(abs_errors)), 2)
                metrics["rmse"] = round(float(math.sqrt(sum(e**2 for e in errors) / len(errors))), 2)

                pct_errors = [
                    abs(float(o["casualty_error_pct"]))
                    for o in casualty_errors
                    if o.get("casualty_error_pct") is not None
                ]
                if pct_errors:
                    metrics["mape"] = round(float(sum(pct_errors) / len(pct_errors)), 2)

                metrics["metrics_breakdown"]["casualty_metrics"] = {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "count": len(casualty_errors),
                }

            # Damage metrics
            damage_errors = [o for o in outcomes if o.get("damage_error") is not None]
            if damage_errors:
                d_errors = [float(o["damage_error"]) for o in damage_errors]
                d_abs = [abs(e) for e in d_errors]
                damage_mae = round(float(sum(d_abs) / len(d_abs)), 2)
                damage_rmse = round(float(math.sqrt(sum(e**2 for e in d_errors) / len(d_errors))), 2)
                metrics["metrics_breakdown"]["damage_metrics"] = {
                    "mae": damage_mae,
                    "rmse": damage_rmse,
                    "count": len(damage_errors),
                }

        elif ptype == "spread":
            # Area prediction metrics
            area_errors = [o for o in outcomes if o.get("area_error") is not None]
            if area_errors:
                errors = [float(o["area_error"]) for o in area_errors]
                abs_errors = [abs(e) for e in errors]
                metrics["mae"] = round(float(sum(abs_errors) / len(abs_errors)), 2)
                metrics["rmse"] = round(float(math.sqrt(sum(e**2 for e in errors) / len(errors))), 2)

                pct_errors = [
                    abs(float(o["area_error_pct"])) for o in area_errors if o.get("area_error_pct") is not None
                ]
                if pct_errors:
                    metrics["mape"] = round(float(sum(pct_errors) / len(pct_errors)), 2)

                metrics["metrics_breakdown"]["area_metrics"] = {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "count": len(area_errors),
                }

        return metrics

    def _should_retrain(self, ptype: str, report: dict) -> bool:
        """Determine if auto-retraining should be triggered.

        Policy:
        - Require minimum outcome count to avoid noisy triggers.
        - Trigger on hard failure thresholds immediately.
        - Otherwise require at least two weak-degradation signals.
        """
        sample_count = int(report.get("total_with_outcomes") or report.get("total_predictions") or 0)
        if sample_count < self.min_outcomes_for_retrain:
            return False

        if ptype == "severity":
            accuracy = report.get("accuracy")
            if accuracy is None:
                return False

            accuracy = float(accuracy)
            if accuracy <= self.severity_hard_floor:
                return True

            weak_signals = 0
            if accuracy < self.auto_retrain_accuracy:
                weak_signals += 1

            confusion = (report.get("metrics_breakdown") or {}).get("confusion_matrix") or {}
            if confusion and len(confusion) >= 6:
                weak_signals += 1

            return weak_signals >= 2

        mae = report.get("mae")
        if mae is None:
            return False

        mae = float(mae)
        if mae >= (self.auto_retrain_mae * self.regression_hard_ceiling_mult):
            return True

        rmse = report.get("rmse")
        mape = report.get("mape")

        weak_signals = 0
        if mae > self.auto_retrain_mae:
            weak_signals += 1
        if mape is not None and float(mape) > 35.0:
            weak_signals += 1
        if rmse is not None and mae > 0 and float(rmse) / mae > self.rmse_mae_ratio_ceiling:
            weak_signals += 1

        return weak_signals >= 2

        return False

    async def _trigger_retrain(self, model_type: str, report: dict):
        """Trigger model retraining via the existing retrain endpoint."""
        logger.info(
            f"Model Performance Alert: Retraining triggered for '{model_type}'. "
            f"Metrics: accuracy={report.get('accuracy', 'N/A')}, mae={report.get('mae', 'N/A')}"
        )

        try:
            # The retrain router is available at /api/ml/retrain
            import httpx

            # Use configurable base URL from Phase5Config
            base_url = phase5_config.API_BASE_URL

            logger.info(f"Initiating retraining request to {base_url}/api/ml/retrain...")

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{base_url}/api/ml/retrain",
                    json={"model_type": model_type},
                )
                if resp.status_code == 200:
                    logger.info(f"Retraining accepted for {model_type}. Response: {resp.json()}")
                else:
                    logger.warning(f"Retraining request rejected: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Critical failure in retraining trigger for {model_type}: {e}")

    # ── Retrieval ──────────────────────────────────────────────────

    async def get_outcomes(
        self,
        disaster_id: str | None = None,
        prediction_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get outcome tracking records."""
        query = (
            db_admin.table("outcome_tracking")
            .select("*")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if disaster_id:
            query = query.eq("disaster_id", disaster_id)
        if prediction_type:
            query = query.eq("prediction_type", prediction_type)

        resp = await query.async_execute()
        return resp.data or []

    async def get_evaluation_reports(
        self,
        model_type: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Get model evaluation reports."""
        query = db_admin.table("model_evaluation_reports").select("*").order("report_date", desc=True).limit(limit)
        if model_type:
            query = query.eq("model_type", model_type)

        resp = await query.async_execute()
        return resp.data or []

    async def get_accuracy_summary(self) -> dict:
        """Get a summary of model accuracy across all types."""
        summary = {}
        for ptype in ["severity", "spread", "impact"]:
            resp = (
                await db_admin.table("model_evaluation_reports")
                .select("*")
                .eq("model_type", ptype)
                .order("report_date", desc=True)
                .limit(1)
                .async_execute()
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
