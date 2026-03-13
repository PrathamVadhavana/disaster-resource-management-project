import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_ml_service, require_admin
from app.services.ml_eval_service import run_ml_evaluation
from app.services.ml_service import MLService

logger = logging.getLogger("ml_evaluation_router")
router = APIRouter(prefix="/api/ml-evaluation", tags=["ML Evaluation"])


@router.post("/run")
async def run_evaluation(
    days: int = Query(30, ge=1, le=365),
    _admin: dict = Depends(require_admin),
):
    """Run the ML evaluation harness immediately and return the generated report summary."""
    try:
        return await run_ml_evaluation(days=days)
    except Exception as e:
        logger.error("Manual ML evaluation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"ML evaluation failed: {e}")


@router.get("/fallback-governance")
async def fallback_governance_snapshot(
    ml_service: MLService = Depends(get_ml_service),
    _admin: dict = Depends(require_admin),
):
    """Return fallback telemetry and governance snapshot for predictions."""
    try:
        return ml_service.get_fallback_governance_snapshot()
    except Exception as e:
        logger.error("Fallback governance snapshot failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Fallback governance snapshot failed: {e}")


@router.get("/fallback-alerts")
async def fallback_alert_status(
    ml_service: MLService = Depends(get_ml_service),
    _admin: dict = Depends(require_admin),
):
    """Return active fallback-rate alerts derived from ML prediction telemetry."""
    try:
        return ml_service.get_fallback_alerts()
    except Exception as e:
        logger.error("Fallback alert evaluation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Fallback alert evaluation failed: {e}")
