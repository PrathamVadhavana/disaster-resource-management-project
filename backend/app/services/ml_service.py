"""
ML Service — loads trained scikit-learn / XGBoost pipelines from disk
and exposes async prediction methods consumed by the FastAPI routers.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
import pandas as pd

from app.schemas import DisasterSeverity, PredictionType
from app.services.training.data_pipeline import (
    DISASTER_TYPES,
    SEVERITY_ORDER,
    TERRAIN_TYPES,
)

logger = logging.getLogger(__name__)


class MLService:
    """Service for loading and using trained ML models for disaster prediction."""

    def __init__(self):
        self.models: Dict[str, Any] = {}
        self.metadata: Dict[str, dict] = {}
        self.models_loaded = False
        self.model_dir = Path(__file__).parent.parent.parent / "models"
        self.model_version = "unknown"

    # ── Model loading ─────────────────────────────────────────────────────

    async def load_models(self):
        """Load all pre-trained ML models from disk, with fallback to dummy."""
        try:
            self.model_dir.mkdir(exist_ok=True)
            manifest_path = self.model_dir / "manifest.json"

            if manifest_path.exists():
                with open(manifest_path) as f:
                    manifest = json.load(f)
                self.model_version = manifest.get("version", "unknown")
                logger.info(f"Loading models – version {self.model_version}")
                self._load_real_models()
            else:
                logger.warning(
                    "No trained models found. Loading rule-based fallbacks. "
                    "Run `python -m app.services.training.train_all` to train."
                )
                self._load_fallback_models()

            self.models_loaded = True
            logger.info("ML models loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load ML models: {e}")
            # Ensure the service stays available with fallbacks
            self._load_fallback_models()
            self.models_loaded = True
            logger.info("Loaded fallback models after error")

    def _load_real_models(self):
        """Load joblib-serialized pipelines from the models/ directory."""
        sev_path = self.model_dir / "severity_model.pkl"
        spr_path = self.model_dir / "spread_model.pkl"
        spr_lo = self.model_dir / "spread_lower.pkl"
        spr_hi = self.model_dir / "spread_upper.pkl"
        imp_path = self.model_dir / "impact_model.pkl"

        # Severity
        if sev_path.exists():
            self.models["severity"] = joblib.load(sev_path)
            meta = self.model_dir / "severity_metadata.json"
            if meta.exists():
                with open(meta) as f:
                    self.metadata["severity"] = json.load(f)
            logger.info(f"  ✔ severity model loaded from {sev_path}")
        else:
            logger.warning("  ✘ severity_model.pkl not found — using fallback")
            self.models["severity"] = None

        # Spread (median + quantile bounds)
        if spr_path.exists():
            self.models["spread"] = joblib.load(spr_path)
            self.models["spread_lower"] = joblib.load(spr_lo) if spr_lo.exists() else None
            self.models["spread_upper"] = joblib.load(spr_hi) if spr_hi.exists() else None
            meta = self.model_dir / "spread_metadata.json"
            if meta.exists():
                with open(meta) as f:
                    self.metadata["spread"] = json.load(f)
            logger.info(f"  ✔ spread model loaded from {spr_path}")
        else:
            logger.warning("  ✘ spread_model.pkl not found — using fallback")
            self.models["spread"] = None

        # Impact
        if imp_path.exists():
            self.models["impact"] = joblib.load(imp_path)
            meta = self.model_dir / "impact_metadata.json"
            if meta.exists():
                with open(meta) as f:
                    self.metadata["impact"] = json.load(f)
            logger.info(f"  ✔ impact model loaded from {imp_path}")
        else:
            logger.warning("  ✘ impact_model.pkl not found — using fallback")
            self.models["impact"] = None

    def _load_fallback_models(self):
        """Populate with None so prediction methods use rule-based fallback."""
        self.models = {"severity": None, "spread": None, "impact": None}
        self.model_version = "fallback"

    # ── Feature builders ──────────────────────────────────────────────────

    def _build_severity_features(self, features: Dict[str, Any]) -> pd.DataFrame:
        """Convert raw feature dict → DataFrame matching training schema."""
        temp = float(features.get("temperature", 25))
        wind = float(features.get("wind_speed", 20))
        hum = float(features.get("humidity", 60))
        pres = float(features.get("pressure", 1013))
        dtype = features.get("disaster_type", "other")

        row = {
            "temperature": temp,
            "wind_speed": wind,
            "humidity": hum,
            "pressure": pres,
            "wind_humidity_idx": wind * hum / 100.0,
            "pressure_drop": 1013.25 - pres,
            "temp_deviation": abs(temp - 25),
        }
        for dt in DISASTER_TYPES:
            row[f"dtype_{dt}"] = 1.0 if dtype == dt else 0.0

        return pd.DataFrame([row])

    def _build_spread_features(self, features: Dict[str, Any]) -> pd.DataFrame:
        area = float(features.get("current_area", features.get("current_area_km2", 50)))
        wind = float(features.get("wind_speed", 20))
        wind_dir = float(features.get("wind_direction", 180))
        elev = float(features.get("elevation_m", 500))
        veg = float(features.get("vegetation_density", 0.5))
        days = int(features.get("days_active", 1))
        terrain = features.get("terrain_type", "flat")
        dtype = features.get("disaster_type", "wildfire")

        terrain_idx = TERRAIN_TYPES.index(terrain) if terrain in TERRAIN_TYPES else 0

        row = {
            "current_area_km2": area,
            "wind_speed": wind,
            "wind_direction": wind_dir,
            "elevation_m": elev,
            "vegetation_density": veg,
            "days_active": days,
            "terrain_idx": terrain_idx,
        }
        for dt in DISASTER_TYPES:
            row[f"dtype_{dt}"] = 1.0 if dtype == dt else 0.0

        return pd.DataFrame([row])

    def _build_impact_features(self, features: Dict[str, Any]) -> pd.DataFrame:
        sev = float(features.get("severity_score", 0.5))
        pop = float(features.get("affected_population", features.get("population", 10000)))
        gdp = float(features.get("gdp_per_capita", 10000))
        infra = float(features.get("infrastructure_density", 0.5))
        dtype = features.get("disaster_type", "other")

        row = {
            "severity_score": sev,
            "affected_population": pop,
            "gdp_per_capita": gdp,
            "infrastructure_density": infra,
        }
        for dt in DISASTER_TYPES:
            row[f"dtype_{dt}"] = 1.0 if dtype == dt else 0.0

        return pd.DataFrame([row])

    # ── Prediction methods ────────────────────────────────────────────────

    async def predict_severity(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict disaster severity using the trained RandomForest pipeline."""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")

        model = self.models.get("severity")
        if model is not None:
            X = self._build_severity_features(features)
            pred_idx = int(model.predict(X)[0])
            severity = SEVERITY_ORDER[pred_idx]

            # Confidence from class probabilities
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X)[0]
                confidence = float(np.max(proba))
            else:
                # Pipeline — get the last step
                clf = model[-1] if hasattr(model, "__getitem__") else model
                if hasattr(clf, "predict_proba"):
                    proba = clf.predict_proba(X)[0]
                    confidence = float(np.max(proba))
                else:
                    confidence = 0.75
        else:
            # Fallback rule-based
            severity, confidence = self._fallback_severity(features)

        return {
            "predicted_severity": severity,
            "confidence_score": round(confidence, 4),
            "model_version": self.model_version,
        }

    async def predict_spread(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict disaster spread with confidence interval."""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")

        model = self.models.get("spread")
        if model is not None:
            X = self._build_spread_features(features)
            predicted_area = float(model.predict(X)[0])

            lower = upper = None
            if self.models.get("spread_lower") is not None:
                lower = float(self.models["spread_lower"].predict(X)[0])
            if self.models.get("spread_upper") is not None:
                upper = float(self.models["spread_upper"].predict(X)[0])

            ci_width = (upper - lower) if (lower is not None and upper is not None) else None
            confidence = max(0.0, min(1.0, 1 - (ci_width / max(predicted_area, 1)) * 0.5)) if ci_width else 0.7
        else:
            predicted_area, confidence = self._fallback_spread(features)
            lower = upper = None

        result = {
            "predicted_area_km2": round(predicted_area, 2),
            "confidence_score": round(confidence, 4),
            "model_version": self.model_version,
        }
        if lower is not None:
            result["ci_lower_km2"] = round(lower, 2)
        if upper is not None:
            result["ci_upper_km2"] = round(upper, 2)

        return result

    async def predict_impact(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Predict casualties and economic damage using the XGBoost multi-output model."""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")

        model = self.models.get("impact")
        if model is not None:
            X = self._build_impact_features(features)
            pred = model.predict(X)[0]  # [casualties, economic_damage]
            casualties = max(0, int(round(pred[0])))
            damage = max(0.0, float(pred[1]))
            confidence = 0.78  # from CV metrics
        else:
            fb = self._fallback_impact(features)
            casualties = fb["casualties"]
            damage = fb["economic_damage"]
            confidence = fb["confidence"]

        return {
            "predicted_casualties": casualties,
            "predicted_damage_usd": round(damage, 2),
            "confidence_score": round(confidence, 4),
            "model_version": self.model_version,
        }

    async def predict(
        self,
        prediction_type: PredictionType,
        features: Dict[str, Any],
    ) -> Dict[str, Any]:
        """General prediction method that routes to specific predictors."""
        if prediction_type == PredictionType.SEVERITY:
            return await self.predict_severity(features)
        elif prediction_type == PredictionType.SPREAD:
            return await self.predict_spread(features)
        elif prediction_type == PredictionType.IMPACT:
            return await self.predict_impact(features)
        else:
            raise ValueError(f"Unknown prediction type: {prediction_type}")

    # ── Model info ────────────────────────────────────────────────────────

    def get_model_info(self) -> Dict[str, Any]:
        """Return current model version and metadata for health checks."""
        return {
            "version": self.model_version,
            "models_loaded": self.models_loaded,
            "severity_loaded": self.models.get("severity") is not None,
            "spread_loaded": self.models.get("spread") is not None,
            "impact_loaded": self.models.get("impact") is not None,
            "metadata": {k: {kk: vv for kk, vv in v.items() if kk != "classification_report"}
                         for k, v in self.metadata.items()},
        }

    # ── Fallbacks (original rule-based logic) ─────────────────────────────

    @staticmethod
    def _fallback_severity(features: Dict[str, Any]):
        temp = features.get("temperature", 25)
        wind = features.get("wind_speed", 20)
        hum = features.get("humidity", 60)
        score = (temp * 0.3 + wind * 0.5 + hum * 0.2) / 100
        if score > 0.75:
            return "critical", 0.55
        elif score > 0.5:
            return "high", 0.50
        elif score > 0.3:
            return "medium", 0.45
        return "low", 0.40

    @staticmethod
    def _fallback_spread(features: Dict[str, Any]):
        area = features.get("current_area", 100)
        wind = features.get("wind_speed", 20)
        predicted = area * (1 + wind * 0.005)
        return predicted, 0.45

    @staticmethod
    def _fallback_impact(features: Dict[str, Any]):
        pop = features.get("population", features.get("affected_population", 10000))
        sev = features.get("severity_score", 0.5)
        cas = int(pop * sev * 0.005)
        dmg = (pop * 5000 * sev) / 1_000_000
        return {"casualties": cas, "economic_damage": dmg, "confidence": 0.40}
