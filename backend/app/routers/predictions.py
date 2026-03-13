import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.database import db
from app.dependencies import get_ml_service
from app.schemas import PredictionInput, PredictionResponse, PredictionType
from app.services.ml_service import MLService

router = APIRouter()


@router.post("/", response_model=PredictionResponse, status_code=201)
async def create_prediction(prediction_input: PredictionInput, ml_service: MLService = Depends(get_ml_service)):
    """Create a new prediction using ML models"""
    try:
        # Run ML prediction
        ml_result = await ml_service.predict(prediction_input.prediction_type, prediction_input.features)

        # Prepare prediction data for database
        prediction_data = {
            "id": str(uuid.uuid4()),
            "location_id": prediction_input.location_id,
            "prediction_type": prediction_input.prediction_type.value,
            "features": prediction_input.features,
            "confidence_score": ml_result.get("confidence_score", 0.0),
            "model_version": ml_result.get("model_version", "1.0.0"),
            "created_at": datetime.utcnow().isoformat(),
        }

        # Add prediction-specific fields
        if prediction_input.prediction_type == PredictionType.SEVERITY:
            prediction_data["predicted_severity"] = ml_result.get("predicted_severity")
            # TFT multi-horizon fields
            prediction_data["severity_6h"] = ml_result.get("severity_6h")
            prediction_data["severity_12h"] = ml_result.get("severity_12h")
            prediction_data["severity_24h"] = ml_result.get("severity_24h")
            prediction_data["severity_48h"] = ml_result.get("severity_48h")
            prediction_data["lower_bound"] = ml_result.get("lower_bound")
            prediction_data["upper_bound"] = ml_result.get("upper_bound")

        if prediction_input.prediction_type == PredictionType.SPREAD:
            prediction_data["predicted_area_km2"] = ml_result.get("predicted_area_km2")
            prediction_data["ci_lower_km2"] = ml_result.get("ci_lower_km2")
            prediction_data["ci_upper_km2"] = ml_result.get("ci_upper_km2")

        if prediction_input.prediction_type == PredictionType.IMPACT:
            prediction_data["predicted_casualties"] = ml_result.get("predicted_casualties")
            prediction_data["predicted_damage_usd"] = ml_result.get("predicted_damage_usd")

        # Save to database
        response = await db.table("predictions").insert(prediction_data).async_execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to save prediction")

        return response.data[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.get("/", response_model=list[PredictionResponse])
async def get_predictions(
    location_id: str = None,
    prediction_type: PredictionType = None,
    limit: int = 100,
):
    """Get all predictions with optional filtering"""
    try:
        query = db.table("predictions").select("*")

        if location_id:
            query = query.eq("location_id", location_id)
        if prediction_type:
            query = query.eq("prediction_type", prediction_type.value)

        query = query.order("created_at", desc=True).limit(limit)
        response = await query.async_execute()

        return response.data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(prediction_id: str):
    """Get a specific prediction by ID"""
    try:
        response = await db.table("predictions").select("*").eq("id", prediction_id).single().async_execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Prediction not found")

        return response.data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=list[PredictionResponse])
async def create_batch_predictions(predictions: list[PredictionInput], ml_service: MLService = Depends(get_ml_service)):
    """Create multiple predictions at once"""
    try:
        results = []

        for pred_input in predictions:
            ml_result = await ml_service.predict(pred_input.prediction_type, pred_input.features)

            prediction_data = {
                "id": str(uuid.uuid4()),
                "location_id": pred_input.location_id,
                "prediction_type": pred_input.prediction_type.value,
                "features": pred_input.features,
                "confidence_score": ml_result.get("confidence_score", 0.0),
                "model_version": ml_result.get("model_version", "1.0.0"),
                "created_at": datetime.utcnow().isoformat(),
            }

            if pred_input.prediction_type == PredictionType.SEVERITY:
                prediction_data["predicted_severity"] = ml_result.get("predicted_severity")
                prediction_data["severity_6h"] = ml_result.get("severity_6h")
                prediction_data["severity_12h"] = ml_result.get("severity_12h")
                prediction_data["severity_24h"] = ml_result.get("severity_24h")
                prediction_data["severity_48h"] = ml_result.get("severity_48h")
                prediction_data["lower_bound"] = ml_result.get("lower_bound")
                prediction_data["upper_bound"] = ml_result.get("upper_bound")

            if pred_input.prediction_type == PredictionType.SPREAD:
                prediction_data["predicted_area_km2"] = ml_result.get("predicted_area_km2")
                prediction_data["ci_lower_km2"] = ml_result.get("ci_lower_km2")
                prediction_data["ci_upper_km2"] = ml_result.get("ci_upper_km2")

            if pred_input.prediction_type == PredictionType.IMPACT:
                prediction_data["predicted_casualties"] = ml_result.get("predicted_casualties")
                prediction_data["predicted_damage_usd"] = ml_result.get("predicted_damage_usd")

            results.append(prediction_data)

        # Batch insert
        response = await db.table("predictions").insert(results).async_execute()

        return response.data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {str(e)}")


from app.dependencies import get_ml_service, require_admin


@router.post("/sandbox")
async def ml_sandbox(
    prediction_input: PredictionInput, ml_service: MLService = Depends(get_ml_service), _admin=Depends(require_admin)
):
    """Run ML prediction without saving to database (Sandbox mode)"""
    try:
        ml_result = await ml_service.predict(prediction_input.prediction_type, prediction_input.features)
        return {
            "prediction_type": prediction_input.prediction_type.value,
            "features": prediction_input.features,
            "result": ml_result,
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "sandbox (no-save)",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sandbox prediction failed: {str(e)}")
