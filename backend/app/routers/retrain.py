"""
/api/ml  — model management & retraining endpoints (admin-only).
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.services.ml_service import MLService
from app.dependencies import get_ml_service

logger = logging.getLogger(__name__)
router = APIRouter()

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"


# ── Schemas ───────────────────────────────────────────────────────────────

class RetrainRequest(BaseModel):
    regenerate_data: bool = False
    random_state: int = 42


class RetrainResponse(BaseModel):
    message: str
    version: Optional[str] = None
    severity_f1: Optional[float] = None
    spread_r2: Optional[float] = None
    impact_metrics: Optional[dict] = None


class ModelInfoResponse(BaseModel):
    version: str
    models_loaded: bool
    severity_loaded: bool
    spread_loaded: bool
    impact_loaded: bool
    metadata: Optional[dict] = None


# ── Background training task ─────────────────────────────────────────────

_training_in_progress = False


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

        if regenerate_data:
            logger.info("Regenerating synthetic training data …")
            from scripts.generate_training_data import main as gen_data
            gen_data()

        from app.services.training.train_all import train_all
        manifest = train_all(model_dir=MODEL_DIR)

        # Hot-reload models into the running service
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ml_service.load_models())
        loop.close()

        logger.info(f"Retraining complete — version {manifest['version']}")
    except Exception:
        logger.exception("Retraining failed")
    finally:
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
    Useful for CI / scripted pipelines.
    """
    global _training_in_progress
    if _training_in_progress:
        raise HTTPException(status_code=409, detail="Training already in progress")

    try:
        _training_in_progress = True

        if body.regenerate_data:
            from scripts.generate_training_data import main as gen_data
            gen_data()

        from app.services.training.train_all import train_all
        manifest = train_all(model_dir=MODEL_DIR)

        # Hot-reload models
        await ml_service.load_models()

        return RetrainResponse(
            message="Retraining complete",
            version=manifest.get("version"),
            severity_f1=manifest["models"]["severity"].get("f1_weighted"),
            spread_r2=manifest["models"]["spread"].get("r2"),
            impact_metrics=manifest["models"]["impact"].get("metrics"),
        )
    except Exception as e:
        logger.exception("Sync retraining failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
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
    status: Optional[str] = None,
    severity: Optional[str] = None,
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
    disaster_id: Optional[str] = None,
    prediction_type: Optional[str] = None,
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
    model_type: Optional[str] = None,
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
