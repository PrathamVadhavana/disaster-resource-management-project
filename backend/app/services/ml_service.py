import os
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from pathlib import Path
import logging

from app.schemas import DisasterSeverity, PredictionType

logger = logging.getLogger(__name__)


class MLService:
    """Service for loading and using ML models for disaster prediction"""
    
    def __init__(self):
        self.models = {}
        self.models_loaded = False
        self.model_dir = Path(__file__).parent.parent.parent / "models"
        
    async def load_models(self):
        """Load all pre-trained ML models"""
        try:
            # Create models directory if it doesn't exist
            self.model_dir.mkdir(exist_ok=True)
            
            # In production, load actual trained models
            # For now, we'll create dummy models
            self.models = {
                'severity_predictor': self._create_dummy_severity_model(),
                'spread_predictor': self._create_dummy_spread_model(),
                'impact_predictor': self._create_dummy_impact_model(),
            }
            
            self.models_loaded = True
            logger.info("ML models loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load ML models: {str(e)}")
            raise
    
    def _create_dummy_severity_model(self):
        """Create a dummy severity prediction model"""
        class DummySeverityModel:
            def predict(self, features):
                # Simple rule-based prediction for demonstration
                temp = features.get('temperature', 25)
                wind_speed = features.get('wind_speed', 20)
                humidity = features.get('humidity', 60)
                
                score = (temp * 0.3 + wind_speed * 0.5 + humidity * 0.2) / 100
                
                if score > 0.75:
                    return 'critical', 0.85
                elif score > 0.5:
                    return 'high', 0.75
                elif score > 0.3:
                    return 'medium', 0.65
                else:
                    return 'low', 0.55
        
        return DummySeverityModel()
    
    def _create_dummy_spread_model(self):
        """Create a dummy spread prediction model"""
        class DummySpreadModel:
            def predict(self, features):
                current_area = features.get('current_area', 100)
                wind_speed = features.get('wind_speed', 20)
                
                # Estimate spread in km²
                spread_rate = wind_speed * 0.5
                predicted_area = current_area * (1 + spread_rate / 100)
                
                return predicted_area, 0.7
        
        return DummySpreadModel()
    
    def _create_dummy_impact_model(self):
        """Create a dummy impact prediction model"""
        class DummyImpactModel:
            def predict(self, features):
                population = features.get('population', 10000)
                severity_score = features.get('severity_score', 0.5)
                
                # Estimate casualties
                casualty_rate = severity_score * 0.1
                predicted_casualties = int(population * casualty_rate)
                
                # Estimate economic damage (in millions)
                damage_per_person = 5000 * severity_score
                predicted_damage = (population * damage_per_person) / 1_000_000
                
                return {
                    'casualties': predicted_casualties,
                    'economic_damage': predicted_damage,
                    'confidence': 0.68
                }
        
        return DummyImpactModel()
    
    async def predict_severity(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict disaster severity"""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")
        
        model = self.models.get('severity_predictor')
        severity, confidence = model.predict(features)
        
        return {
            'predicted_severity': severity,
            'confidence_score': confidence,
            'model_version': '1.0.0'
        }
    
    async def predict_spread(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict disaster spread"""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")
        
        model = self.models.get('spread_predictor')
        area, confidence = model.predict(features)
        
        return {
            'predicted_area_km': area,
            'confidence_score': confidence,
            'model_version': '1.0.0'
        }
    
    async def predict_impact(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict disaster impact"""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")
        
        model = self.models.get('impact_predictor')
        result = model.predict(features)
        
        return {
            'predicted_casualties': result['casualties'],
            'predicted_damage_usd': result['economic_damage'],
            'confidence_score': result['confidence'],
            'model_version': '1.0.0'
        }
    
    async def predict(
        self,
        prediction_type: PredictionType,
        features: Dict[str, Any]
    ) -> Dict[str, Any]:
        """General prediction method that routes to specific predictors"""
        if prediction_type == PredictionType.SEVERITY:
            return await self.predict_severity(features)
        elif prediction_type == PredictionType.SPREAD:
            return await self.predict_spread(features)
        elif prediction_type == PredictionType.IMPACT:
            return await self.predict_impact(features)
        else:
            raise ValueError(f"Unknown prediction type: {prediction_type}")
