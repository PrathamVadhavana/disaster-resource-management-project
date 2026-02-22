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
