from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import os
import json
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from app.routers import disasters, predictions, resources, auth, victim, victim_profile, retrain, nlp, ingestion, coordinator, global_disasters, admin, certifications, donor
from app.services.ml_service import MLService
from app.services.ingestion.orchestrator import IngestionOrchestrator
from app.routers.ingestion import set_orchestrator
from app.services.anomaly_service import AnomalyDetectionService
from app.services.sitrep_service import SitrepService
from app.database import init_db
from app.dependencies import set_ml_service
from app.middleware import setup_rate_limiting, setup_logging_middleware, configure_logging

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

    # Initialize database
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

    yield

    # Shutdown
    logger.info("Shutting down API...")
    if hasattr(app.state, "anomaly_detector") and app.state.anomaly_detector:
        app.state.anomaly_detector.stop_periodic_detection()
        logger.info("Anomaly detection stopped")
    if hasattr(app.state, "sitrep_cron_task") and app.state.sitrep_cron_task:
        app.state.sitrep_cron_task.cancel()
    if hasattr(app.state, "ingestion_orchestrator") and app.state.ingestion_orchestrator:
        await app.state.ingestion_orchestrator.stop()
        logger.info("Ingestion orchestrator stopped")


async def _sitrep_cron_loop():
    """Daily cron loop that generates situation reports at the configured hour."""
    from app.core.phase5_config import phase5_config
    import asyncio
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
_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
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
    return {
        "message": "Disaster Management API",
        "status": "operational",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    ml = getattr(app.state, "ml_service", None)
    return {
        "status": "healthy",
        "ml_models_loaded": ml is not None and ml.models_loaded
    }


@app.get("/test-datetime")
async def test_datetime():
    """Test endpoint to check datetime serialization"""
    return {
        "current_time": datetime.utcnow(),
        "test_datetime": datetime(2024, 1, 23, 10, 0, 0)
    }


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
app.include_router(coordinator.router, prefix="/api/coordinator", tags=["AI Coordinator Dashboard"])
app.include_router(global_disasters.router, prefix="/api/global-disasters", tags=["Global Live Disasters"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(certifications.router, prefix="/api/volunteer", tags=["Volunteer Certifications"])
app.include_router(donor.router, prefix="/api/donor", tags=["Donor Operations"])


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
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
