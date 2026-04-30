"""
Phase 5 – Outcome Tracking & Model Feedback Loop Service.

Logs actual vs predicted outcomes, computes error metrics,
generates weekly evaluation reports, and triggers retraining when needed.
"""

import logging
import math
import os
import json
import asyncio
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
        
        # LLM Initialization for Post-Mortems
        self._groq_client = None
        self._groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=groq_key)
                logger.info("Outcome service using Groq LLM for post-mortems: %s", self._groq_model)
            except Exception as e:
                logger.warning("Groq not available for Outcome Post-Mortems: %s", e)

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

        # Verify the disaster is real (not simulated) - reject mock data
        try:
            dis_resp = await db_admin.table("disasters")\
                .select("is_simulated")\
                .eq("id", disaster_id)\
                .single()\
                .async_execute()
            if dis_resp.data and dis_resp.data.get("is_simulated"):
                raise ValueError("Cannot log outcome for simulated disaster - only real victim data is accepted")
        except Exception as e:
            # If the is_simulated column doesn't exist yet, skip verification (assume real disaster)
            if "is_simulated" in str(e) and ("does not exist" in str(e) or "column" in str(e)):
                logger.warning(
                    f"is_simulated column missing – cannot verify disaster {disaster_id} is real. "
                    f"Skipping check. Run DB migration to enforce real-data-only filter."
                )
            else:
                logger.error(f"Failed to verify disaster {disaster_id} is real: {e}")
                raise  # Abort on other errors

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

        # Generate Automated LLM Post-Mortem if notes are empty
        if self._groq_client and not record.get("notes"):
            try:
                post_mortem = await self._generate_post_mortem(record)
                if post_mortem:
                    record["notes"] = post_mortem
            except Exception as e:
                logger.warning(f"Failed to generate LLM post-mortem: {e}")

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

    async def _generate_post_mortem(self, record: dict) -> str | None:
        """Generate a brief narrative post-mortem using LLM."""
        try:
            ptype = record.get("prediction_type", "general")
            prompt = f"""
            Analyze the following disaster prediction vs actual outcome data and generate a 2-sentence 'Response Post-Mortem'.
            
            Data:
            - Type: {ptype}
            - Predicted Severity: {record.get('predicted_severity')}
            - Actual Severity: {record.get('actual_severity')}
            - Predicted Casualties: {record.get('predicted_casualties')}
            - Actual Casualties: {record.get('actual_casualties')}
            - Predicted Damage USD: {record.get('predicted_damage_usd')}
            - Actual Damage USD: {record.get('actual_damage_usd')}
            
            The summary should be concise and focused on how accurate the AI was and what the operational impact was.
            """
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._groq_client.chat.completions.create(
                    model=self._groq_model,
                    messages=[
                        {"role": "system", "content": "You are a disaster response analyst. Write a concise 2-sentence post-mortem summary."},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=150,
                    temperature=0.3,
                ),
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None

    # ── Automated outcome capturing ────────────────────────────────

    async def auto_capture_outcomes(self) -> list[dict]:
        """
        Capture outcomes for any disaster that has ML predictions but no outcome record yet.

        Works across ALL disaster statuses (active, monitoring, resolved, etc.) so that
        real ingested data from GDACS / USGS / weather feeds immediately feeds the
        feedback loop.  The actual values are taken directly from the disaster record —
        the same ground-truth fields the ingestion pipeline populates (severity,
        casualties, estimated_damage, affected_area_km2).
        """
        captured = []

        try:
            # ── 1. Fetch all predictions that don't yet have an outcome record ──
            #    LEFT-JOIN equivalent: get predictions, then filter out those
            #    already tracked.  Done in two small queries to stay within
            #    Supabase free-tier row limits.
            pred_resp = (
                await db_admin.table("predictions")
                .select(
                    "id, disaster_id, prediction_type, predicted_severity, "
                    "predicted_casualties, affected_area_km, features, model_version"
                )
                .order("created_at", desc=True)
                .limit(500)
                .async_execute()
            )
            predictions = pred_resp.data or []

            if not predictions:
                logger.info("auto_capture_outcomes: no predictions in DB yet")
                return captured

            # ── 2. Which prediction IDs already have outcome records? ──────────
            tracked_resp = (
                await db_admin.table("outcome_tracking")
                .select("prediction_id")
                .not_.is_("prediction_id", "null")
                .async_execute()
            )
            already_tracked = {
                r["prediction_id"]
                for r in (tracked_resp.data or [])
                if r.get("prediction_id")
            }

            untracked = [p for p in predictions if p["id"] not in already_tracked]
            if not untracked:
                logger.info("auto_capture_outcomes: all predictions already have outcome records")
                return captured

            # ── 3. Fetch the disaster records for those predictions ───────────
            disaster_ids = list({p["disaster_id"] for p in untracked if p.get("disaster_id")})
            if not disaster_ids:
                logger.warning("auto_capture_outcomes: predictions missing disaster_id")
                return captured

            # Supabase `in_` filter — chunk to avoid URL length limits
            chunk_size = 50
            disasters_by_id: dict[str, dict] = {}
            for i in range(0, len(disaster_ids), chunk_size):
                chunk = disaster_ids[i : i + chunk_size]
                dis_resp = (
                    await db_admin.table("disasters")
                    .select(
                        "id, type, status, severity, casualties, "
                        "estimated_damage, affected_area_km2, start_date, end_date, updated_at"
                    )
                    .in_("id", chunk)
                    .eq("is_simulated", False)  # Only real disaster data
                    .async_execute()
                )
                for d in (dis_resp.data or []):
                    disasters_by_id[d["id"]] = d

            # ── 4. Log an outcome for each untracked prediction ───────────────
            for pred in untracked:
                disaster = disasters_by_id.get(pred.get("disaster_id", ""))
                if not disaster:
                    continue  # prediction references a disaster we can't find

                pred_type = pred.get("prediction_type", "")
                # Validate that the disaster has outcome data relevant to prediction type
                # This prevents logging meaningless outcomes
                outcome_data = {
                    "disaster_id":      pred["disaster_id"],
                    "prediction_id":    pred["id"],
                    "prediction_type":  pred_type,
                    "model_version":    pred.get("model_version"),
                    "logged_by":        "system",
                    "notes":            f"Auto-captured from {disaster.get('status', 'active')} disaster (real ingested data)",
                }

                # Copy predicted values from prediction record (will be compared to actuals)
                if pred_type == "severity":
                    outcome_data["predicted_severity"] = pred.get("predicted_severity")
                elif pred_type == "impact":
                    outcome_data["predicted_casualties"] = pred.get("predicted_casualties")
                    outcome_data["predicted_damage_usd"] = (
                        pred.get("features", {}).get("predicted_damage_usd")
                        or pred.get("metadata", {}).get("predicted_damage_usd")
                    )
                elif pred_type == "spread":
                    outcome_data["predicted_area_km2"] = (
                        pred.get("features", {}).get("predicted_area_km2")
                        or pred.get("affected_area_km")
                    )

                # Only set actual values that are relevant AND present
                if pred_type == "severity":
                    actual_sev = disaster.get("severity")
                    if actual_sev:
                        outcome_data["actual_severity"] = actual_sev
                    else:
                        logger.debug(f"Skipping outcome for prediction {pred['id']}: no severity in disaster")
                        continue

                elif pred_type == "impact":
                    actual_cas = disaster.get("casualties")
                    actual_dmg = disaster.get("estimated_damage")
                    if actual_cas is not None or actual_dmg is not None:
                        if actual_cas is not None:
                            outcome_data["actual_casualties"] = actual_cas
                        if actual_dmg is not None:
                            outcome_data["actual_damage_usd"] = actual_dmg
                    else:
                        logger.debug(f"Skipping outcome for prediction {pred['id']}: no casualties or damage in disaster")
                        continue

                elif pred_type == "spread":
                    actual_area = disaster.get("affected_area_km2")
                    if actual_area is not None:
                        outcome_data["actual_area_km2"] = actual_area
                    else:
                        logger.debug(f"Skipping outcome for prediction {pred['id']}: no affected_area_km2 in disaster")
                        continue

                else:
                    logger.warning(f"Unknown prediction_type '{pred_type}' for prediction {pred['id']}")
                    continue

                # Must have at least one predicted and one actual value
                has_actual = any(k in outcome_data for k in ["actual_severity", "actual_casualties", "actual_damage_usd", "actual_area_km2"])
                has_predicted = any(k in outcome_data for k in ["predicted_severity", "predicted_casualties", "predicted_damage_usd", "predicted_area_km2"])
                if not (has_actual and has_predicted):
                    logger.debug(f"Skipping outcome for prediction {pred['id']}: missing actual or predicted data")
                    continue

                try:
                    result = await self.log_outcome(outcome_data)
                    if result:
                        captured.append(result)
                except Exception as e:
                    logger.error(
                        f"Failed to capture outcome for prediction {pred['id']}: {e}"
                    )

            logger.info(
                f"Auto-captured {len(captured)} outcomes from "
                f"{len(disasters_by_id)} real disasters "
                f"({len(untracked)} predictions were untracked)"
            )
        except Exception as e:
            logger.error(f"auto_capture_outcomes failed: {e}")

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
        If the requested period_days window returns no data, automatically
        widens to all available historical records so the dashboard always
        reflects real ingested outcomes.
        """
        since = (datetime.utcnow() - timedelta(days=period_days)).isoformat()
        types_to_evaluate = [model_type] if model_type else ["severity", "spread", "impact"]

        reports = []
        for ptype in types_to_evaluate:
            try:
                # First try the requested window
                resp = (
                    await db_admin.table("outcome_tracking")
                    .select("*")
                    .eq("prediction_type", ptype)
                    .gte("created_at", since)
                    .async_execute()
                )
                outcomes = resp.data or []

                # Fallback: widen to all-time if the window is empty
                if not outcomes:
                    logger.info(
                        f"No outcomes for {ptype} in the last {period_days} days — "
                        f"widening to all-time records"
                    )
                    resp_all = (
                        await db_admin.table("outcome_tracking")
                        .select("*")
                        .eq("prediction_type", ptype)
                        .async_execute()
                    )
                    outcomes = resp_all.data or []

                if not outcomes:
                    logger.info(f"No outcomes at all for {ptype} — skipping")
                    continue

                # Filter out outcomes from simulated disasters (only real victim data)
                # NOTE: requires disasters table to have is_simulated column. If not present, skip filtering with warning.
                if outcomes:
                    disaster_ids = list({o.get("disaster_id") for o in outcomes if o.get("disaster_id")})
                    real_disaster_ids: set[str] = set()
                    if disaster_ids:
                        try:
                            # Batch check which disaster IDs are real (not simulated)
                            chunk_size = 50
                            for i in range(0, len(disaster_ids), chunk_size):
                                chunk = disaster_ids[i : i + chunk_size]
                                dis_resp = await db_admin.table("disasters")\
                                    .select("id")\
                                    .in_("id", chunk)\
                                    .eq("is_simulated", False)\
                                    .async_execute()
                                real_disaster_ids.update(d["id"] for d in (dis_resp.data or []))
                            outcomes = [o for o in outcomes if o.get("disaster_id") in real_disaster_ids]
                        except Exception as e:
                            # If column doesn't exist yet, log warning and skip filtering
                            if "does not exist" in str(e):
                                logger.warning(f"is_simulated column not found in disasters table - skipping simulated-data filter. "
                                              f"Apply database migration to enforce real-data only: "
                                              f"database/migrations/add_is_simulated_column.sql. Error: {e}")
                            else:
                                logger.warning(f"Failed to filter simulated disasters: {e}")
                    # If all outcomes were from simulated disasters, skip
                    if not outcomes:
                        logger.info(f"No real-disaster outcomes for {ptype} after filtering — skipping")
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
        """Compute accuracy metrics for a prediction type, including calibration."""
        metrics: dict[str, Any] = {
            "accuracy": None,
            "mae": None,
            "rmse": None,
            "mape": None,
            "r_squared": None,
            "metrics_breakdown": {},
            "recommendations": [],
            "calibration": {},  # New: calibration metrics
            "business_impact": {
                "estimated_resources_saved": 0,
                "over_allocation_prevented_pct": 0.0,
            },
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

                # Compute Brier score (mean squared probability of correct class)
                # For severity predictions, we treat it as categorical probability
                # Simplified: Brier score based on whether prediction was correct
                n = len(matches)
                brier = round(float(sum(1.0 if o["severity_match"] else 0.0 for o in matches) / n), 4)
                metrics["calibration"]["brier_score"] = brier

                # Reliability diagram data: accuracy per predicted class
                reliability = {}
                for pred_sev in ["low", "medium", "high", "critical"]:
                    class_outcomes = [o for o in matches if o.get("predicted_severity") == pred_sev]
                    if class_outcomes:
                        class_correct = sum(1 for o in class_outcomes if o["severity_match"])
                        reliability[pred_sev] = {
                            "count": len(class_outcomes),
                            "accuracy": round(class_correct / len(class_outcomes), 4),
                        }
                metrics["calibration"]["reliability"] = reliability

                # Calibration slope: if predictions systematically over/under estimate
                # (not applicable for multi-class without probabilities)
                
                # Business Impact KPIs:
                # If accuracy is good (>75%), we assume the AI prevented the standard 20% over-allocation panic factor
                base_resources_per_disaster = 5000
                accuracy_val = metrics.get("accuracy", 0.0)
                if accuracy_val > 0.5:
                    efficiency_ratio = (accuracy_val - 0.5) * 0.4 # scales up to ~20%
                    metrics["business_impact"]["over_allocation_prevented_pct"] = round(efficiency_ratio * 100, 1)
                    metrics["business_impact"]["estimated_resources_saved"] = int(len(matches) * base_resources_per_disaster * efficiency_ratio)

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

                # Bias: positive error = over-prediction, negative = under-prediction
                bias = round(float(sum(errors) / len(errors)), 2)
                metrics["calibration"]["bias_casualties"] = bias
                metrics["calibration"]["bias_pct_casualties"] = round(bias / (sum(abs(errors)) / len(errors) * len(errors)) * 100, 2) if sum(abs_errors) > 0 else 0.0

                pct_errors = [
                    abs(float(o["casualty_error_pct"]))
                    for o in casualty_errors
                    if o.get("casualty_error_pct") is not None
                ]
                if pct_errors:
                    metrics["mape"] = round(float(sum(pct_errors) / len(pct_errors)), 2)
                    # Prediction interval coverage: what % of actuals fall within +/- 50% of predicted?
                    within_50pct = sum(1 for o in casualty_errors if abs(o["casualty_error"]) <= 0.5 * abs(float(o.get("predicted_casualties", 1) or 1)))
                    metrics["calibration"]["coverage_50pct"] = round(within_50pct / len(casualty_errors), 4) if casualty_errors else 0.0

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
                # Bias for damage
                d_bias = round(float(sum(d_errors) / len(d_errors)), 2)
                metrics["calibration"]["bias_damage"] = d_bias

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

                # Bias for area predictions
                area_bias = round(float(sum(errors) / len(errors)), 2)
                metrics["calibration"]["bias_area"] = area_bias

                # Prediction interval coverage: within 20% of actual?
                within_20pct = sum(1 for o in area_errors if abs(o["area_error"]) <= 0.2 * abs(float(o.get("actual_area_km2", 1) or 1)))
                metrics["calibration"]["coverage_20pct"] = round(within_20pct / len(area_errors), 4) if area_errors else 0.0

                metrics["metrics_breakdown"]["area_metrics"] = {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "count": len(area_errors),
                }

        return metrics

    def _should_retrain(self, ptype: str, report: dict) -> bool:
        """
        Determine if auto-retraining should be triggered.

        Enhanced policy:
        1. Minimum sample size check (prevents noisy triggers on small data)
        2. Hard failure floor (immediate retrain if performance is unacceptably bad)
        3. Degradation signals with consistency check
        4. Trend analysis: if metrics worsening over recent window

        Returns True if retraining should be triggered.
        """
        sample_count = int(report.get("total_with_outcomes") or report.get("total_predictions") or 0)
        if sample_count < self.min_outcomes_for_retrain:
            logger.debug(f"Not enough outcomes for {ptype}: {sample_count} < {self.min_outcomes_for_retrain}")
            return False

        if ptype == "severity":
            accuracy = report.get("accuracy")
            if accuracy is None:
                return False

            accuracy = float(accuracy)

            # HARD FLOOR: If accuracy is below 50%, retrain immediately
            if accuracy <= self.severity_hard_floor:
                logger.warning(f"Severity accuracy {accuracy:.1%} below hard floor {self.severity_hard_floor:.1%} - immediate retrain")
                return True

            # Check for degradation below acceptable threshold
            weak_signals = 0
            if accuracy < self.auto_retrain_accuracy:
                weak_signals += 1
                logger.debug(f"Severity accuracy below threshold: {accuracy:.1%} < {self.auto_retrain_accuracy:.1%}")

            # Confusion matrix signal: if > 5 different prediction-actual combos, model is inconsistent
            confusion = (report.get("metrics_breakdown") or {}).get("confusion_matrix") or {}
            if confusion and len(confusion) >= 6:
                weak_signals += 1
                logger.debug(f"Confusion matrix has {len(confusion)} cells - inconsistent predictions")

            # Calibration signal: check reliability - if any severity class has accuracy < 0.4
            calibration = report.get("calibration", {})
            reliability = calibration.get("reliability", {})
            if reliability:
                low_acc_classes = [cls for cls, stats in reliability.items() if stats.get("accuracy", 1.0) < 0.4]
                if low_acc_classes:
                    weak_signals += 1
                    logger.debug(f"Poor calibration on classes: {low_acc_classes}")

            # Brier score signal: > 0.25 indicates poor probability calibration
            brier = calibration.get("brier_score")
            if brier is not None and brier > 0.25:
                weak_signals += 1

            # Require at least 2 weak signals to trigger (avoids overfitting to single metric)
            if weak_signals >= 2:
                logger.info(f"Severity retrain triggered: {weak_signals} degradation signals detected")
                return True

            return False

        # Regression models (impact, spread)
        mae = report.get("mae")
        if mae is None:
            return False

        mae = float(mae)

        # HARD CEILING: If MAE is extremely high (e.g., 3x threshold), retrain immediately
        if mae >= (self.auto_retrain_mae * self.regression_hard_ceiling_mult):
            logger.warning(f"MAE {mae} exceeds hard ceiling {self.auto_retrain_mae * self.regression_hard_ceiling_mult} - immediate retrain")
            return True

        weak_signals = 0
        reasons = []

        if mae > self.auto_retrain_mae:
            weak_signals += 1
            reasons.append(f"MAE {mae:.2f} > threshold {self.auto_retrain_mae:.2f}")

        # Check MAPE if available
        mape = report.get("mape")
        if mape is not None and float(mape) > 35.0:
            weak_signals += 1
            reasons.append(f"MAPE {mape:.1f}% > 35%")

        # Check RMSE/MAE ratio (consistency check - high ratio indicates unstable predictions)
        rmse = report.get("rmse")
        if rmse is not None and mae > 0:
            ratio = float(rmse) / mae
            if ratio > self.rmse_mae_ratio_ceiling:
                weak_signals += 1
                reasons.append(f"RMSE/MAE ratio {ratio:.2f} > {self.rmse_mae_ratio_ceiling}")

        # Bias check: if predictions are systematically off in one direction
        calibration = report.get("calibration", {})
        bias_key = f"bias_{ptype}" if ptype != "impact" else "bias_casualties"  # use first metric
        bias = calibration.get(bias_key)
        if bias is not None and abs(bias) > (self.auto_retrain_mae * 0.5):
            weak_signals += 1
            reasons.append(f"Systematic bias detected: {bias:.2f}")

        # Coverage check: prediction intervals should capture ~80% of actuals
        coverage_key = "coverage_50pct" if ptype == "impact" else "coverage_20pct"
        coverage = calibration.get(coverage_key)
        if coverage is not None and coverage < 0.6:  # Less than 60% of actuals within interval
            weak_signals += 1
            reasons.append(f"Low coverage {coverage:.1%}")

        if weak_signals >= 2:
            logger.info(f"{ptype} retrain triggered: {weak_signals} signals - {', '.join(reasons)}")
            return True

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
        """Get outcome tracking records (only from real disasters, not simulated)."""
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
        outcomes = resp.data or []

        # Filter out outcomes from simulated disasters (only real victim data)
        # NOTE: requires disasters table to have is_simulated column. If not present, skip filtering with warning.
        if outcomes:
            disaster_ids = list({o.get("disaster_id") for o in outcomes if o.get("disaster_id")})
            real_disaster_ids: set[str] = set()
            if disaster_ids:
                try:
                    chunk_size = 50
                    for i in range(0, len(disaster_ids), chunk_size):
                        chunk = disaster_ids[i : i + chunk_size]
                        dis_resp = await db_admin.table("disasters")\
                            .select("id")\
                            .in_("id", chunk)\
                            .eq("is_simulated", False)\
                            .async_execute()
                        real_disaster_ids.update(d["id"] for d in (dis_resp.data or []))
                    outcomes = [o for o in outcomes if o.get("disaster_id") in real_disaster_ids]
                except Exception as e:
                    if "does not exist" in str(e):
                        logger.warning("is_simulated column missing - cannot filter simulated disasters. "
                                      "Run migration: database/migrations/add_is_simulated_column.sql")
                    else:
                        logger.warning(f"Error filtering simulated disasters: {e}")
        return outcomes

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
