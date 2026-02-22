"""
Phase 5 – AI Coordinator Dashboard Router.

Endpoints for:
- Situation reports (generate, list, get)
- Natural language queries (ask, history, feedback)
- Anomaly alerts (list, acknowledge, resolve, run detection)
- Outcome tracking (log, list, evaluate, accuracy summary)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.services.sitrep_service import SitrepService
from app.services.nl_query_service import NLQueryService
from app.services.anomaly_service import AnomalyDetectionService
from app.services.outcome_service import OutcomeTrackingService

router = APIRouter()

# Service instances
sitrep_service = SitrepService()
nl_query_service = NLQueryService()
anomaly_service = AnomalyDetectionService()
outcome_service = OutcomeTrackingService()


# ── Request/Response schemas ───────────────────────────────────────

class GenerateReportRequest(BaseModel):
    report_type: str = Field(default="daily", description="daily, weekly, or on_demand")
    generated_by: str = Field(default="system", description="'system' or user ID")


class NLQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000, description="Natural language question")
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class NLQueryFeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Quality rating 1-5")


class LogOutcomeRequest(BaseModel):
    disaster_id: str
    prediction_id: Optional[str] = None
    prediction_type: str = Field(..., description="severity, spread, or impact")
    actual_severity: Optional[str] = None
    actual_casualties: Optional[int] = None
    actual_damage_usd: Optional[float] = None
    actual_area_km2: Optional[float] = None
    logged_by: str = Field(default="system")
    notes: Optional[str] = None


class AcknowledgeAlertRequest(BaseModel):
    user_id: str


class ResolveAlertRequest(BaseModel):
    status: str = Field(default="resolved", description="resolved or false_positive")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SITUATION REPORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/sitrep/generate")
async def generate_situation_report(request: GenerateReportRequest):
    """Generate a new AI-powered situation report."""
    try:
        report = await sitrep_service.generate_report(
            report_type=request.report_type,
            generated_by=request.generated_by,
        )
        return report
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/sitrep")
async def list_situation_reports(
    report_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List situation reports with optional filtering."""
    reports = await sitrep_service.list_reports(
        report_type=report_type,
        limit=limit,
        offset=offset,
    )
    return {"reports": reports, "total": len(reports)}


@router.get("/sitrep/latest")
async def get_latest_report():
    """Get the most recent generated situation report."""
    report = await sitrep_service.get_latest_report()
    if not report:
        raise HTTPException(status_code=404, detail="No reports found")
    return report


@router.get("/sitrep/{report_id}")
async def get_situation_report(report_id: str):
    """Get a specific situation report by ID."""
    report = await sitrep_service.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/sitrep/data/snapshot")
async def get_data_snapshot():
    """Get the raw data snapshot used for report generation (for preview/debugging)."""
    data = await sitrep_service.gather_all_data()
    return data


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  NATURAL LANGUAGE QUERIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/query")
async def ask_natural_language_query(request: NLQueryRequest):
    """Submit a natural language query and get an AI-powered response."""
    try:
        result = await nl_query_service.ask(
            query_text=request.query,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query processing failed: {str(e)}")


@router.get("/query/history")
async def get_query_history(
    user_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Get natural language query history."""
    history = await nl_query_service.get_query_history(
        user_id=user_id,
        session_id=session_id,
        limit=limit,
    )
    return {"queries": history, "total": len(history)}


@router.post("/query/{query_id}/feedback")
async def submit_query_feedback(query_id: str, request: NLQueryFeedbackRequest):
    """Submit quality feedback for a query response."""
    success = await nl_query_service.submit_feedback(query_id, request.rating)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to submit feedback")
    return {"message": "Feedback submitted", "query_id": query_id, "rating": request.rating}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ANOMALY ALERTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/anomalies")
async def list_anomaly_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List anomaly alerts with optional filtering."""
    alerts = await anomaly_service.get_all_alerts(
        status=status,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return {"alerts": alerts, "total": len(alerts)}


@router.get("/anomalies/active")
async def get_active_anomalies(
    severity: Optional[str] = Query(None),
    anomaly_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get active (unacknowledged) anomaly alerts."""
    alerts = await anomaly_service.get_active_alerts(
        severity=severity,
        anomaly_type=anomaly_type,
        limit=limit,
    )
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/anomalies/detect")
async def run_anomaly_detection():
    """Trigger anomaly detection manually."""
    try:
        alerts = await anomaly_service.run_detection()
        return {
            "message": f"Detection complete: {len(alerts)} anomalies found",
            "alerts": alerts,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anomaly detection failed: {str(e)}")


@router.post("/anomalies/{alert_id}/acknowledge")
async def acknowledge_anomaly(alert_id: str, request: AcknowledgeAlertRequest):
    """Acknowledge an anomaly alert."""
    result = await anomaly_service.acknowledge_alert(alert_id, request.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="Alert not found or update failed")
    return result


@router.post("/anomalies/{alert_id}/resolve")
async def resolve_anomaly(alert_id: str, request: ResolveAlertRequest):
    """Resolve an anomaly alert or mark as false positive."""
    if request.status not in ("resolved", "false_positive"):
        raise HTTPException(status_code=400, detail="Status must be 'resolved' or 'false_positive'")
    result = await anomaly_service.resolve_alert(alert_id, request.status)
    if not result:
        raise HTTPException(status_code=404, detail="Alert not found or update failed")
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OUTCOME TRACKING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/outcomes")
async def log_outcome(request: LogOutcomeRequest):
    """Log an actual outcome for a disaster prediction."""
    try:
        result = await outcome_service.log_outcome(request.dict())
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log outcome: {str(e)}")


@router.get("/outcomes")
async def list_outcomes(
    disaster_id: Optional[str] = Query(None),
    prediction_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List outcome tracking records."""
    outcomes = await outcome_service.get_outcomes(
        disaster_id=disaster_id,
        prediction_type=prediction_type,
        limit=limit,
        offset=offset,
    )
    return {"outcomes": outcomes, "total": len(outcomes)}


@router.post("/outcomes/auto-capture")
async def auto_capture_outcomes():
    """Automatically capture outcomes from resolved disasters."""
    try:
        captured = await outcome_service.auto_capture_outcomes()
        return {
            "message": f"Captured {len(captured)} outcomes",
            "outcomes": captured,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-capture failed: {str(e)}")


@router.post("/outcomes/evaluate")
async def generate_evaluation_report(
    model_type: Optional[str] = Query(None),
    period_days: int = Query(7, ge=1, le=90),
):
    """Generate a model evaluation report."""
    try:
        reports = await outcome_service.generate_evaluation_report(
            model_type=model_type,
            period_days=period_days,
        )
        return {
            "message": f"Generated {len(reports)} evaluation reports",
            "reports": reports,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/outcomes/evaluations")
async def list_evaluation_reports(
    model_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """List model evaluation reports."""
    reports = await outcome_service.get_evaluation_reports(
        model_type=model_type,
        limit=limit,
    )
    return {"reports": reports, "total": len(reports)}


@router.get("/outcomes/accuracy")
async def get_accuracy_summary():
    """Get a summary of model accuracy across all prediction types."""
    summary = await outcome_service.get_accuracy_summary()
    return summary
