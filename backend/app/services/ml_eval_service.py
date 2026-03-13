from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.database import db_admin
from app.services.outcome_service import OutcomeTrackingService

logger = logging.getLogger("ml_eval_service")
REPORT_DIR = Path(__file__).resolve().parent.parent.parent / "reports"


def _confidence_band(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def _band_expected_confidence(band: str) -> float:
    if band == "high":
        return 0.9
    if band == "medium":
        return 0.7
    return 0.4


def _build_calibration_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    severity = result.get("severity", {})
    spread = result.get("spread", {})
    impact = result.get("impact", {})

    sev_weighted_gap_num = 0.0
    sev_weighted_gap_den = 0
    sev_order_pairs: list[tuple[str, float]] = []
    for band in ("low", "medium", "high"):
        band_data = severity.get(band, {})
        count = int(band_data.get("count") or 0)
        accuracy = band_data.get("accuracy")
        if accuracy is None or count <= 0:
            continue

        expected = _band_expected_confidence(band)
        gap = abs(float(accuracy) - expected)
        band_data["expected_confidence"] = expected
        band_data["calibration_gap"] = round(gap, 4)

        sev_weighted_gap_num += gap * count
        sev_weighted_gap_den += count
        sev_order_pairs.append((band, float(accuracy)))

    def _is_monotonic_acc(pairs: list[tuple[str, float]]) -> bool | None:
        if len(pairs) < 2:
            return None
        ordered = {k: v for k, v in pairs}
        values = [ordered.get("low"), ordered.get("medium"), ordered.get("high")]
        compact = [v for v in values if v is not None]
        if len(compact) < 2:
            return None
        return all(compact[i] <= compact[i + 1] for i in range(len(compact) - 1))

    def _mae_triplet(data: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
        low = data.get("low", {}).get("mae")
        medium = data.get("medium", {}).get("mae")
        high = data.get("high", {}).get("mae")
        return (
            float(low) if low is not None else None,
            float(medium) if medium is not None else None,
            float(high) if high is not None else None,
        )

    def _is_monotonic_desc(mae_values: tuple[float | None, float | None, float | None]) -> bool | None:
        compact = [v for v in mae_values if v is not None]
        if len(compact) < 2:
            return None
        return all(compact[i] >= compact[i + 1] for i in range(len(compact) - 1))

    spread_mae = _mae_triplet(spread)
    impact_mae = _mae_triplet(impact)
    spread_monotonic = _is_monotonic_desc(spread_mae)
    impact_monotonic = _is_monotonic_desc(impact_mae)
    severity_monotonic = _is_monotonic_acc(sev_order_pairs)

    warnings: list[str] = []
    weighted_gap = (sev_weighted_gap_num / sev_weighted_gap_den) if sev_weighted_gap_den else None
    if weighted_gap is not None and weighted_gap > 0.18:
        warnings.append("Severity confidence appears miscalibrated (high weighted gap).")
    if severity_monotonic is False:
        warnings.append("Severity confidence ranking is inconsistent across low/medium/high bands.")
    if spread_monotonic is False:
        warnings.append("Spread MAE does not improve with higher confidence bands.")
    if impact_monotonic is False:
        warnings.append("Impact MAE does not improve with higher confidence bands.")

    return {
        "severity": {
            "weighted_calibration_gap": round(weighted_gap, 4) if weighted_gap is not None else None,
            "confidence_ranking_consistent": severity_monotonic,
            "evaluated_samples": sev_weighted_gap_den,
        },
        "spread": {
            "mae_by_band": {
                "low": spread_mae[0],
                "medium": spread_mae[1],
                "high": spread_mae[2],
            },
            "confidence_ranking_consistent": spread_monotonic,
        },
        "impact": {
            "mae_by_band": {
                "low": impact_mae[0],
                "medium": impact_mae[1],
                "high": impact_mae[2],
            },
            "confidence_ranking_consistent": impact_monotonic,
        },
        "status": "needs_attention" if warnings else "ok",
        "warnings": warnings,
    }


def _calc_ece_and_reliability(
    confidence_truth_pairs: list[tuple[float, int]],
    n_bins: int = 10,
) -> dict[str, Any]:
    if not confidence_truth_pairs:
        return {
            "samples": 0,
            "ece": None,
            "brier_score": None,
            "avg_confidence": None,
            "avg_accuracy": None,
            "reliability_bins": [],
        }

    pairs = [
        (max(0.0, min(1.0, float(conf))), int(label))
        for conf, label in confidence_truth_pairs
    ]
    total = len(pairs)
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]

    for conf, label in pairs:
        idx = min(int(conf * n_bins), n_bins - 1)
        bins[idx].append((conf, label))

    ece = 0.0
    rel_bins: list[dict[str, Any]] = []
    for i, bucket in enumerate(bins):
        if not bucket:
            continue
        count = len(bucket)
        avg_conf = sum(conf for conf, _ in bucket) / count
        avg_acc = sum(label for _, label in bucket) / count
        gap = abs(avg_conf - avg_acc)
        ece += (count / total) * gap

        rel_bins.append(
            {
                "bin_start": round(i / n_bins, 3),
                "bin_end": round((i + 1) / n_bins, 3),
                "count": count,
                "avg_confidence": round(avg_conf, 4),
                "avg_accuracy": round(avg_acc, 4),
                "gap": round(gap, 4),
            }
        )

    brier = sum((conf - label) ** 2 for conf, label in pairs) / total
    avg_conf = sum(conf for conf, _ in pairs) / total
    avg_acc = sum(label for _, label in pairs) / total

    return {
        "samples": total,
        "ece": round(ece, 4),
        "brier_score": round(brier, 4),
        "avg_confidence": round(avg_conf, 4),
        "avg_accuracy": round(avg_acc, 4),
        "reliability_bins": rel_bins,
    }


def _calc_confidence_error_correlation(
    confidence_error_pairs: list[tuple[float, float]],
) -> dict[str, Any]:
    if len(confidence_error_pairs) < 3:
        return {
            "samples": len(confidence_error_pairs),
            "pearson_confidence_abs_error": None,
            "interpretation": "insufficient_data",
        }

    confs = [max(0.0, min(1.0, float(c))) for c, _ in confidence_error_pairs]
    abs_errs = [abs(float(e)) for _, e in confidence_error_pairs]

    mean_conf = sum(confs) / len(confs)
    mean_err = sum(abs_errs) / len(abs_errs)

    num = sum((c - mean_conf) * (e - mean_err) for c, e in zip(confs, abs_errs, strict=False))
    den_left = math.sqrt(sum((c - mean_conf) ** 2 for c in confs))
    den_right = math.sqrt(sum((e - mean_err) ** 2 for e in abs_errs))
    if den_left <= 0 or den_right <= 0:
        corr = None
    else:
        corr = num / (den_left * den_right)

    interpretation = "insufficient_data"
    if corr is not None:
        if corr <= -0.2:
            interpretation = "good_confidence_signal"
        elif corr < 0.2:
            interpretation = "weak_confidence_signal"
        else:
            interpretation = "confidence_misaligned"

    return {
        "samples": len(confidence_error_pairs),
        "pearson_confidence_abs_error": round(corr, 4) if corr is not None else None,
        "interpretation": interpretation,
    }


async def _build_confidence_calibration(days: int) -> dict[str, Any]:
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    try:
        pred_resp = (
            await db_admin.table("predictions")
            .select("id, prediction_type, confidence_score, created_at")
            .gte("created_at", since)
            .limit(10000)
            .async_execute()
        )
        predictions = pred_resp.data or []

        out_resp = (
            await db_admin.table("outcome_tracking")
            .select(
                "prediction_id, prediction_type, severity_match, casualty_error, area_error, damage_error, created_at"
            )
            .gte("created_at", since)
            .limit(10000)
            .async_execute()
        )
        outcomes = out_resp.data or []
    except Exception as exc:
        return {
            "severity": {},
            "spread": {},
            "impact": {},
            "advanced": {},
            "data_readiness": {
                "status": "unavailable",
                "reason": str(exc),
            },
            "warning": f"confidence calibration skipped: {exc}",
        }

    pred_map = {str(p["id"]): p for p in predictions if p.get("id")}

    result: dict[str, Any] = {
        "severity": {},
        "spread": {},
        "impact": {},
    }

    severity_bins: dict[str, list[bool]] = defaultdict(list)
    spread_bins: dict[str, list[float]] = defaultdict(list)
    impact_bins: dict[str, list[float]] = defaultdict(list)
    severity_pairs: list[tuple[float, int]] = []
    spread_pairs: list[tuple[float, float]] = []
    impact_pairs: list[tuple[float, float]] = []

    for out in outcomes:
        pred_id = str(out.get("prediction_id") or "")
        if not pred_id or pred_id not in pred_map:
            continue

        pred = pred_map[pred_id]
        ptype = str(out.get("prediction_type") or pred.get("prediction_type") or "").lower()
        conf = float(pred.get("confidence_score") or 0.0)
        band = _confidence_band(conf)

        if ptype == "severity" and out.get("severity_match") is not None:
            severity_bins[band].append(bool(out.get("severity_match")))
            severity_pairs.append((conf, 1 if bool(out.get("severity_match")) else 0))
        elif ptype == "spread" and out.get("area_error") is not None:
            spread_bins[band].append(abs(float(out.get("area_error"))))
            spread_pairs.append((conf, abs(float(out.get("area_error")))))
        elif ptype == "impact":
            if out.get("casualty_error") is not None:
                impact_bins[band].append(abs(float(out.get("casualty_error"))))
                impact_pairs.append((conf, abs(float(out.get("casualty_error")))))
            elif out.get("damage_error") is not None:
                impact_bins[band].append(abs(float(out.get("damage_error"))))
                impact_pairs.append((conf, abs(float(out.get("damage_error")))))

    for band in ("low", "medium", "high"):
        sev_vals = severity_bins.get(band, [])
        result["severity"][band] = {
            "count": len(sev_vals),
            "accuracy": round(sum(1 for v in sev_vals if v) / len(sev_vals), 4) if sev_vals else None,
        }

        spr_vals = spread_bins.get(band, [])
        result["spread"][band] = {
            "count": len(spr_vals),
            "mae": round(sum(spr_vals) / len(spr_vals), 3) if spr_vals else None,
        }

        imp_vals = impact_bins.get(band, [])
        result["impact"][band] = {
            "count": len(imp_vals),
            "mae": round(sum(imp_vals) / len(imp_vals), 3) if imp_vals else None,
        }

    result["diagnostics"] = _build_calibration_diagnostics(result)
    result["advanced"] = {
        "severity": _calc_ece_and_reliability(severity_pairs),
        "spread": _calc_confidence_error_correlation(spread_pairs),
        "impact": _calc_confidence_error_correlation(impact_pairs),
    }
    matched_pairs = len(severity_pairs) + len(spread_pairs) + len(impact_pairs)

    readiness_status = "ready" if matched_pairs >= 20 else "limited"
    readiness_notes: list[str] = []
    if not predictions:
        readiness_notes.append("No predictions in lookback window.")
    if not outcomes:
        readiness_notes.append("No outcomes in lookback window.")
    if matched_pairs < 20:
        readiness_notes.append("Matched prediction/outcome pairs below recommended minimum (20).")

    result["data_readiness"] = {
        "status": readiness_status,
        "predictions": len(predictions),
        "outcomes": len(outcomes),
        "matched_pairs": matched_pairs,
        "notes": readiness_notes,
    }
    result["summary"] = {
        "predictions_considered": len(predictions),
        "outcomes_considered": len(outcomes),
        "matched_pairs": matched_pairs,
    }
    return result


async def run_ml_evaluation(days: int = 30) -> dict[str, Any]:
    service = OutcomeTrackingService()
    reports = await service.generate_evaluation_report(period_days=days)
    calibration = await _build_confidence_calibration(days=days)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "window_days": days,
        "evaluation_reports": reports,
        "confidence_calibration": calibration,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORT_DIR / f"ml_eval_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    summary["output_path"] = str(output_path)
    logger.info("ML evaluation report generated at %s", output_path)
    return summary
