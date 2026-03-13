import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv(override=True)

from app.database import init_db
from app.dependencies import init_supabase_auth, set_ml_service
from app.middleware import configure_logging, setup_logging_middleware, setup_rate_limiting
from app.routers import (
    admin,
    advanced_ml,
    ai_insights,
    analytics,
    auth,
    causal,
    certifications,
    chat,
    disasters,
    donor,
    global_disasters,
    hotspots,
    ingestion,
    interactivity,
    llm,
    ml_evaluation,
    ngo,
    nlp,
    predictions,
    realtime,
    resources,
    retrain,
    victim,
    victim_profile,
    volunteer,
    workflow,
)
from app.routers.ingestion import set_orchestrator
from app.services.anomaly_service import AnomalyDetectionService
from app.services.ingestion.orchestrator import IngestionOrchestrator
from app.services.ml_eval_service import run_ml_evaluation
from app.services.ml_service import MLService
from app.services.sitrep_service import SitrepService

# Configure structured logging
configure_logging()
logger = logging.getLogger(__name__)


# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown.

    All long-lived services are stored on ``app.state`` instead of
    module-level globals so that they are accessible from request
    handlers via ``request.app.state``.
    """
    # Startup
    logger.info("Starting Disaster Management API...")

    # Initialize Supabase auth
    init_supabase_auth()
    logger.info("Auth layer initialized")

    # Initialize Supabase database client
    await init_db()

    # Load ML models
    ml_service = MLService()
    await ml_service.load_models()
    set_ml_service(ml_service)  # Register in dependency module
    app.state.ml_service = ml_service
    logger.info("ML models loaded successfully")

    # Start ingestion orchestrator
    ingestion_orchestrator = IngestionOrchestrator()
    ingestion_orchestrator.set_ml_service(ml_service)
    set_orchestrator(ingestion_orchestrator)
    await ingestion_orchestrator.start()
    app.state.ingestion_orchestrator = ingestion_orchestrator
    logger.info("Ingestion orchestrator started")

    # Phase 5: Start anomaly detection background loop
    anomaly_detector = AnomalyDetectionService()
    asyncio.create_task(anomaly_detector.start_periodic_detection())
    app.state.anomaly_detector = anomaly_detector
    logger.info("Anomaly detection started")

    # Phase 5: Start daily sitrep cron
    sitrep_cron_task = asyncio.create_task(_sitrep_cron_loop())
    app.state.sitrep_cron_task = sitrep_cron_task
    logger.info("Sitrep cron scheduled")

    # Phase 6: Start DBSCAN hotspot clustering every 5 minutes
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    from ml.clustering_service import run_clustering

    hotspot_scheduler = AsyncIOScheduler()
    hotspot_scheduler.add_job(
        run_clustering,
        trigger="interval",
        minutes=30,
        id="hotspot_dbscan",
        name="DBSCAN hotspot detection",
        max_instances=1,
        replace_existing=True,
    )
    hotspot_scheduler.start()
    app.state.hotspot_scheduler = hotspot_scheduler
    logger.info("Hotspot DBSCAN scheduler started (every 30 min)")

    # Phase 5+: Periodic ML evaluation harness run
    from app.core.phase5_config import phase5_config

    eval_scheduler = AsyncIOScheduler()

    async def _scheduled_ml_eval_run():
        try:
            await run_ml_evaluation(days=phase5_config.EVALUATION_LOOKBACK_DAYS)
            logger.info("Scheduled ML evaluation completed")
        except Exception as exc:
            logger.error("Scheduled ML evaluation failed: %s", exc)

    eval_scheduler.add_job(
        _scheduled_ml_eval_run,
        trigger="interval",
        hours=max(1, phase5_config.EVALUATION_INTERVAL_HOURS),
        id="ml_eval_harness",
        name="ML evaluation harness",
        max_instances=1,
        replace_existing=True,
    )
    eval_scheduler.start()
    app.state.eval_scheduler = eval_scheduler
    logger.info(
        "ML evaluation scheduler started (every %sh, lookback=%sd)",
        phase5_config.EVALUATION_INTERVAL_HOURS,
        phase5_config.EVALUATION_LOOKBACK_DAYS,
    )

    async def _scheduled_fallback_alert_check():
        try:
            alerts_payload = ml_service.get_fallback_alerts()
            if alerts_payload.get("alerts_active"):
                logger.warning(
                    "ML fallback alerts active: %s",
                    json.dumps(alerts_payload.get("alerts", []), default=str),
                )
            else:
                logger.debug("ML fallback alert check: no active alerts")
        except Exception as exc:
            logger.error("Scheduled fallback alert check failed: %s", exc)

    eval_scheduler.add_job(
        _scheduled_fallback_alert_check,
        trigger="interval",
        minutes=15,
        id="ml_fallback_alert_check",
        name="ML fallback alert monitor",
        max_instances=1,
        replace_existing=True,
    )

    # Phase 7: Start SLA monitoring background loop
    from app.services.sla_service import sla_check_loop

    sla_task = asyncio.create_task(sla_check_loop())
    app.state.sla_task = sla_task
    logger.info("SLA monitoring background task started")

    # Start event store batch flush loop (reduces DB writes)
    from app.services.event_sourcing_service import start_event_flush_loop

    event_flush_task = asyncio.create_task(start_event_flush_loop())
    app.state.event_flush_task = event_flush_task
    logger.info("Event store batch flush loop started")

    # Start periodic in-memory cache cleanup
    from app.core.query_cache import cleanup_expired

    async def _cache_cleanup_loop():
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            cleanup_expired()

    cache_cleanup_task = asyncio.create_task(_cache_cleanup_loop())
    app.state.cache_cleanup_task = cache_cleanup_task

    # Allow the event loop to complete uvicorn startup before background
    # tasks begin executing database calls.
    await asyncio.sleep(0.1)

    yield

    # Shutdown
    logger.info("Shutting down API...")
    if hasattr(app.state, "anomaly_detector") and app.state.anomaly_detector:
        app.state.anomaly_detector.stop_periodic_detection()
        logger.info("Anomaly detection stopped")
    if hasattr(app.state, "sitrep_cron_task") and app.state.sitrep_cron_task:
        app.state.sitrep_cron_task.cancel()
    if hasattr(app.state, "hotspot_scheduler") and app.state.hotspot_scheduler:
        app.state.hotspot_scheduler.shutdown(wait=False)
        logger.info("Hotspot scheduler stopped")
    if hasattr(app.state, "eval_scheduler") and app.state.eval_scheduler:
        app.state.eval_scheduler.shutdown(wait=False)
        logger.info("ML evaluation scheduler stopped")
    if hasattr(app.state, "sla_task") and app.state.sla_task:
        app.state.sla_task.cancel()
        logger.info("SLA monitoring task stopped")
    if hasattr(app.state, "event_flush_task") and app.state.event_flush_task:
        # Flush remaining events before shutdown
        from app.services.event_sourcing_service import _flush_event_buffer

        await _flush_event_buffer()
        app.state.event_flush_task.cancel()
        logger.info("Event flush task stopped")
    if hasattr(app.state, "cache_cleanup_task") and app.state.cache_cleanup_task:
        app.state.cache_cleanup_task.cancel()
    if hasattr(app.state, "ingestion_orchestrator") and app.state.ingestion_orchestrator:
        await app.state.ingestion_orchestrator.stop()
        logger.info("Ingestion orchestrator stopped")


async def _sitrep_cron_loop():
    """Daily cron loop that generates situation reports at the configured hour."""
    import asyncio

    from app.core.phase5_config import phase5_config

    while True:
        try:
            now = datetime.utcnow()
            target_hour = phase5_config.SITREP_CRON_HOUR_UTC
            next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            if now >= next_run:
                next_run += timedelta(days=1)
            wait_seconds = (next_run - now).total_seconds()
            logger.info("Next sitrep in %.1fh", wait_seconds / 3600)
            await asyncio.sleep(wait_seconds)
            svc = SitrepService()
            await svc.generate_report(report_type="daily", generated_by="system")
            logger.info("Daily situation report generated")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Sitrep cron error: %s", e)
            await asyncio.sleep(3600)


app = FastAPI(
    title="Disaster Management API",
    description="AI-powered disaster prediction and resource allocation system",
    version="1.0.0",
    lifespan=lifespan,
    json_encoder=DateTimeEncoder,
)

# CORS configuration – NEVER use "*" with allow_credentials in production.
# In production, set ALLOWED_ORIGINS to a comma-separated list of frontend URLs.
# Defaults include both common local dev origins.
_default_origins = "http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000"
_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]
if os.getenv("ALLOWED_ORIGINS"):
    logger.info("CORS origins from env: %s", _allowed_origins)
else:
    logger.warning(
        "ALLOWED_ORIGINS env var not set — using localhost defaults. "
        "Set this in production to your deployed frontend URL(s)."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach rate-limiting and request logging middleware
setup_rate_limiting(app)
setup_logging_middleware(app)


# Health check endpoint
@app.get("/")
async def root():
    return {"message": "Disaster Management API", "status": "operational", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    ml = getattr(app.state, "ml_service", None)
    return {"status": "healthy", "ml_models_loaded": ml is not None and ml.models_loaded}


@app.get("/test-datetime")
async def test_datetime():
    """Test endpoint to check datetime serialization"""
    return {"current_time": datetime.utcnow(), "test_datetime": datetime(2024, 1, 23, 10, 0, 0)}


# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(disasters.router, prefix="/api/disasters", tags=["Disasters"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["Predictions"])
app.include_router(resources.router, prefix="/api/resources", tags=["Resources"])
app.include_router(retrain.router, prefix="/api/ml", tags=["ML Models"])
app.include_router(victim.router, prefix="/api/victim", tags=["Victim Requests"])
app.include_router(victim_profile.router, prefix="/api/victim", tags=["Victim Profile"])
app.include_router(nlp.router, prefix="/api/nlp", tags=["NLP Triage & Chatbot"])
app.include_router(ingestion.router, prefix="/api/ingestion", tags=["Data Ingestion & Alerts"])

app.include_router(global_disasters.router, prefix="/api/global-disasters", tags=["Global Live Disasters"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(certifications.router, prefix="/api/volunteer", tags=["Volunteer Certifications"])
app.include_router(volunteer.router, prefix="/api/volunteer", tags=["Volunteer Operations"])
app.include_router(donor.router, prefix="/api/donor", tags=["Donor Operations"])
app.include_router(ngo.router, prefix="/api/ngo", tags=["NGO Operations"])
app.include_router(interactivity.router)
app.include_router(analytics.router)
app.include_router(chat.router)
app.include_router(realtime.router)
app.include_router(hotspots.router, prefix="/api/hotspots", tags=["Hotspot Clusters"])
app.include_router(causal.router, prefix="/api/causal", tags=["Causal AI Analysis"])
app.include_router(llm.router, prefix="/api/llm", tags=["DisasterGPT LLM"])
app.include_router(ml_evaluation.router)
app.include_router(advanced_ml.router, prefix="/api/ml", tags=["Advanced ML (RL, Federated, Multi-Agent, PINN)"])
app.include_router(workflow.router, tags=["Workflow & SLA"])
app.include_router(ai_insights.router, prefix="/api/ai-insights", tags=["AI Insights"])


# Global exception handler – never leak internal details in production
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback

    # Let HTTPExceptions pass through with their real detail
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    # Log the full traceback server-side
    logger.error(
        "Unhandled %s: %s\n%s",
        type(exc).__name__,
        exc,
        traceback.format_exc(),
    )
    # Return a generic message to the client
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["app", "ml", "scripts"], log_level="info"
    )
