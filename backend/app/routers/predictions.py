from fastapi import APIRouter, HTTPException, Depends
from typing import List
from datetime import datetime
import uuid

from app.database import supabase
from app.schemas import PredictionInput, PredictionResponse, PredictionType
from app.services.ml_service import MLService
from app.dependencies import get_ml_service

router = APIRouter()


@router.post("/", response_model=PredictionResponse, status_code=201)
async def create_prediction(
    prediction_input: PredictionInput,
    ml_service: MLService = Depends(get_ml_service)
):
    """Create a new prediction using ML models"""
    try:
        # Run ML prediction
        ml_result = await ml_service.predict(
            prediction_input.prediction_type,
            prediction_input.features
        )
        
        # Prepare prediction data for database
        prediction_data = {
            "id": str(uuid.uuid4()),
            "location_id": prediction_input.location_id,
            "prediction_type": prediction_input.prediction_type.value,
            "features": prediction_input.features,
            "confidence_score": ml_result.get('confidence_score', 0.0),
            "model_version": ml_result.get('model_version', '1.0.0'),
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Add prediction-specific fields
        if prediction_input.prediction_type == PredictionType.SEVERITY:
            prediction_data["predicted_severity"] = ml_result.get('predicted_severity')
        
        if prediction_input.prediction_type == PredictionType.IMPACT:
            prediction_data["predicted_casualties"] = ml_result.get('predicted_casualties')
        
        # Save to database
        response = supabase.table("predictions").insert(prediction_data).execute()
        
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to save prediction")
        
        return response.data[0]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")


@router.get("/", response_model=List[PredictionResponse])
async def get_predictions(
    location_id: str = None,
    prediction_type: PredictionType = None,
    limit: int = 100,
):
    """Get all predictions with optional filtering"""
    try:
        query = supabase.table("predictions").select("*")
        
        if location_id:
            query = query.eq("location_id", location_id)
        if prediction_type:
            query = query.eq("prediction_type", prediction_type.value)
        
        query = query.order("created_at", desc=True).limit(limit)
        response = query.execute()
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(prediction_id: str):
    """Get a specific prediction by ID"""
    try:
        response = (
            supabase.table("predictions")
            .select("*")
            .eq("id", prediction_id)
            .single()
            .execute()
        )
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Prediction not found")
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=List[PredictionResponse])
async def create_batch_predictions(
    predictions: List[PredictionInput],
    ml_service: MLService = Depends(get_ml_service)
):
    """Create multiple predictions at once"""
    try:
        results = []
        
        for pred_input in predictions:
            ml_result = await ml_service.predict(
                pred_input.prediction_type,
                pred_input.features
            )
            
            prediction_data = {
                "id": str(uuid.uuid4()),
                "location_id": pred_input.location_id,
                "prediction_type": pred_input.prediction_type.value,
                "features": pred_input.features,
                "confidence_score": ml_result.get('confidence_score', 0.0),
                "model_version": ml_result.get('model_version', '1.0.0'),
                "created_at": datetime.utcnow().isoformat(),
            }
            
            if pred_input.prediction_type == PredictionType.SEVERITY:
                prediction_data["predicted_severity"] = ml_result.get('predicted_severity')
            
            if pred_input.prediction_type == PredictionType.IMPACT:
                prediction_data["predicted_casualties"] = ml_result.get('predicted_casualties')
            
            results.append(prediction_data)
        
        # Batch insert
        response = supabase.table("predictions").insert(results).execute()
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch prediction failed: {str(e)}")
