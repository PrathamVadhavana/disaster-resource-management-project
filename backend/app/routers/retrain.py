"""
/api/ml  — model management & retraining endpoints (admin-only).
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_ml_service
from app.services.ml_service import MLService

logger = logging.getLogger(__name__)
router = APIRouter()

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"


# ── Schemas ───────────────────────────────────────────────────────────────


class RetrainRequest(BaseModel):
    regenerate_data: bool = False
    random_state: int = 42


class RetrainResponse(BaseModel):
    message: str
    version: str | None = None
    severity_f1: float | None = None
    spread_r2: float | None = None
    impact_metrics: dict | None = None
    promoted: bool | None = None
    promotion_reasons: list[str] | None = None


class ModelInfoResponse(BaseModel):
    version: str
    models_loaded: bool
    severity_loaded: bool
    spread_loaded: bool
    impact_loaded: bool
    metadata: dict | None = None


# ── Background training task ─────────────────────────────────────────────

_training_in_progress = False


def _capture_baseline_metrics(ml_service: MLService) -> dict[str, float | None]:
    severity_meta = ml_service.metadata.get("severity", {})
    spread_meta = ml_service.metadata.get("spread", {})
    impact_meta = ml_service.metadata.get("impact", {})
    return {
        "severity": severity_meta.get("cv_score_mean"),
        "spread": spread_meta.get("cv_r2_mean") or spread_meta.get("cv_score_mean"),
        "impact": impact_meta.get("cv_mae_mean") or impact_meta.get("cv_score_mean"),
    }


def _extract_candidate_metrics(results: dict[str, dict]) -> dict[str, float | None]:
    return {
        "severity": results.get("severity", {}).get("cv_score_mean"),
        "spread": results.get("spread", {}).get("cv_score_mean"),
        "impact": results.get("impact", {}).get("cv_score_mean"),
    }


def _should_promote_candidate(
    baseline: dict[str, float | None],
    candidate: dict[str, float | None],
) -> tuple[bool, list[str]]:
    min_acc_drop = float(os.getenv("ML_PROMOTION_MAX_ACCURACY_DROP", "0.03"))
    max_mae_increase = float(os.getenv("ML_PROMOTION_MAX_MAE_INCREASE", "0.12"))

    reasons: list[str] = []
    blocked = False

    # Higher is better: severity/spread
    for key in ("severity", "spread"):
        b = baseline.get(key)
        c = candidate.get(key)
        if b is None or c is None:
            continue
        try:
            delta = float(c) - float(b)
            if delta < -min_acc_drop:
                blocked = True
                reasons.append(
                    f"Rejected: {key} score dropped by {abs(delta):.4f} (baseline={float(b):.4f}, candidate={float(c):.4f})"
                )
        except (TypeError, ValueError):
            continue

    # Lower is better: impact MAE
    b_impact = baseline.get("impact")
    c_impact = candidate.get("impact")
    if b_impact is not None and c_impact is not None:
        try:
            mae_delta = float(c_impact) - float(b_impact)
            if mae_delta > max_mae_increase:
                blocked = True
                reasons.append(
                    f"Rejected: impact MAE increased by {mae_delta:.4f} (baseline={float(b_impact):.4f}, candidate={float(c_impact):.4f})"
                )
        except (TypeError, ValueError):
            pass

    if not reasons:
        reasons.append("Accepted: no guardrail violations detected")

    return (not blocked), reasons


def _create_models_backup() -> str | None:
    if not MODEL_DIR.exists():
        return None
    backup_root = tempfile.mkdtemp(prefix="ml_models_backup_")
    backup_path = Path(backup_root) / "models"
    shutil.copytree(MODEL_DIR, backup_path, dirs_exist_ok=True)
    return str(backup_path)


def _restore_models_backup(backup_path: str | None) -> None:
    if not backup_path:
        return
    src = Path(backup_path)
    if not src.exists():
        return
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, MODEL_DIR, dirs_exist_ok=True)


def _cleanup_models_backup(backup_path: str | None) -> None:
    if not backup_path:
        return
    root = Path(backup_path).parent
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def _run_training(
    regenerate_data: bool,
    random_state: int,
    ml_service: MLService,
):
    """Synchronous heavy-lift function executed in a background thread."""
    global _training_in_progress
    try:
        _training_in_progress = True
        logger.info("Background model retraining started")
        backup_path = _create_models_backup()
        baseline_metrics = _capture_baseline_metrics(ml_service)
        promotion_reasons: list[str] = ["Accepted: no candidate metrics available for guardrail check"]
        should_promote = True

        if regenerate_data:
            logger.info("Regenerating synthetic training data …")
            from scripts.generate_training_data import main as gen_data

            gen_data()

        # Use Supabase-based training (primary method)
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(ml_service.build_training_data_from_supabase())
            logger.info(f"Supabase-based training results: {results}")

            candidate_metrics = _extract_candidate_metrics(results)
            should_promote, promotion_reasons = _should_promote_candidate(baseline_metrics, candidate_metrics)
            logger.info("Retrain guardrail decision: promote=%s reasons=%s", should_promote, promotion_reasons)

            # If all models skipped (insufficient data), fall back to CSV-based training
            all_skipped = all(r.get("skipped") for r in results.values())
            if all_skipped:
                logger.warning("All Supabase models skipped due to insufficient data, falling back to CSV-based training")
                from app.services.training.train_all import train_all

                manifest = train_all(model_dir=MODEL_DIR)
                logger.info(f"CSV-based fallback training complete — version {manifest['version']}")

            if not should_promote:
                logger.warning("Retrain guardrail rejected candidate models; restoring previous model snapshot")
                _restore_models_backup(backup_path)
        finally:
            loop.close()

        # Hot-reload models into the running service
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(ml_service.load_models())
        finally:
            loop.close()

        logger.info("Retraining complete")
    except Exception:
        logger.exception("Retraining failed")
        _restore_models_backup(locals().get("backup_path"))
    finally:
        _cleanup_models_backup(locals().get("backup_path"))
        _training_in_progress = False


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/info", response_model=ModelInfoResponse)
async def model_info(ml_service: MLService = Depends(get_ml_service)):
    """Return current model version and metadata."""
    info = ml_service.get_model_info()
    return ModelInfoResponse(**info)


@router.get("/training-status")
async def training_status():
    """Check whether a training job is currently running."""
    return {"training_in_progress": _training_in_progress}


@router.get("/fallback-governance")
async def fallback_governance(ml_service: MLService = Depends(get_ml_service)):
    """Return fallback usage telemetry and alert state for prediction reliability monitoring."""
    return ml_service.get_fallback_governance_snapshot()


@router.post("/retrain", response_model=RetrainResponse)
async def retrain_models(
    body: RetrainRequest,
    background_tasks: BackgroundTasks,
    ml_service: MLService = Depends(get_ml_service),
):
    """
    Trigger model retraining (admin-only).

    Training runs in a background thread so the API remains responsive.
    Poll /api/ml/training-status to check progress.
    """
    if _training_in_progress:
        raise HTTPException(status_code=409, detail="Training already in progress")

    background_tasks.add_task(
        _run_training,
        regenerate_data=body.regenerate_data,
        random_state=body.random_state,
        ml_service=ml_service,
    )

    return RetrainResponse(message="Retraining started in background. Poll /api/ml/training-status for progress.")


@router.post("/retrain-sync", response_model=RetrainResponse)
async def retrain_models_sync(
    body: RetrainRequest,
    ml_service: MLService = Depends(get_ml_service),
):
    """
    Trigger model retraining synchronously (blocks until done).
    Uses Supabase-based training as primary method, falls back to CSV-based
    training if insufficient Supabase data.
    Useful for CI / scripted pipelines.
    """
    global _training_in_progress
    if _training_in_progress:
        raise HTTPException(status_code=409, detail="Training already in progress")

    try:
        _training_in_progress = True
        backup_path = _create_models_backup()
        baseline_metrics = _capture_baseline_metrics(ml_service)
        promotion_reasons: list[str] = ["Accepted: no candidate metrics available for guardrail check"]
        promoted = True

        if body.regenerate_data:
            from scripts.generate_training_data import main as gen_data

            gen_data()

        # Use Supabase-based training (primary method)
        results = await ml_service.build_training_data_from_supabase()
        candidate_metrics = _extract_candidate_metrics(results)
        promoted, promotion_reasons = _should_promote_candidate(baseline_metrics, candidate_metrics)

        # If all models skipped (insufficient data), fall back to CSV-based training
        all_skipped = all(r.get("skipped") for r in results.values())
        version = None
        if all_skipped:
            logger.warning("All Supabase models skipped due to insufficient data, falling back to CSV-based training")
            from app.services.training.train_all import train_all

            manifest = train_all(model_dir=MODEL_DIR)
            version = manifest.get("version")
        else:
            # Extract version from results
            for r in results.values():
                if r.get("version"):
                    version = r["version"]
                    break

        if not promoted:
            _restore_models_backup(backup_path)

        # Hot-reload models
        await ml_service.load_models()

        # Build response metrics
        severity_f1 = results.get("severity", {}).get("cv_score_mean")
        spread_r2 = results.get("spread", {}).get("cv_score_mean")
        impact_metrics = results.get("impact", {}).get("cv_score_mean")

        return RetrainResponse(
            message="Retraining complete" if promoted else "Retraining rejected by guardrail; previous model snapshot restored",
            version=version,
            severity_f1=severity_f1,
            spread_r2=spread_r2,
            impact_metrics={"mae": impact_metrics} if impact_metrics else None,
            promoted=promoted,
            promotion_reasons=promotion_reasons,
        )
    except Exception as e:
        logger.exception("Sync retraining failed")
        _restore_models_backup(locals().get("backup_path"))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _cleanup_models_backup(locals().get("backup_path"))
        _training_in_progress = False


# ── AI Coordinator / Intelligence Endpoints ─────────────────────────────────

from app.dependencies import require_admin


class QueryRequest(BaseModel):
    query: str


@router.get("/sitreps/latest")
async def get_latest_sitrep(admin: dict = Depends(require_admin)):
    from app.services.sitrep_service import SitrepService

    svc = SitrepService()
    return await svc.get_latest_report()


@router.get("/sitreps")
async def get_sitreps(limit: int = 20, offset: int = 0, admin: dict = Depends(require_admin)):
    from app.services.sitrep_service import SitrepService

    svc = SitrepService()
    return await svc.list_reports(limit=limit, offset=offset)


@router.post("/sitreps/generate")
async def generate_sitrep(admin: dict = Depends(require_admin)):
    from app.services.sitrep_service import SitrepService

    svc = SitrepService()
    report = await svc.generate_report(report_type="manual", generated_by=admin.get("id", "system"))
    return report


@router.post("/sitreps/generate-llm")
async def generate_sitrep_with_llm(admin: dict = Depends(require_admin)):
    """
    Generate a structured sitrep using the new LLM-based approach with data snapshot.
    
    This endpoint:
    1. Assembles structured data snapshot from Supabase
    2. Injects snapshot as system prompt context
    3. Uses LLM to narrate the data
    4. Returns structured 7-section sitrep output
    """
    from app.services.sitrep_service import SitrepService

    svc = SitrepService()
    # Generate sitrep using new LLM-based method with data snapshot
    sitrep = await svc.generate_sitrep_with_llm()
    return sitrep


@router.get("/sitreps/snapshot")
async def get_data_snapshot(admin: dict = Depends(require_admin)):
    """
    Get the current data snapshot without generating a full sitrep.
    Useful for debugging or checking current data state.
    """
    from app.services.sitrep_service import SitrepService

    svc = SitrepService()
    snapshot = await svc.assemble_data_snapshot()
    return snapshot


@router.post("/query")
async def ask_coordinator_query(req: QueryRequest, admin: dict = Depends(require_admin)):
    from app.services.nl_query_service import NLQueryService

    svc = NLQueryService()
    result = await svc.ask(req.query, user_id=admin.get("id"))
    return result


@router.get("/query-history")
async def get_query_history(admin: dict = Depends(require_admin)):
    from app.services.nl_query_service import NLQueryService

    svc = NLQueryService()
    return await svc.get_query_history(user_id=admin.get("id"))


# ── Anomaly Detection Endpoints ──────────────────────────────────────────────


@router.get("/anomalies")
async def get_anomaly_alerts(
    status: str | None = None,
    severity: str | None = None,
    limit: int = 30,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    """Get anomaly alerts with optional filters."""
    from app.services.anomaly_service import AnomalyDetectionService

    svc = AnomalyDetectionService()
    alerts = await svc.get_all_alerts(status=status, severity=severity, limit=limit, offset=offset)
    return {"alerts": alerts}


@router.post("/anomalies/run")
async def run_anomaly_detection(admin: dict = Depends(require_admin)):
    """Trigger a manual anomaly detection run."""
    from app.services.anomaly_service import AnomalyDetectionService

    svc = AnomalyDetectionService()
    results = await svc.run_detection()
    return {"message": "Anomaly detection completed", "results": results}


@router.patch("/anomalies/{alert_id}/acknowledge")
async def acknowledge_anomaly(alert_id: str, admin: dict = Depends(require_admin)):
    """Mark an anomaly alert as acknowledged."""
    from app.services.anomaly_service import AnomalyDetectionService

    svc = AnomalyDetectionService()
    result = await svc.acknowledge_alert(alert_id, user_id=admin.get("id", "system"))
    return result


@router.patch("/anomalies/{alert_id}/resolve")
async def resolve_anomaly(alert_id: str, status: str = "resolved", admin: dict = Depends(require_admin)):
    """Resolve or mark an anomaly alert as false positive."""
    from app.services.anomaly_service import AnomalyDetectionService

    svc = AnomalyDetectionService()
    result = await svc.resolve_alert(alert_id, status=status)
    return result


# ── Outcome Tracking & Accuracy Endpoints ────────────────────────────────────


@router.get("/accuracy-summary")
async def get_accuracy_summary(admin: dict = Depends(require_admin)):
    """Get model accuracy summary across all prediction types."""
    from app.services.outcome_service import OutcomeTrackingService

    svc = OutcomeTrackingService()
    return await svc.get_accuracy_summary()


@router.get("/outcomes")
async def get_outcomes(
    disaster_id: str | None = None,
    prediction_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    """Get outcome tracking records."""
    from app.services.outcome_service import OutcomeTrackingService

    svc = OutcomeTrackingService()
    return await svc.get_outcomes(
        disaster_id=disaster_id,
        prediction_type=prediction_type,
        limit=limit,
        offset=offset,
    )


@router.get("/evaluation-reports")
async def get_evaluation_reports(
    model_type: str | None = None,
    limit: int = 20,
    admin: dict = Depends(require_admin),
):
    """Get model evaluation reports."""
    from app.services.outcome_service import OutcomeTrackingService

    svc = OutcomeTrackingService()
    return await svc.get_evaluation_reports(model_type=model_type, limit=limit)


@router.post("/outcomes/auto-capture")
async def auto_capture_outcomes(admin: dict = Depends(require_admin)):
    """Auto-capture outcomes from resolved disasters."""
    from app.services.outcome_service import OutcomeTrackingService

    svc = OutcomeTrackingService()
    results = await svc.auto_capture_outcomes()
    return {"captured": len(results), "outcomes": results}


@router.post("/evaluation-reports/generate")
async def generate_evaluation_report_endpoint(admin: dict = Depends(require_admin)):
    """Generate model evaluation reports."""
    from app.services.outcome_service import OutcomeTrackingService

    svc = OutcomeTrackingService()
    reports = await svc.generate_evaluation_report()
    return {"reports": reports}


@router.post("/auto-retrain")
async def auto_retrain_trigger(admin: dict = Depends(require_admin)):
    """
    Auto-retrain trigger endpoint.

    Checks if last training was > 24h ago and triggers background training
    for TFT, NLP, and GAT models if needed.
    """
    import json
    from datetime import datetime, timedelta

    # Check if training is already in progress
    global _training_in_progress
    if _training_in_progress:
        return {"message": "Training already in progress", "triggered": False}

    # Check last training time from manifest
    manifest_path = MODEL_DIR / "manifest.json"
    last_training_time = None

    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
                last_training_time_str = manifest.get("last_trained")
                if last_training_time_str:
                    last_training_time = datetime.fromisoformat(last_training_time_str.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning(f"Failed to read manifest: {e}")

    # Check if more than 24 hours have passed
    if last_training_time is None:
        should_train = True
        reason = "No previous training found"
    else:
        time_since_last = datetime.now(last_training_time.tzinfo) - last_training_time
        should_train = time_since_last > timedelta(hours=24)
        reason = f"Last training was {time_since_last.total_seconds() / 3600:.1f} hours ago"

    if should_train:
        # Trigger background training for all models

        from app.services.ml_service import MLService
        from app.services.training.train_all import train_all

        # Get ML service for hot-reload
        ml_service = MLService()

        def _run_auto_training():
            """Background training function for auto-retrain."""
            global _training_in_progress
            backup_path = None
            try:
                _training_in_progress = True
                logger.info("Auto-retrain: Starting background training for TFT, NLP, and GAT models")
                backup_path = _create_models_backup()

                import asyncio

                # Capture baseline before training
                loop = asyncio.new_event_loop()
                loop.run_until_complete(ml_service.load_models())
                baseline_metrics = _capture_baseline_metrics(ml_service)
                loop.close()

                # Train all models
                manifest = train_all(model_dir=MODEL_DIR)

                # Hot-reload models
                loop = asyncio.new_event_loop()
                loop.run_until_complete(ml_service.load_models())
                loop.close()

                candidate_metrics = _capture_baseline_metrics(ml_service)
                promoted, reasons = _should_promote_candidate(baseline_metrics, candidate_metrics)
                if not promoted:
                    logger.warning("Auto-retrain guardrail rejected candidate: %s", reasons)
                    _restore_models_backup(backup_path)
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(ml_service.load_models())
                    loop.close()

                logger.info(f"Auto-retrain complete — version {manifest['version']}")
            except Exception:
                logger.exception("Auto-retrain failed")
                _restore_models_backup(backup_path)
            finally:
                _cleanup_models_backup(backup_path)
                _training_in_progress = False

        # Run in background
        import threading

        thread = threading.Thread(target=_run_auto_training, daemon=True)
        thread.start()

        return {
            "message": "Auto-retrain triggered for TFT, NLP, and GAT models",
            "triggered": True,
            "reason": reason,
            "last_training": last_training_time.isoformat() if last_training_time else None,
        }
    else:
        return {
            "message": "Auto-retrain skipped - last training was recent",
            "triggered": False,
            "reason": reason,
            "last_training": last_training_time.isoformat() if last_training_time else None,
        }


# ── Disaster-Specific Endpoints ─────────────────────────────────────────────


@router.get("/anomalies/disaster/{disaster_id}")
async def get_disaster_anomalies(
    disaster_id: str,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 30,
    admin: dict = Depends(require_admin),
):
    """Get anomaly alerts for a specific disaster."""
    from app.services.anomaly_service import AnomalyDetectionService

    svc = AnomalyDetectionService()
    alerts = await svc.get_disaster_alerts(
        disaster_id=disaster_id,
        status=status,
        severity=severity,
        limit=limit,
    )
    return {"alerts": alerts, "disaster_id": disaster_id}


@router.get("/outcomes/disaster/{disaster_id}")
async def get_disaster_outcomes(
    disaster_id: str,
    limit: int = 50,
    admin: dict = Depends(require_admin),
):
    """Get outcome tracking records for a specific disaster."""
    from app.services.outcome_service import OutcomeTrackingService

    svc = OutcomeTrackingService()
    return await svc.get_disaster_outcomes(disaster_id=disaster_id, limit=limit)


@router.get("/sitreps/disaster/{disaster_id}")
async def get_disaster_sitreps(
    disaster_id: str,
    limit: int = 10,
    admin: dict = Depends(require_admin),
):
    """Get situation reports for a specific disaster."""
    from app.services.sitrep_service import SitrepService

    svc = SitrepService()
    return await svc.get_disaster_reports(disaster_id=disaster_id, limit=limit)


@router.get("/query-history/disaster/{disaster_id}")
async def get_disaster_query_history(
    disaster_id: str,
    limit: int = 20,
    admin: dict = Depends(require_admin),
):
    """Get query history for a specific disaster."""
    from app.services.nl_query_service import NLQueryService

    svc = NLQueryService()
    return await svc.get_disaster_query_history(disaster_id=disaster_id, user_id=admin.get("id"), limit=limit)


@router.get("/forecast/disaster/{disaster_id}")
async def get_disaster_severity_forecast(
    disaster_id: str,
    horizon_hours: int = 48,
    admin: dict = Depends(require_admin),
):
    """Get severity forecast for a specific disaster."""
    from app.services.ml_service import MLService

    ml_service = MLService()
    forecast = await ml_service.get_disaster_forecast(disaster_id=disaster_id, horizon_hours=horizon_hours)
    return {"forecast": forecast, "disaster_id": disaster_id}


@router.get("/pinn/disaster/{disaster_id}")
async def get_disaster_spread_prediction(
    disaster_id: str,
    time_hours: int = 24,
    admin: dict = Depends(require_admin),
):
    """Get spread prediction for a specific disaster."""
    from app.services.ml_service import MLService

    ml_service = MLService()
    prediction = await ml_service.get_disaster_spread(disaster_id=disaster_id, time_hours=time_hours)
    return {"prediction": prediction, "disaster_id": disaster_id}


@router.get("/recommendations/disaster/{disaster_id}")
async def get_disaster_resource_recommendations(
    disaster_id: str,
    admin: dict = Depends(require_admin),
):
    """Get AI resource recommendations for a specific disaster."""
    from app.services.ml_service import MLService

    ml_service = MLService()
    recommendations = await ml_service.get_disaster_recommendations(disaster_id=disaster_id)
    return {"recommendations": recommendations, "disaster_id": disaster_id}


# ── MoE (Mixture of Experts) Endpoints ──────────────────────────────────────


@router.get("/moe/status")
async def get_moe_status(admin: dict = Depends(require_admin)):
    """Get MoE model status and expert utilization statistics."""
    from ml.moe_disaster_model import load_moe_model

    try:
        moe_engine = load_moe_model()
        utilization = moe_engine.model.get_expert_utilization()
        cache_stats = moe_engine.get_cache_stats()
        
        return {
            "model_loaded": True,
            "n_experts": moe_engine.model.n_experts,
            "top_k": moe_engine.model.top_k,
            "expert_utilization": utilization,
            "cache_stats": cache_stats,
            "experts": moe_engine.model.expert_names,
        }
    except Exception as e:
        logger.error("Failed to get MoE status: %s", e)
        return {
            "model_loaded": False,
            "error": str(e),
        }


@router.post("/moe/predict")
async def moe_predict(
    features: dict[str, Any],
    disaster_type: str = "other",
    severity: str = "medium",
    latitude: float = 0,
    longitude: float = 0,
    use_cache: bool = True,
    admin: dict = Depends(require_admin),
):
    """Make predictions using MoE model with expert routing visualization."""
    from ml.moe_disaster_model import load_moe_model

    try:
        moe_engine = load_moe_model()
        
        # Prepare features
        feature_dict = {
            **features,
            "disaster_type": disaster_type,
            "severity": severity,
            "latitude": latitude,
            "longitude": longitude,
        }
        
        # Make prediction
        result = moe_engine.predict(feature_dict, use_cache=use_cache)
        
        return result
    except Exception as e:
        logger.error("MoE prediction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"MoE prediction failed: {str(e)}")


@router.post("/moe/predict-task")
async def moe_predict_task(
    features: dict[str, Any],
    task: str = "all",
    disaster_type: str = "other",
    severity: str = "medium",
    latitude: float = 0,
    longitude: float = 0,
    admin: dict = Depends(require_admin),
):
    """Make task-specific predictions using MoE model."""
    import torch
    from ml.moe_disaster_model import DISASTER_TYPE_TO_IDX, DisasterMoEModel, load_moe_model

    try:
        moe_engine = load_moe_model()
        
        # Validate task
        valid_tasks = ["severity", "spread", "impact", "resource", "anomaly", "all"]
        if task not in valid_tasks:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid task: {task}. Valid tasks: {valid_tasks}"
            )
        
        # Prepare inputs
        x = moe_engine._prepare_features(features)
        disaster_type_tensor = moe_engine._encode_disaster_type(disaster_type)
        severity_tensor = moe_engine._encode_severity(severity)
        location_tensor = moe_engine._encode_location(latitude, longitude)
        
        # Forward pass with specific task
        with torch.no_grad():
            outputs = moe_engine.model(
                x, disaster_type_tensor, severity_tensor, location_tensor, task=task
            )
        
        # Process outputs based on task
        result = {"task": task}
        
        if task in ("severity", "all"):
            result["severity"] = moe_engine._process_severity(outputs["severity"])
        
        if task in ("spread", "all"):
            result["spread"] = moe_engine._process_spread(outputs["spread"])
        
        if task in ("impact", "all"):
            result["impact"] = moe_engine._process_impact(outputs["impact"])
        
        if task in ("resource", "all"):
            result["resource"] = moe_engine._process_resource(outputs["resource"])
        
        if task in ("anomaly", "all"):
            result["anomaly"] = moe_engine._process_anomaly(outputs["anomaly"])
        
        # Add expert routing info
        result["expert_routing"] = {
            "gate_probs": outputs["gate_probs"].cpu().numpy().tolist(),
            "expert_usage": outputs["expert_usage"].cpu().numpy().tolist(),
            "load_balance_loss": outputs["load_balance_loss"].item(),
        }
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("MoE task prediction failed: %s", e)
        raise HTTPException(status_code=500, detail=f"MoE task prediction failed: {str(e)}")


@router.post("/moe/train")
async def train_moe_endpoint(
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    admin: dict = Depends(require_admin),
):
    """Train MoE model on disaster data."""
    from ml.moe_disaster_model import MOE_CHECKPOINT, train_moe_model

    try:
        # Fetch training data from Supabase
        from app.database import db_admin
        
        resp = await db_admin.table("disasters").select("*").limit(1000).async_execute()
        disasters = resp.data or []
        
        if len(disasters) < 10:
            raise HTTPException(
                status_code=400,
                detail="Insufficient data for MoE training. Need at least 10 disasters."
            )
        
        # Prepare training data (simplified - would need proper feature extraction)
        train_data = []
        val_data = []
        
        for i, disaster in enumerate(disasters):
            features = {
                "disaster_type": disaster.get("type", "other"),
                "severity": disaster.get("severity", "medium"),
                "latitude": disaster.get("latitude", 0),
                "longitude": disaster.get("longitude", 0),
                "affected_population": disaster.get("affected_population", 0),
                "temperature": 25,
                "humidity": 60,
                "wind_speed": 10,
                "pressure": 1013,
                "precipitation": 0,
                "population_density": 100,
                "current_area": disaster.get("estimated_damage", 0) / 1000,
            }
            
            if i < len(disasters) * 0.8:
                train_data.append(features)
            else:
                val_data.append(features)
        
        # Train model
        history = train_moe_model(
            train_data=train_data,
            val_data=val_data,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            save_path=MOE_CHECKPOINT,
        )
        
        return {
            "message": "MoE training complete",
            "epochs": epochs,
            "train_samples": len(train_data),
            "val_samples": len(val_data),
            "final_utilization": history["expert_utilization"][-1] if history["expert_utilization"] else {},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("MoE training failed: %s", e)
        raise HTTPException(status_code=500, detail=f"MoE training failed: {str(e)}")


@router.get("/moe/cache-stats")
async def get_moe_cache_stats(admin: dict = Depends(require_admin)):
    """Get MoE inference cache statistics."""
    from ml.moe_disaster_model import load_moe_model

    try:
        moe_engine = load_moe_model()
        return moe_engine.get_cache_stats()
    except Exception as e:
        logger.error("Failed to get MoE cache stats: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")


@router.post("/moe/clear-cache")
async def clear_moe_cache(admin: dict = Depends(require_admin)):
    """Clear MoE inference cache."""
    from ml.moe_disaster_model import load_moe_model

    try:
        moe_engine = load_moe_model()
        moe_engine.clear_cache()
        return {"message": "MoE cache cleared"}
    except Exception as e:
        logger.error("Failed to clear MoE cache: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.post("/moe/reset-stats")
async def reset_moe_stats(admin: dict = Depends(require_admin)):
    """Reset MoE expert utilization statistics."""
    from ml.moe_disaster_model import load_moe_model

    try:
        moe_engine = load_moe_model()
        moe_engine.model.reset_usage_stats()
        return {"message": "MoE statistics reset"}
    except Exception as e:
        logger.error("Failed to reset MoE stats: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to reset stats: {str(e)}")
