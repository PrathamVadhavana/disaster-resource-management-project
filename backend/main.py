from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from app.routers import disasters, predictions, resources, auth
from app.services.ml_service import MLService
from app.database import init_db
from app.dependencies import ml_service as global_ml_service

# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Global ML service instance
ml_service: MLService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    global ml_service

    # Startup
    print("🚀 Starting Disaster Management API...")

    # Initialize database
    await init_db()

    # Load ML models
    ml_service = MLService()
    await ml_service.load_models()
    global_ml_service = ml_service  # Set the global reference
    print("✅ ML models loaded successfully")

    yield

    # Shutdown
    print("👋 Shutting down API...")


app = FastAPI(
    title="Disaster Management API",
    description="AI-powered disaster prediction and resource allocation system",
    version="1.0.0",
    lifespan=lifespan,
    json_encoder=DateTimeEncoder,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    return {
        "status": "healthy",
        "ml_models_loaded": ml_service is not None and ml_service.models_loaded
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


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    # Don't include exception details to avoid datetime serialization issues
    return JSONResponse(
        status_code=500,
        content={
            "message": "An unexpected error occurred",
            "detail": "Internal server error"
        },
    )


# Get ML service dependency
def get_ml_service():
    if ml_service is None:
        raise HTTPException(status_code=503, detail="ML service not initialized")
    return ml_service


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
