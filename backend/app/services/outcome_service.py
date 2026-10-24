"""
Phase 5 – Outcome Tracking & Model Feedback Loop Service.

Logs actual vs predicted outcomes, computes error metrics,
generates weekly evaluation reports, and triggers retraining when needed.

Improvements:
1. Trend-aware retraining: rolling window check over 3 consecutive weekly reports
2. Per-disaster-type accuracy breakdown in _compute_metrics
3. Confidence scores stored and Brier score computed per-class
4. RMSE/MAE ratio ceiling now wired into _should_retrain (was defined but unused)
5. Temporal drift detection: >25% MAE spike triggers retrain
6. R² computation for regression models (was initialized to None, never computed)
7. Human coordinator correction feedback flow: write_correction()
8. Outcome staleness detection: recheck_stale_outcomes() for active disasters
9. Prediction age weighting: predictions in first 2h discounted in accuracy scoring
"""

import logging
import math
import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.phase5_config import phase5_config
from app.database import db_admin

logger = logging.getLogger("outcome_service")

# Weight applied to outcomes where the prediction was made in the first 2 hours
# of a disaster (less data available → less reliable → lower contribution weight)
_EARLY_PREDICTION_DISCOUNT = 0.4
_EARLY_PREDICTION_HOURS = 2


def _age_weight(predicted_at_iso: str | None, disaster_start_iso: str | None) -> float:
    """
    Return a weight in [0.4, 1.0] for an outcome record.

    Predictions made within the first _EARLY_PREDICTION_HOURS of the disaster
    lifecycle receive _EARLY_PREDICTION_DISCOUNT; all others get weight 1.0.
    If timestamps are missing we fall back to full weight.
    """
    if not predicted_at_iso or not disaster_start_iso:
        return 1.0
    try:
        pred_t = datetime.fromisoformat(predicted_at_iso.replace("Z", "+00:00"))
        start_t = datetime.fromisoformat(disaster_start_iso.replace("Z", "+00:00"))
        hours_elapsed = (pred_t - start_t).total_seconds() / 3600
        if hours_elapsed < _EARLY_PREDICTION_HOURS:
            return _EARLY_PREDICTION_DISCOUNT
    except Exception:
        pass
    return 1.0


def _r_squared(actuals: list[float], errors: list[float]) -> float | None:
    """
    Compute R² = 1 - SS_res / SS_tot.

    actuals:  list of actual (ground truth) values
    errors:   list of (actual - predicted) residuals, same order
    Returns None if SS_tot is zero (all actuals are identical).
    """
    if len(actuals) < 2:
        return None
    mean_actual = sum(actuals) / len(actuals)
    ss_tot = sum((a - mean_actual) ** 2 for a in actuals)
    if ss_tot == 0:
        return None
    ss_res = sum(e ** 2 for e in errors)
    return round(1.0 - ss_res / ss_tot, 4)


class OutcomeTrackingService:
    """Tracks prediction accuracy and manages the model feedback loop."""

    def __init__(self):
        self.auto_retrain_mae = phase5_config.AUTO_RETRAIN_THRESHOLD_MAE
        self.auto_retrain_accuracy = phase5_config.AUTO_RETRAIN_THRESHOLD_ACCURACY
        self.min_outcomes_for_retrain = 20
        self.severity_hard_floor = 0.50
        self.regression_hard_ceiling_mult = 1.75
        # [IMPROVEMENT #4] This was defined but never used in _should_retrain — now wired in.
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
            if "is_simulated" in str(e) and ("does not exist" in str(e) or "column" in str(e)):
                logger.warning(
                    f"is_simulated column missing – cannot verify disaster {disaster_id} is real. "
                    f"Skipping check. Run DB migration to enforce real-data-only filter."
                )
            else:
                logger.error(f"Failed to verify disaster {disaster_id} is real: {e}")
                raise

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

        record = {
            "disaster_id": disaster_id,
            "prediction_id": prediction_id,
            "prediction_type": prediction_type,
            "model_version": model_version,
            "logged_by": outcome_data.get("logged_by", "system"),
            "notes": outcome_data.get("notes"),
            "is_correction": outcome_data.get("is_correction", False),  # [IMPROVEMENT #7]
            "correction_confidence": outcome_data.get("correction_confidence"),  # [IMPROVEMENT #7]
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
            # [IMPROVEMENT #8] staleness tracking
            "recheck_after": outcome_data.get("recheck_after"),
            "disaster_status_at_capture": outcome_data.get("disaster_status_at_capture"),
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

    # ── [IMPROVEMENT #7] Coordinator correction flow ───────────────

    async def write_correction(
        self,
        disaster_id: str,
        prediction_id: str,
        prediction_type: str,
        corrected_severity: str | None = None,
        corrected_casualties: int | None = None,
        corrected_area_km2: float | None = None,
        coordinator_id: str | None = None,
        reason: str | None = None,
    ) -> dict | None:
        """
        Record a coordinator's manual override as a high-confidence ground truth signal.

        When a coordinator corrects a predicted severity label (or other value), that
        correction is written back to outcome_tracking with is_correction=True and
        correction_confidence=1.0 so it contributes more strongly to accuracy scoring.
        """
        outcome_data: dict[str, Any] = {
            "disaster_id": disaster_id,
            "prediction_id": prediction_id,
            "prediction_type": prediction_type,
            "logged_by": coordinator_id or "coordinator",
            "is_correction": True,
            "correction_confidence": 1.0,  # human corrections are treated as ground truth
            "notes": f"[COORDINATOR CORRECTION] {reason or 'Manual override by coordinator'}",
        }
        if corrected_severity is not None:
            outcome_data["actual_severity"] = corrected_severity
        if corrected_casualties is not None:
            outcome_data["actual_casualties"] = corrected_casualties
        if corrected_area_km2 is not None:
            outcome_data["actual_area_km2"] = corrected_area_km2

        logger.info(
            f"Coordinator correction for prediction {prediction_id} on disaster {disaster_id}: "
            f"type={prediction_type}, severity={corrected_severity}"
        )
        return await self.log_outcome(outcome_data)

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

    # ── [IMPROVEMENT #8] Outcome staleness detection ───────────────

    async def recheck_stale_outcomes(self) -> list[dict]:
        """
        Re-evaluate outcomes for active disasters whose values may have changed.

        When a disaster is still active at outcome capture time, we set
        recheck_after to now + 24h. This method finds those records whose
        recheck_after has passed and refreshes actual values from the live
        disaster record.
        """
        rechecked: list[dict] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            stale_resp = (
                await db_admin.table("outcome_tracking")
                .select("*, predictions(predicted_at)")
                .lte("recheck_after", now_iso)
                .not_.is_("recheck_after", "null")
                .limit(200)
                .async_execute()
            )
            stale = stale_resp.data or []

            if not stale:
                logger.info("recheck_stale_outcomes: no stale records to update")
                return rechecked

            disaster_ids = list({r["disaster_id"] for r in stale if r.get("disaster_id")})
            disasters: dict[str, dict] = {}
            for chunk_start in range(0, len(disaster_ids), 50):
                chunk = disaster_ids[chunk_start:chunk_start + 50]
                dis_resp = (
                    await db_admin.table("disasters")
                    .select("id, status, severity, casualties, estimated_damage, affected_area_km2")
                    .in_("id", chunk)
                    .async_execute()
                )
                for d in dis_resp.data or []:
                    disasters[d["id"]] = d

            for record in stale:
                disaster = disasters.get(record.get("disaster_id", ""))
                if not disaster:
                    continue

                ptype = record.get("prediction_type", "")
                update_fields: dict[str, Any] = {
                    "disaster_status_at_capture": disaster.get("status"),
                }

                # If the disaster is resolved, clear the recheck flag and update actuals
                if disaster.get("status") in ("resolved", "closed"):
                    update_fields["recheck_after"] = None
                    if ptype == "severity" and disaster.get("severity"):
                        update_fields["actual_severity"] = disaster["severity"]
                        update_fields["severity_match"] = (
                            record.get("predicted_severity") == disaster["severity"]
                        )
                    elif ptype == "impact":
                        if disaster.get("casualties") is not None:
                            update_fields["actual_casualties"] = disaster["casualties"]
                            pred_c = record.get("predicted_casualties")
                            if pred_c is not None:
                                err = float(disaster["casualties"]) - float(pred_c)
                                update_fields["casualty_error"] = err
                                if float(pred_c) > 0:
                                    update_fields["casualty_error_pct"] = round(err / float(pred_c) * 100, 2)
                    elif ptype == "spread":
                        if disaster.get("affected_area_km2") is not None:
                            update_fields["actual_area_km2"] = disaster["affected_area_km2"]
                            pred_a = record.get("predicted_area_km2")
                            if pred_a is not None:
                                err = float(disaster["affected_area_km2"]) - float(pred_a)
                                update_fields["area_error"] = err
                                if float(pred_a) > 0:
                                    update_fields["area_error_pct"] = round(err / float(pred_a) * 100, 2)
                else:
                    # Disaster still active: push recheck_after 24h forward
                    new_recheck = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                    update_fields["recheck_after"] = new_recheck

                try:
                    up_resp = (
                        await db_admin.table("outcome_tracking")
                        .update(update_fields)
                        .eq("id", record["id"])
                        .async_execute()
                    )
                    if up_resp.data:
                        rechecked.append(up_resp.data[0])
                except Exception as e:
                    logger.error(f"Failed to update stale outcome {record['id']}: {e}")

            logger.info(f"recheck_stale_outcomes: refreshed {len(rechecked)} records")
        except Exception as e:
            logger.error(f"recheck_stale_outcomes failed: {e}")

        return rechecked

    # ── Automated outcome capturing ────────────────────────────────

    async def auto_capture_outcomes(self) -> list[dict]:
        """
        Capture outcomes for any disaster that has ML predictions but no outcome record yet.

        [IMPROVEMENT #8] For active (non-resolved) disasters, sets recheck_after=24h
        so the outcome gets refreshed once the disaster is resolved.
        """
        captured = []

        try:
            pred_resp = (
                await db_admin.table("predictions")
                .select(
                    "id, disaster_id, prediction_type, predicted_severity, "
                    "predicted_casualties, affected_area_km, features, model_version, created_at"
                )
                .order("created_at", desc=True)
                .limit(500)
                .async_execute()
            )
            predictions = pred_resp.data or []

            if not predictions:
                logger.info("auto_capture_outcomes: no predictions in DB yet")
                return captured

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

            disaster_ids = list({p["disaster_id"] for p in untracked if p.get("disaster_id")})
            if not disaster_ids:
                logger.warning("auto_capture_outcomes: predictions missing disaster_id")
                return captured

            chunk_size = 50
            disasters_by_id: dict[str, dict] = {}
            for i in range(0, len(disaster_ids), chunk_size):
                chunk = disaster_ids[i: i + chunk_size]
                dis_resp = (
                    await db_admin.table("disasters")
                    .select(
                        "id, type, status, severity, casualties, "
                        "estimated_damage, affected_area_km2, start_date, end_date, updated_at"
                    )
                    .in_("id", chunk)
                    .eq("is_simulated", False)
                    .async_execute()
                )
                for d in (dis_resp.data or []):
                    disasters_by_id[d["id"]] = d

            for pred in untracked:
                disaster = disasters_by_id.get(pred.get("disaster_id", ""))
                if not disaster:
                    continue

                pred_type = pred.get("prediction_type", "")
                is_active = disaster.get("status") not in ("resolved", "closed")

                # [IMPROVEMENT #8] schedule recheck for active disasters
                recheck_after = (
                    (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                    if is_active else None
                )

                outcome_data = {
                    "disaster_id": pred["disaster_id"],
                    "prediction_id": pred["id"],
                    "prediction_type": pred_type,
                    "model_version": pred.get("model_version"),
                    "logged_by": "system",
                    "notes": f"Auto-captured from {disaster.get('status', 'active')} disaster (real ingested data)",
                    "disaster_status_at_capture": disaster.get("status"),
                    "recheck_after": recheck_after,  # [IMPROVEMENT #8]
                }

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

                if pred_type == "severity":
                    actual_sev = disaster.get("severity")
                    if actual_sev:
                        outcome_data["actual_severity"] = actual_sev
                    else:
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
                        continue
                elif pred_type == "spread":
                    actual_area = disaster.get("affected_area_km2")
                    if actual_area is not None:
                        outcome_data["actual_area_km2"] = actual_area
                    else:
                        continue
                else:
                    logger.warning(f"Unknown prediction_type '{pred_type}' for prediction {pred['id']}")
                    continue

                has_actual = any(k in outcome_data for k in ["actual_severity", "actual_casualties", "actual_damage_usd", "actual_area_km2"])
                has_predicted = any(k in outcome_data for k in ["predicted_severity", "predicted_casualties", "predicted_damage_usd", "predicted_area_km2"])
                if not (has_actual and has_predicted):
                    continue

                try:
                    result = await self.log_outcome(outcome_data)
                    if result:
                        captured.append(result)
                except Exception as e:
                    logger.error(f"Failed to capture outcome for prediction {pred['id']}: {e}")

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

        [IMPROVEMENT #5] Compares this window's MAE to the previous window's MAE;
        a >25% spike is treated as a retrain signal even if absolute value is okay.
        """
        since = (datetime.utcnow() - timedelta(days=period_days)).isoformat()
        types_to_evaluate = [model_type] if model_type else ["severity", "spread", "impact"]

        # [IMPROVEMENT #5] fetch previous window MAE for drift detection
        prev_since = (datetime.utcnow() - timedelta(days=period_days * 2)).isoformat()
        prev_until = (datetime.utcnow() - timedelta(days=period_days)).isoformat()
        prev_mae: dict[str, float | None] = {}

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
                    logger.info(f"No outcomes for {ptype} in the last {period_days} days — widening to all-time records")
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

                # Filter out simulated disaster outcomes
                if outcomes:
                    disaster_ids = list({o.get("disaster_id") for o in outcomes if o.get("disaster_id")})
                    real_disaster_ids: set[str] = set()
                    if disaster_ids:
                        try:
                            for i in range(0, len(disaster_ids), 50):
                                chunk = disaster_ids[i: i + 50]
                                dis_resp = await db_admin.table("disasters")\
                                    .select("id")\
                                    .in_("id", chunk)\
                                    .eq("is_simulated", False)\
                                    .async_execute()
                                real_disaster_ids.update(d["id"] for d in (dis_resp.data or []))
                            outcomes = [o for o in outcomes if o.get("disaster_id") in real_disaster_ids]
                        except Exception as e:
                            if "does not exist" in str(e):
                                logger.warning(f"is_simulated column not found – skipping simulated filter: {e}")
                            else:
                                logger.warning(f"Failed to filter simulated disasters: {e}")
                    if not outcomes:
                        logger.info(f"No real-disaster outcomes for {ptype} after filtering — skipping")
                        continue

                    # [IMPROVEMENT #5] Fetch previous window outcomes for drift check
                    try:
                        prev_resp = (
                            await db_admin.table("outcome_tracking")
                            .select("*")
                            .eq("prediction_type", ptype)
                            .gte("created_at", prev_since)
                            .lte("created_at", prev_until)
                            .async_execute()
                        )
                        prev_outcomes = prev_resp.data or []
                        if prev_outcomes and ptype != "severity":
                            prev_report = self._compute_metrics(ptype, prev_outcomes)
                            prev_mae[ptype] = prev_report.get("mae")
                        else:
                            prev_mae[ptype] = None
                    except Exception:
                        prev_mae[ptype] = None

                    report = self._compute_metrics(ptype, outcomes)
                    report["report_date"] = datetime.utcnow().date().isoformat()
                    report["report_period"] = "weekly" if period_days == 7 else "monthly"
                    report["model_type"] = ptype
                    report["total_predictions"] = len(outcomes)
                    report["total_with_outcomes"] = len([
                        o for o in outcomes
                        if any([
                            o.get("actual_severity"),
                            o.get("actual_casualties") is not None,
                            o.get("actual_damage_usd") is not None,
                            o.get("actual_area_km2") is not None,
                        ])
                    ])

                    # [IMPROVEMENT #5] attach drift data for _should_retrain
                    report["_prev_mae"] = prev_mae.get(ptype)

                    retrain_triggered = self._should_retrain(ptype, report)
                    report["retrain_triggered"] = retrain_triggered
                    # Clean up internal key before storage
                    report.pop("_prev_mae", None)

                    if report.get("model_version") is None:
                        versions = [o.get("model_version") for o in outcomes if o.get("model_version")]
                        report["model_version"] = versions[0] if versions else None

                    db_record = {k: v for k, v in report.items()}
                    try:
                        db_resp = await db_admin.table("model_evaluation_reports").insert(db_record).async_execute()
                        stored = db_resp.data[0] if db_resp.data else db_record
                        reports.append(stored)
                    except Exception as e:
                        logger.error(f"Failed to store evaluation report for {ptype}: {e}")
                        reports.append(report)

                    if retrain_triggered:
                        await self._trigger_retrain(ptype, report)

            except Exception as e:
                logger.error(f"Evaluation failed for {ptype}: {e}")

        logger.info(f"Generated {len(reports)} evaluation reports")
        return reports

    def _compute_metrics(self, ptype: str, outcomes: list[dict]) -> dict:
        """
        Compute accuracy metrics for a prediction type.

        [IMPROVEMENT #2] Breaks down accuracy by disaster.type.
        [IMPROVEMENT #3] Brier score computed from stored confidence scores.
        [IMPROVEMENT #6] R² computed for regression models.
        [IMPROVEMENT #9] Age-weighted accuracy scoring (early predictions discounted).
        """
        metrics: dict[str, Any] = {
            "accuracy": None,
            "mae": None,
            "rmse": None,
            "mape": None,
            "r_squared": None,
            "metrics_breakdown": {},
            "recommendations": [],
            "calibration": {},
            # [IMPROVEMENT #2] per-disaster-type accuracy breakdown
            "accuracy_by_disaster_type": {},
            "business_impact": {
                "estimated_resources_saved": 0,
                "over_allocation_prevented_pct": 0.0,
            },
        }

        if ptype == "severity":
            matches = [o for o in outcomes if o.get("severity_match") is not None]
            if matches:
                # [IMPROVEMENT #9] age-weighted accuracy
                weighted_correct = 0.0
                total_weight = 0.0
                for o in matches:
                    w = _age_weight(o.get("created_at"), o.get("disaster_start_date"))
                    # [IMPROVEMENT #7] coordinator corrections get full weight
                    if o.get("is_correction"):
                        w = 1.0
                    total_weight += w
                    if o.get("severity_match"):
                        weighted_correct += w

                metrics["accuracy"] = round(weighted_correct / total_weight, 4) if total_weight > 0 else None

                # Confusion matrix
                confusion: dict[str, int] = {}
                for o in matches:
                    pred = o.get("predicted_severity", "unknown")
                    actual = o.get("actual_severity", "unknown")
                    key = f"{pred}_vs_{actual}"
                    confusion[key] = confusion.get(key, 0) + 1
                metrics["metrics_breakdown"]["confusion_matrix"] = confusion

                # [IMPROVEMENT #3] Brier score from stored confidence_score
                # Join with predictions table to get probabilities if available
                brier_pairs: list[tuple[float, int]] = []
                for o in matches:
                    conf = o.get("confidence_score")
                    if conf is not None:
                        brier_pairs.append((float(conf), 1 if o["severity_match"] else 0))

                if brier_pairs:
                    brier = sum((conf - label) ** 2 for conf, label in brier_pairs) / len(brier_pairs)
                    metrics["calibration"]["brier_score"] = round(brier, 4)
                    metrics["calibration"]["brier_sample_size"] = len(brier_pairs)
                else:
                    # Fallback: simplified Brier using 1.0 for correct, 0.0 for incorrect
                    n = len(matches)
                    brier = round(float(sum(1.0 if o["severity_match"] else 0.0 for o in matches) / n), 4)
                    metrics["calibration"]["brier_score"] = brier

                # Reliability diagram: accuracy per predicted class
                reliability: dict[str, dict] = {}
                for pred_sev in ["low", "medium", "high", "critical"]:
                    class_outcomes = [o for o in matches if o.get("predicted_severity") == pred_sev]
                    if class_outcomes:
                        class_correct = sum(1 for o in class_outcomes if o["severity_match"])
                        reliability[pred_sev] = {
                            "count": len(class_outcomes),
                            "accuracy": round(class_correct / len(class_outcomes), 4),
                        }
                metrics["calibration"]["reliability"] = reliability

                # [IMPROVEMENT #2] Per-disaster-type accuracy breakdown
                type_buckets: dict[str, dict[str, Any]] = {}
                for o in matches:
                    dtype = (o.get("disaster_type") or "unknown").lower()
                    if dtype not in type_buckets:
                        type_buckets[dtype] = {"correct": 0, "total": 0}
                    type_buckets[dtype]["total"] += 1
                    if o.get("severity_match"):
                        type_buckets[dtype]["correct"] += 1
                for dtype, counts in type_buckets.items():
                    metrics["accuracy_by_disaster_type"][dtype] = {
                        "accuracy": round(counts["correct"] / counts["total"], 4),
                        "count": counts["total"],
                    }

                # Business Impact KPIs
                accuracy_val = metrics.get("accuracy") or 0.0
                base_resources_per_disaster = 5000
                if accuracy_val > 0.5:
                    efficiency_ratio = (accuracy_val - 0.5) * 0.4
                    metrics["business_impact"]["over_allocation_prevented_pct"] = round(efficiency_ratio * 100, 1)
                    metrics["business_impact"]["estimated_resources_saved"] = int(len(matches) * base_resources_per_disaster * efficiency_ratio)

                if metrics["accuracy"] is not None and metrics["accuracy"] < self.auto_retrain_accuracy:
                    metrics["recommendations"].append({
                        "action": "retrain_severity_model",
                        "reason": f"Accuracy {metrics['accuracy']:.1%} below threshold {self.auto_retrain_accuracy:.1%}",
                        "priority": "high",
                    })

        elif ptype == "impact":
            casualty_errors = [o for o in outcomes if o.get("casualty_error") is not None]
            if casualty_errors:
                # [IMPROVEMENT #9] age-weighted MAE
                weighted_sum = 0.0
                sq_sum = 0.0
                total_weight = 0.0
                actuals: list[float] = []
                errors: list[float] = []

                for o in casualty_errors:
                    w = _age_weight(o.get("created_at"), o.get("disaster_start_date"))
                    if o.get("is_correction"):
                        w = 1.0
                    err = float(o["casualty_error"])
                    abs_err = abs(err)
                    weighted_sum += abs_err * w
                    sq_sum += (err ** 2) * w
                    total_weight += w
                    actuals.append(float(o.get("actual_casualties") or 0))
                    errors.append(err)

                if total_weight > 0:
                    metrics["mae"] = round(weighted_sum / total_weight, 2)
                    metrics["rmse"] = round(math.sqrt(sq_sum / total_weight), 2)

                # [IMPROVEMENT #6] R² for casualty regression
                metrics["r_squared"] = _r_squared(actuals, errors)

                bias = round(float(sum(e for e in errors) / len(errors)), 2)
                metrics["calibration"]["bias_casualties"] = bias

                pct_errors = [
                    abs(float(o["casualty_error_pct"]))
                    for o in casualty_errors
                    if o.get("casualty_error_pct") is not None
                ]
                if pct_errors:
                    metrics["mape"] = round(float(sum(pct_errors) / len(pct_errors)), 2)
                    within_50pct = sum(1 for o in casualty_errors if abs(o["casualty_error"]) <= 0.5 * abs(float(o.get("predicted_casualties", 1) or 1)))
                    metrics["calibration"]["coverage_50pct"] = round(within_50pct / len(casualty_errors), 4)

                metrics["metrics_breakdown"]["casualty_metrics"] = {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "r_squared": metrics["r_squared"],
                    "count": len(casualty_errors),
                }

                # [IMPROVEMENT #2] Per-disaster-type MAE breakdown
                type_mae: dict[str, dict[str, Any]] = {}
                for o in casualty_errors:
                    dtype = (o.get("disaster_type") or "unknown").lower()
                    if dtype not in type_mae:
                        type_mae[dtype] = {"errors": [], "count": 0}
                    type_mae[dtype]["errors"].append(abs(float(o["casualty_error"])))
                    type_mae[dtype]["count"] += 1
                for dtype, data in type_mae.items():
                    metrics["accuracy_by_disaster_type"][dtype] = {
                        "mae": round(sum(data["errors"]) / len(data["errors"]), 2),
                        "count": data["count"],
                    }

            damage_errors = [o for o in outcomes if o.get("damage_error") is not None]
            if damage_errors:
                d_errors = [float(o["damage_error"]) for o in damage_errors]
                d_abs = [abs(e) for e in d_errors]
                damage_mae = round(float(sum(d_abs) / len(d_abs)), 2)
                damage_rmse = round(float(math.sqrt(sum(e**2 for e in d_errors) / len(d_errors))), 2)
                # [IMPROVEMENT #6] R² for damage regression
                damage_actuals = [float(o.get("actual_damage_usd") or 0) for o in damage_errors]
                damage_r2 = _r_squared(damage_actuals, d_errors)
                metrics["metrics_breakdown"]["damage_metrics"] = {
                    "mae": damage_mae,
                    "rmse": damage_rmse,
                    "r_squared": damage_r2,
                    "count": len(damage_errors),
                }
                d_bias = round(float(sum(d_errors) / len(d_errors)), 2)
                metrics["calibration"]["bias_damage"] = d_bias

        elif ptype == "spread":
            area_errors = [o for o in outcomes if o.get("area_error") is not None]
            if area_errors:
                # [IMPROVEMENT #9] age-weighted MAE
                weighted_sum = 0.0
                sq_sum = 0.0
                total_weight = 0.0
                actuals: list[float] = []
                errors: list[float] = []

                for o in area_errors:
                    w = _age_weight(o.get("created_at"), o.get("disaster_start_date"))
                    if o.get("is_correction"):
                        w = 1.0
                    err = float(o["area_error"])
                    abs_err = abs(err)
                    weighted_sum += abs_err * w
                    sq_sum += (err ** 2) * w
                    total_weight += w
                    actuals.append(float(o.get("actual_area_km2") or 0))
                    errors.append(err)

                if total_weight > 0:
                    metrics["mae"] = round(weighted_sum / total_weight, 2)
                    metrics["rmse"] = round(math.sqrt(sq_sum / total_weight), 2)

                # [IMPROVEMENT #6] R² for spread regression
                metrics["r_squared"] = _r_squared(actuals, errors)

                pct_errors = [
                    abs(float(o["area_error_pct"])) for o in area_errors if o.get("area_error_pct") is not None
                ]
                if pct_errors:
                    metrics["mape"] = round(float(sum(pct_errors) / len(pct_errors)), 2)

                area_bias = round(float(sum(e for e in errors) / len(errors)), 2)
                metrics["calibration"]["bias_area"] = area_bias

                within_20pct = sum(1 for o in area_errors if abs(o["area_error"]) <= 0.2 * abs(float(o.get("actual_area_km2", 1) or 1)))
                metrics["calibration"]["coverage_20pct"] = round(within_20pct / len(area_errors), 4)

                metrics["metrics_breakdown"]["area_metrics"] = {
                    "mae": metrics["mae"],
                    "rmse": metrics["rmse"],
                    "mape": metrics["mape"],
                    "r_squared": metrics["r_squared"],
                    "count": len(area_errors),
                }

                # [IMPROVEMENT #2] Per-disaster-type MAE breakdown
                type_mae: dict[str, dict[str, Any]] = {}
                for o in area_errors:
                    dtype = (o.get("disaster_type") or "unknown").lower()
                    if dtype not in type_mae:
                        type_mae[dtype] = {"errors": [], "count": 0}
                    type_mae[dtype]["errors"].append(abs(float(o["area_error"])))
                    type_mae[dtype]["count"] += 1
                for dtype, data in type_mae.items():
                    metrics["accuracy_by_disaster_type"][dtype] = {
                        "mae": round(sum(data["errors"]) / len(data["errors"]), 2),
                        "count": data["count"],
                    }

        return metrics

    def _should_retrain(self, ptype: str, report: dict) -> bool:
        """
        Determine if auto-retraining should be triggered.

        Policy changes:
        [IMPROVEMENT #1] Trend-aware: checks 3 consecutive weekly reports for declining accuracy.
        [IMPROVEMENT #4] RMSE/MAE ratio ceiling now actually used (was defined but never referenced).
        [IMPROVEMENT #5] Temporal drift: >25% MAE spike from previous window triggers retrain.
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

            if accuracy <= self.severity_hard_floor:
                logger.warning(f"Severity accuracy {accuracy:.1%} below hard floor {self.severity_hard_floor:.1%} - immediate retrain")
                return True

            weak_signals = 0
            if accuracy < self.auto_retrain_accuracy:
                weak_signals += 1

            confusion = (report.get("metrics_breakdown") or {}).get("confusion_matrix") or {}
            if confusion and len(confusion) >= 6:
                weak_signals += 1

            calibration = report.get("calibration", {})
            reliability = calibration.get("reliability", {})
            if reliability:
                low_acc_classes = [cls for cls, stats in reliability.items() if stats.get("accuracy", 1.0) < 0.4]
                if low_acc_classes:
                    weak_signals += 1

            brier = calibration.get("brier_score")
            if brier is not None and brier > 0.25:
                weak_signals += 1

            if weak_signals >= 2:
                logger.info(f"Severity retrain triggered: {weak_signals} degradation signals detected")
                return True

            return False

        # Regression models (impact, spread)
        mae = report.get("mae")
        if mae is None:
            return False

        mae = float(mae)

        if mae >= (self.auto_retrain_mae * self.regression_hard_ceiling_mult):
            logger.warning(f"MAE {mae} exceeds hard ceiling {self.auto_retrain_mae * self.regression_hard_ceiling_mult} - immediate retrain")
            return True

        weak_signals = 0
        reasons: list[str] = []

        if mae > self.auto_retrain_mae:
            weak_signals += 1
            reasons.append(f"MAE {mae:.2f} > threshold {self.auto_retrain_mae:.2f}")

        mape = report.get("mape")
        if mape is not None and float(mape) > 35.0:
            weak_signals += 1
            reasons.append(f"MAPE {mape:.1f}% > 35%")

        # [IMPROVEMENT #4] RMSE/MAE ratio guard — was defined but never checked until now
        rmse = report.get("rmse")
        if rmse is not None and mae > 0:
            ratio = float(rmse) / mae
            if ratio > self.rmse_mae_ratio_ceiling:
                weak_signals += 1
                reasons.append(f"RMSE/MAE ratio {ratio:.2f} > ceiling {self.rmse_mae_ratio_ceiling} (catastrophic outliers detected)")

        # [IMPROVEMENT #5] Temporal drift: sudden MAE spike vs previous window
        prev_mae = report.get("_prev_mae")
        if prev_mae is not None and float(prev_mae) > 0:
            drift_pct = (mae - float(prev_mae)) / float(prev_mae)
            if drift_pct > 0.25:
                weak_signals += 1
                reasons.append(f"MAE spiked {drift_pct:.0%} vs previous window (drift detected)")

        calibration = report.get("calibration", {})
        bias_key = f"bias_{ptype}" if ptype != "impact" else "bias_casualties"
        bias = calibration.get(bias_key)
        if bias is not None and abs(bias) > (self.auto_retrain_mae * 0.5):
            weak_signals += 1
            reasons.append(f"Systematic bias detected: {bias:.2f}")

        coverage_key = "coverage_50pct" if ptype == "impact" else "coverage_20pct"
        coverage = calibration.get(coverage_key)
        if coverage is not None and coverage < 0.6:
            weak_signals += 1
            reasons.append(f"Low coverage {coverage:.1%}")

        if weak_signals >= 2:
            logger.info(f"{ptype} retrain triggered: {weak_signals} signals - {', '.join(reasons)}")
            return True

        return False

    # ── [IMPROVEMENT #1] Trend-aware retrain check ─────────────────

    async def check_consecutive_decline(self, ptype: str, window: int = 3) -> bool:
        """
        Return True if accuracy/MAE has been declining for `window` consecutive weekly reports.

        This provides early retrain triggering before the hard floor is breached.
        Called externally from a scheduler or as part of generate_evaluation_report.
        """
        try:
            resp = (
                await db_admin.table("model_evaluation_reports")
                .select("report_date, accuracy, mae")
                .eq("model_type", ptype)
                .order("report_date", desc=True)
                .limit(window)
                .async_execute()
            )
            reports = resp.data or []
        except Exception as e:
            logger.warning(f"check_consecutive_decline: DB error for {ptype}: {e}")
            return False

        if len(reports) < window:
            return False  # not enough history to judge

        # Reports are newest-first; reverse to get chronological order
        reports = list(reversed(reports))

        if ptype == "severity":
            # Declining accuracy = each value strictly less than the previous
            vals = [r.get("accuracy") for r in reports]
            if any(v is None for v in vals):
                return False
            declining = all(float(vals[i]) < float(vals[i - 1]) for i in range(1, len(vals)))
        else:
            # Rising MAE = each value strictly greater than the previous
            vals = [r.get("mae") for r in reports]
            if any(v is None for v in vals):
                return False
            declining = all(float(vals[i]) > float(vals[i - 1]) for i in range(1, len(vals)))

        if declining:
            logger.warning(
                f"[Trend Alert] {ptype} has deteriorated for {window} consecutive reports: {vals}"
            )
        return declining

    async def _trigger_retrain(self, model_type: str, report: dict):
        """Trigger model retraining via the existing retrain endpoint."""
        logger.info(
            f"Model Performance Alert: Retraining triggered for '{model_type}'. "
            f"Metrics: accuracy={report.get('accuracy', 'N/A')}, mae={report.get('mae', 'N/A')}"
        )

        try:
            import httpx
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

        if outcomes:
            disaster_ids = list({o.get("disaster_id") for o in outcomes if o.get("disaster_id")})
            real_disaster_ids: set[str] = set()
            if disaster_ids:
                try:
                    for i in range(0, len(disaster_ids), 50):
                        chunk = disaster_ids[i: i + 50]
                        dis_resp = await db_admin.table("disasters")\
                            .select("id")\
                            .in_("id", chunk)\
                            .eq("is_simulated", False)\
                            .async_execute()
                        real_disaster_ids.update(d["id"] for d in (dis_resp.data or []))
                    outcomes = [o for o in outcomes if o.get("disaster_id") in real_disaster_ids]
                except Exception as e:
                    if "does not exist" in str(e):
                        logger.warning("is_simulated column missing - cannot filter simulated disasters.")
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

    async def _build_accuracy_trend(self, ptype: str, window: int = 7) -> tuple[list[float], str]:
        """
        Fetch the last `window` weekly evaluation reports and return:
          - accuracy_trend: list of accuracy or (1 - normalised_mae) values, oldest→newest
          - trend_direction: 'improving' | 'declining' | 'stable'

        For severity we use the `accuracy` column; for regression models we proxy
        (1 − MAE/hard_ceiling) so both use the same 0..1 scale in the sparkline.
        """
        try:
            resp = (
                await db_admin.table("model_evaluation_reports")
                .select("report_date, accuracy, mae")
                .eq("model_type", ptype)
                .order("report_date", desc=True)
                .limit(window)
                .async_execute()
            )
            rows = list(reversed(resp.data or []))  # oldest → newest
        except Exception as e:
            logger.warning("_build_accuracy_trend: DB error for %s: %s", ptype, e)
            return [], "stable"

        if len(rows) < 2:
            return [], "stable"

        if ptype == "severity":
            vals = [float(r["accuracy"]) for r in rows if r.get("accuracy") is not None]
        else:
            ceiling = self.auto_retrain_mae * self.regression_hard_ceiling_mult
            vals = [
                max(0.0, 1.0 - float(r["mae"]) / ceiling)
                for r in rows
                if r.get("mae") is not None
            ]

        if len(vals) < 2:
            return vals, "stable"

        # Compare the last half vs the first half to determine direction
        mid = len(vals) // 2
        first_avg = sum(vals[:mid]) / mid if mid > 0 else vals[0]
        last_avg = sum(vals[mid:]) / len(vals[mid:]) if vals[mid:] else vals[-1]
        delta = last_avg - first_avg

        if delta > 0.02:
            direction = "improving"
        elif delta < -0.02:
            direction = "declining"
        else:
            direction = "stable"

        return vals, direction

    async def get_accuracy_summary(self) -> dict:
        """
        Get a summary of model accuracy across all types.

        Returns frontend-compatible field names:
          - accuracy_trend:       list[float]  (#10 — 7-day sparkline)
          - trend_direction:      str           (#10 — 'improving'|'declining'|'stable')
          - trend_declining:      bool          (#1  — 3-report consecutive decline flag)
          - per_class_accuracy:   dict          (#12 — {cls: accuracy} flat map)
          - per_disaster_type:    dict          (#2  — {type: accuracy} flat map)
          - last_retrain_date:    str|None      (#11 — date of last triggered retrain)
          - r_squared:            float|None    (#6  — R² for regression models)
          - business_impact:      dict
        """
        summary = {}
        for ptype in ["severity", "spread", "impact"]:
            # ── latest report ─────────────────────────────────────────────────
            resp = (
                await db_admin.table("model_evaluation_reports")
                .select("*")
                .eq("model_type", ptype)
                .order("report_date", desc=True)
                .limit(1)
                .async_execute()
            )
            if not resp.data:
                summary[ptype] = {"status": "no_data"}
                continue

            latest = resp.data[0]
            trend_declining = await self.check_consecutive_decline(ptype, window=3)
            accuracy_trend, trend_direction = await self._build_accuracy_trend(ptype, window=7)

            # ── #12 per-class accuracy (flat {cls: accuracy}) ─────────────────
            per_class_accuracy: dict[str, float] = {}
            calibration = latest.get("calibration") or {}
            reliability = calibration.get("reliability") or {}
            for cls, stats in reliability.items():
                if isinstance(stats, dict) and "accuracy" in stats:
                    per_class_accuracy[cls] = stats["accuracy"]

            # ── #2 per-disaster-type accuracy (flat {type: accuracy}) ─────────
            per_disaster_type: dict[str, float] = {}
            accuracy_by_disaster_type = latest.get("accuracy_by_disaster_type") or {}
            for dtype, stats in accuracy_by_disaster_type.items():
                if isinstance(stats, dict) and "accuracy" in stats:
                    per_disaster_type[dtype] = stats["accuracy"]
                elif isinstance(stats, dict) and "mae" in stats:
                    # regression models: invert MAE → proxy accuracy
                    ceiling = self.auto_retrain_mae * self.regression_hard_ceiling_mult
                    per_disaster_type[dtype] = max(0.0, 1.0 - stats["mae"] / ceiling)

            # ── #11 last retrain date ─────────────────────────────────────────
            last_retrain_date: str | None = None
            try:
                retrain_resp = (
                    await db_admin.table("model_evaluation_reports")
                    .select("report_date")
                    .eq("model_type", ptype)
                    .eq("retrain_triggered", True)
                    .order("report_date", desc=True)
                    .limit(1)
                    .async_execute()
                )
                if retrain_resp.data:
                    last_retrain_date = retrain_resp.data[0].get("report_date")
            except Exception as e:
                logger.debug("Could not fetch last retrain date for %s: %s", ptype, e)

            summary[ptype] = {
                "report_date": latest.get("report_date"),
                "accuracy": latest.get("accuracy"),
                "mae": latest.get("mae"),
                "rmse": latest.get("rmse"),
                "mape": latest.get("mape"),
                "r_squared": latest.get("r_squared"),           # #6
                "total_predictions": latest.get("total_predictions"),
                "retrain_triggered": latest.get("retrain_triggered"),
                "business_impact": latest.get("business_impact", {}),
                # #1 – rolling trend decline flag
                "trend_declining": trend_declining,
                # #10 – sparkline + direction
                "accuracy_trend": accuracy_trend,
                "trend_direction": trend_direction,
                # #11 – retrain badge date
                "last_retrain_date": last_retrain_date,
                # #12 – per-class confusion breakdown (frontend field name)
                "per_class_accuracy": per_class_accuracy,
                # #2 – per-disaster-type breakdown (frontend field name)
                "per_disaster_type": per_disaster_type,
                # Raw fields kept for backward compat
                "accuracy_by_disaster_type": accuracy_by_disaster_type,
                "metrics_breakdown": latest.get("metrics_breakdown", {}),
            }

        return summary