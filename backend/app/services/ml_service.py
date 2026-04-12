"""
ML Service — loads trained scikit-learn / XGBoost pipelines from disk
and exposes async prediction methods consumed by the FastAPI routers.

Severity predictions now delegate to a Temporal Fusion Transformer (TFT)
when the trained checkpoint is available, falling back to the legacy
RandomForest / rule-based approach otherwise.
"""

import json
import logging
import math
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.metrics import (
    classification_report,
    f1_score,
    r2_score,
    mean_absolute_error,
)
from sklearn.model_selection import cross_val_score
from sklearn.model_selection import cross_val_predict
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from app.database import db_admin
from app.schemas import PredictionType
from app.services.training.data_pipeline import (
    DISASTER_TYPES,
    SEVERITY_ORDER,
    TERRAIN_TYPES,
)

# Lazy-loaded TFT forecaster singleton
_tft_forecaster = None
_tft_load_attempted = False

logger = logging.getLogger(__name__)


class MLService:
    """Service for loading and using trained ML models for disaster prediction."""

    def __init__(self):
        self.models: dict[str, Any] = {}
        self.metadata: dict[str, dict] = {}
        self.models_loaded = False
        self.model_dir = Path(__file__).parent.parent.parent / "models"
        self.model_version = "unknown"
        self.fallback_alert_rate = float(os.getenv("ML_FALLBACK_ALERT_RATE", "0.2"))
        self._telemetry_window_size = int(os.getenv("ML_TELEMETRY_WINDOW_SIZE", "200"))
        self.prediction_telemetry: dict[str, Any] = {
            "total_predictions": 0,
            "fallback_predictions": 0,
            "by_type": {
                "severity": {"total": 0, "fallback": 0},
                "spread": {"total": 0, "fallback": 0},
                "impact": {"total": 0, "fallback": 0},
            },
            "recent_events": [],
            "last_updated": None,
        }

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

            # Attempt to load TFT model for severity forecasting
            self._load_tft_model()

            self.models_loaded = True
            logger.info("ML models loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load ML models: {e}")
            # Ensure the service stays available with fallbacks
            self._load_fallback_models()
            self.models_loaded = True
            logger.info("Loaded fallback models after error")

    def _load_tft_model(self):
        """Try to load the Temporal Fusion Transformer for severity predictions."""
        global _tft_forecaster, _tft_load_attempted
        if _tft_load_attempted:
            return
        _tft_load_attempted = True
        try:
            from ml.tft_model import TFTSeverityForecaster

            forecaster = TFTSeverityForecaster()
            if forecaster.load():
                _tft_forecaster = forecaster
                logger.info("  ✔ TFT severity forecaster loaded")
            else:
                logger.warning(
                    "  ✘ TFT checkpoint not found — severity uses legacy model. Run `python -m ml.train_tft` to train."
                )
        except ImportError:
            logger.warning(
                "  ✘ pytorch-forecasting not installed — TFT unavailable. "
                "Install with: pip install pytorch-forecasting lightning"
            )
        except Exception as e:
            logger.error("  ✘ TFT load error: %s", e)

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
            self.models["spread_lower"] = (
                joblib.load(spr_lo) if spr_lo.exists() else None
            )
            self.models["spread_upper"] = (
                joblib.load(spr_hi) if spr_hi.exists() else None
            )
            meta = self.model_dir / "spread_metadata.json"
            if meta.exists():
                with open(meta) as f:
                    self.metadata["spread"] = json.load(f)
            logger.info(f"  ✔ spread model loaded from {spr_path}")
        else:
            logger.warning("  ✘ spread_model.pkl not found — using fallback")
            self.models["spread"] = None

        # Clean Up Spread keys if they are None (causes NaN in UI)
        if self.models.get("spread_lower") is None: self.models.pop("spread_lower", None)
        if self.models.get("spread_upper") is None: self.models.pop("spread_upper", None)

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

    def _build_severity_features(self, features: dict[str, Any]) -> pd.DataFrame:
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

    def _build_spread_features(self, features: dict[str, Any]) -> pd.DataFrame:
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

    def _build_impact_features(self, features: dict[str, Any]) -> pd.DataFrame:
        sev = float(features.get("severity_score", 0.5))
        pop = float(
            features.get("affected_population", features.get("population", 10000))
        )
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

    @staticmethod
    def _confidence_band(score: float) -> str:
        if score >= 0.8:
            return "high"
        if score >= 0.6:
            return "medium"
        return "low"

    @staticmethod
    def _clip01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _severity_index(level: str) -> int:
        try:
            return SEVERITY_ORDER.index(level)
        except ValueError:
            return 0

    def _apply_severity_guardrail(
        self, predicted: str, features: dict[str, Any]
    ) -> str:
        """Prevent implausibly low severity under extreme hazard conditions."""

        def _safe_float(value: Any, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        dtype = str(features.get("disaster_type", "other")).lower()
        wind = _safe_float(features.get("wind_speed", 0), 0.0)
        temp = _safe_float(features.get("temperature", 25), 25.0)
        hum = _safe_float(features.get("humidity", 60), 60.0)
        pres = _safe_float(features.get("pressure", 1013.25), 1013.25)

        floor = "low"

        if wind >= 200:
            floor = "critical"
        elif wind >= 120:
            floor = "high"
        elif wind >= 70:
            floor = "medium"

        if pres <= 960:
            floor = "critical"
        elif pres <= 985 and self._severity_index(floor) < self._severity_index("high"):
            floor = "high"

        # Temperature-based exhaustion and risk
        if temp >= 45:
            if self._severity_index(floor) < self._severity_index("critical"):
                floor = "critical"
        elif temp >= 38 and self._severity_index(floor) < self._severity_index("high"):
            floor = "high"

        if dtype == "wildfire":
            if temp >= 42 or (temp >= 35 and hum <= 20) or wind >= 60:
                floor = "critical"
            elif temp >= 30 or (temp >= 25 and hum <= 40) or wind >= 40:
                floor = "high"
            elif temp >= 22:
                floor = "medium"

        if dtype in {"hurricane", "cyclone", "tornado"}:
            if wind >= 130 or pres <= 950:
                floor = "critical"
            elif wind >= 75 or pres <= 980:
                floor = "high"
            elif wind >= 35:
                floor = "medium"

        if dtype == "flood" and (hum >= 85 or wind >= 60):
            floor = "high"
        
        if dtype == "tsunami":
            floor = "critical" # Tsunamis in the sandbox are always high-impact

        # Hard enforcement: If atmospheric conditions are extreme, never allow "low"
        final_severity = (
            floor
            if self._severity_index(predicted) < self._severity_index(floor)
            else predicted
        )
        return final_severity

    def _record_prediction_event(
        self, prediction_type: str, model_version: str, confidence: float
    ) -> None:
        safe_type = (
            prediction_type
            if prediction_type in self.prediction_telemetry["by_type"]
            else "severity"
        )
        model_version_norm = str(model_version or "unknown")
        is_fallback = "fallback" in model_version_norm.lower()

        self.prediction_telemetry["total_predictions"] += 1
        self.prediction_telemetry["by_type"][safe_type]["total"] += 1
        if is_fallback:
            self.prediction_telemetry["fallback_predictions"] += 1
            self.prediction_telemetry["by_type"][safe_type]["fallback"] += 1

        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "prediction_type": safe_type,
            "model_version": model_version_norm,
            "fallback_used": is_fallback,
            "confidence_score": round(self._clip01(confidence), 4),
        }
        self.prediction_telemetry["recent_events"].append(event)
        if (
            len(self.prediction_telemetry["recent_events"])
            > self._telemetry_window_size
        ):
            self.prediction_telemetry["recent_events"] = self.prediction_telemetry[
                "recent_events"
            ][-self._telemetry_window_size :]

        self.prediction_telemetry["last_updated"] = event["timestamp"]

    def get_fallback_governance_snapshot(self) -> dict[str, Any]:
        recent = self.prediction_telemetry["recent_events"]
        recent_total = len(recent)
        recent_fallback = sum(1 for e in recent if e.get("fallback_used"))
        recent_rate = (recent_fallback / recent_total) if recent_total else 0.0

        by_type_recent: dict[str, dict[str, float | int | bool]] = {}
        for ptype in ("severity", "spread", "impact"):
            type_events = [e for e in recent if e.get("prediction_type") == ptype]
            type_total = len(type_events)
            type_fallback = sum(1 for e in type_events if e.get("fallback_used"))
            type_rate = (type_fallback / type_total) if type_total else 0.0
            by_type_recent[ptype] = {
                "recent_total": type_total,
                "recent_fallback": type_fallback,
                "recent_fallback_rate": round(type_rate, 4),
                "alert": type_total >= 10 and type_rate >= self.fallback_alert_rate,
            }

        overall_total = self.prediction_telemetry["total_predictions"]
        overall_fallback = self.prediction_telemetry["fallback_predictions"]
        overall_rate = (overall_fallback / overall_total) if overall_total else 0.0

        return {
            "threshold": {
                "fallback_alert_rate": round(self.fallback_alert_rate, 4),
                "minimum_window_events": 10,
            },
            "lifetime": {
                "total_predictions": overall_total,
                "fallback_predictions": overall_fallback,
                "fallback_rate": round(overall_rate, 4),
                "by_type": self.prediction_telemetry["by_type"],
            },
            "recent_window": {
                "window_size": self._telemetry_window_size,
                "event_count": recent_total,
                "fallback_count": recent_fallback,
                "fallback_rate": round(recent_rate, 4),
                "alert": recent_total >= 10 and recent_rate >= self.fallback_alert_rate,
                "by_type": by_type_recent,
            },
            "last_updated": self.prediction_telemetry.get("last_updated"),
        }

    def get_fallback_alerts(self) -> dict[str, Any]:
        snapshot = self.get_fallback_governance_snapshot()
        threshold = snapshot.get("threshold", {}).get(
            "fallback_alert_rate", self.fallback_alert_rate
        )
        recent_window = snapshot.get("recent_window", {})

        alerts: list[dict[str, Any]] = []
        if recent_window.get("alert"):
            alerts.append(
                {
                    "scope": "overall",
                    "severity": "warning",
                    "message": "Overall fallback usage exceeded alert threshold in recent window.",
                    "fallback_rate": recent_window.get("fallback_rate", 0.0),
                    "threshold": threshold,
                    "event_count": recent_window.get("event_count", 0),
                }
            )

        by_type = recent_window.get("by_type") or {}
        for ptype, stats in by_type.items():
            if stats.get("alert"):
                alerts.append(
                    {
                        "scope": str(ptype),
                        "severity": "warning",
                        "message": f"Fallback usage exceeded threshold for {ptype} predictions.",
                        "fallback_rate": stats.get("recent_fallback_rate", 0.0),
                        "threshold": threshold,
                        "event_count": stats.get("recent_total", 0),
                    }
                )

        status = "alert" if alerts else "ok"
        return {
            "status": status,
            "alerts_active": bool(alerts),
            "threshold": threshold,
            "alerts": alerts,
            "snapshot": snapshot,
        }

    def _calibrate_classification_confidence(
        self, raw_confidence: float, margin: float | None = None
    ) -> float:
        conf = self._clip01(raw_confidence)
        margin_score = 0.0
        if margin is not None:
            margin_score = self._clip01(margin)
        calibrated = 0.75 * conf + 0.25 * margin_score
        return self._clip01(calibrated)

    def _calibrate_regression_confidence(
        self,
        model_key: str,
        base_confidence: float,
        interval_width: float | None,
        predicted_value: float,
    ) -> float:
        confidence = self._clip01(base_confidence)
        if interval_width is not None and predicted_value > 0:
            rel_width = abs(float(interval_width)) / max(
                abs(float(predicted_value)), 1.0
            )
            interval_penalty = self._clip01(rel_width)
            confidence = self._clip01(confidence * (1 - 0.45 * interval_penalty))

        expected_mae = self.metadata.get(model_key, {}).get("cv_mae_mean")
        if expected_mae is not None:
            try:
                mae_penalty = 1.0 / (1.0 + float(expected_mae))
                confidence = self._clip01(0.8 * confidence + 0.2 * mae_penalty)
            except (TypeError, ValueError):
                pass
        return confidence

    # ── Prediction methods ────────────────────────────────────────────────

    async def predict_severity(self, features: dict[str, Any]) -> dict[str, Any]:
        """Predict disaster severity.

        Delegates to the Temporal Fusion Transformer when available,
        providing multi-horizon forecasts (t+6h, t+12h, t+24h, t+48h)
        with quantile uncertainty bands.  Falls back to the legacy
        RandomForest pipeline or rule-based heuristic otherwise.
        """
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")

        # ── Try TFT first (multi-horizon with uncertainty) ──────────────
        global _tft_forecaster
        if _tft_forecaster is not None:
            try:
                result = _tft_forecaster.predict_from_features(features)
                # Apply guardrail to TFT output too!
                if "predicted_severity" in result:
                    result["predicted_severity"] = self._apply_severity_guardrail(result["predicted_severity"], features)
                
                confidence = self._clip01(float(result.get("confidence_score") or 0.0))
                result["confidence_score"] = round(confidence, 4)
                result.setdefault("confidence_band", self._confidence_band(confidence))
                model_version = str(result.get("model_version") or "tft")
                self._record_prediction_event("severity", model_version, confidence)
                return result
            except Exception as e:
                logger.warning("TFT inference failed, falling back: %s", e)

        # ── Legacy path: sklearn / rule-based ───────────────────────────
        model = self.models.get("severity")
        if model is not None:
            X = self._build_severity_features(features)
            pred_idx = int(model.predict(X)[0])
            severity = SEVERITY_ORDER[pred_idx]

            # Confidence from class probabilities
            margin = None
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X)[0]
                confidence = float(np.max(proba))
                sorted_proba = np.sort(proba)
                if len(sorted_proba) > 1:
                    margin = float(sorted_proba[-1] - sorted_proba[-2])
            else:
                clf = model[-1] if hasattr(model, "__getitem__") else model
                if hasattr(clf, "predict_proba"):
                    proba = clf.predict_proba(X)[0]
                    confidence = float(np.max(proba))
                    sorted_proba = np.sort(proba)
                    if len(sorted_proba) > 1:
                        margin = float(sorted_proba[-1] - sorted_proba[-2])
                else:
                    confidence = 0.75
            confidence = self._calibrate_classification_confidence(confidence, margin)
        else:
            severity, confidence = self._fallback_severity(features)
            confidence = self._calibrate_classification_confidence(confidence)

        severity = self._apply_severity_guardrail(severity, features)

        # Return legacy result with multi-horizon stub fields for compat
        confidence = self._clip01(confidence)
        result = {
            "predicted_severity": severity,
            "severity_6h": severity,
            "severity_12h": severity,
            "severity_24h": severity,
            "severity_48h": severity,
            "lower_bound": {},
            "upper_bound": {},
            "confidence_score": round(confidence, 4),
            "confidence_band": self._confidence_band(confidence),
            "model_version": self.model_version,
        }
        self._record_prediction_event(
            "severity",
            str(result.get("model_version") or self.model_version),
            confidence,
        )
        return result

    async def predict_spread(self, features: dict[str, Any]) -> dict[str, Any]:
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

            ci_width = (
                (upper - lower) if (lower is not None and upper is not None) else None
            )
            confidence = self._calibrate_regression_confidence(
                model_key="spread",
                base_confidence=0.85, # Base confidence for regression ML
                interval_width=ci_width,
                predicted_value=predicted_area,
            )
        else:
            # ── Chain Inference: If weather is present, use it to bias the spread ──
            sev_bias = 1.0
            sev_label = "medium"
            if "temperature" in features or "wind_speed" in features:
                # Get a severity score to influence the spread
                sev_res = await self.predict_severity(features)
                sev_label = sev_res.get("predicted_severity", "medium")
                sev_bias = 0.8 + (self._severity_index(sev_label) * 0.5) # Aggressive scale

            predicted_area, confidence = self._fallback_spread(features)
            
            def _safe_float(value: Any, default: float) -> float:
                try: return float(value)
                except: return default

            # Aggressive scaling for extreme weather
            temp = _safe_float(features.get("temperature", 25), 25.0)
            wind = _safe_float(features.get("wind_speed", 0), 0.0)
            
            if temp > 40 or wind > 60:
                predicted_area *= 3.0
            elif temp > 32 or wind > 35:
                predicted_area *= 1.8
            
            predicted_area *= sev_bias
            lower = upper = None
            confidence = self._calibrate_regression_confidence(
                model_key="spread",
                base_confidence=confidence,
                interval_width=None,
                predicted_value=predicted_area,
            )

        confidence = self._clip01(confidence)
        result = {
            "predicted_area_km2": round(predicted_area, 2),
            "confidence_score": round(confidence, 4),
            "confidence_band": self._confidence_band(confidence),
            "model_version": self.model_version,
        }
        if lower is not None:
            result["ci_lower_km2"] = round(lower, 2)
        if upper is not None:
            result["ci_upper_km2"] = round(upper, 2)

        # Propagate severity context if available
        if 'sev_label' in locals():
            result["predicted_severity"] = sev_label

        self._record_prediction_event(
            "spread", str(result.get("model_version") or self.model_version), confidence
        )

        return result

    async def predict_impact(self, features: dict[str, Any]) -> dict[str, Any]:
        """Predict casualties and economic damage using the XGBoost multi-output model."""
        if not self.models_loaded:
            raise RuntimeError("Models not loaded")

        model = self.models.get("impact")
        if model is not None:
            X = self._build_impact_features(features)
            pred = model.predict(X)[0]  # [casualties, economic_damage]
            casualties = max(0, int(round(pred[0])))
            damage = max(0.0, float(pred[1]))
            magnitude = casualties + (damage / 1_000_000.0)
            raw_conf = 1.0 / (1.0 + math.log1p(max(magnitude, 1.0)) * 0.06)
            confidence = self._calibrate_regression_confidence(
                model_key="impact",
                base_confidence=raw_conf,
                interval_width=None,
                predicted_value=max(magnitude, 1.0),
            )
        else:
            # ── Chain Inference: Force a realistic severity score if missing ──
            sev_label = "medium"
            if "severity_score" not in features and ("temperature" in features or "wind_speed" in features):
                sev_res = await self.predict_severity(features)
                sev_label = sev_res.get("predicted_severity", "medium")
                # Map label to 0-1 scale: low=0.2, med=0.5, high=0.8, crit=1.0
                features["severity_score"] = [0.2, 0.5, 0.8, 1.0][self._severity_index(sev_label)]
            elif "severity_score" in features:
                # Map back to a label if possible for the multiplier logic
                scores = [0.2, 0.5, 0.8, 1.0]
                idx = 0
                closest_diff = 1.0
                for i, s in enumerate(scores):
                    diff = abs(float(features["severity_score"]) - s)
                    if diff < closest_diff:
                        closest_diff = diff
                        idx = i
                sev_label = SEVERITY_ORDER[idx]

            fb = self._fallback_impact(features)
            casualties = fb["casualties"]
            damage = fb["economic_damage"]
            pop = float(features.get("affected_population", features.get("population", 10000)))
            
            # Massive escalation for Critical/High severity stressors
            # 48C Wildfire = Exponential catastrophic impact
            sev_idx = self._severity_index(sev_label)
            
            # Use exponential multipliers: Low=0.2, Med=1.0, High=5.0, Crit=20.0
            sev_multiplier = [0.2, 1.0, 5.0, 20.0][sev_idx]
            
            def _safe_float(value: Any, default: float) -> float:
                try: return float(value)
                except: return default

            # Additional stressor bias (Wind/Heat)
            temp_val = _safe_float(features.get("temperature", 25), 25.0)
            wind_val = _safe_float(features.get("wind_speed", 0), 0.0)
            
            temp_bias = max(1.0, (temp_val - 22) / 8.0)
            wind_bias = max(1.0, wind_val / 35.0)
            
            casualties = min(int(pop), int(casualties * sev_multiplier * temp_bias * wind_bias))
            damage *= (sev_multiplier * temp_bias * wind_bias)

            confidence = self._calibrate_regression_confidence(
                model_key="impact",
                base_confidence=fb["confidence"],
                interval_width=None,
                predicted_value=max(float(casualties + damage), 1.0),
            )

        confidence = self._clip01(confidence)
        result = {
            "predicted_casualties": casualties,
            "predicted_damage_usd": round(damage, 2),
            "predicted_severity": locals().get('sev_label', features.get('severity_label', 'medium')), 
            "confidence_score": round(confidence, 4),
            "confidence_band": self._confidence_band(confidence),
            "model_version": self.model_version,
        }
        self._record_prediction_event(
            "impact", str(result.get("model_version") or self.model_version), confidence
        )
        return result

    async def predict(
        self,
        prediction_type: PredictionType,
        features: dict[str, Any],
        run_ensemble: bool = False,
    ) -> dict[str, Any]:
        """General prediction method with ensemble and XAI support."""
        # 1. Base Prediction
        if prediction_type == PredictionType.SEVERITY:
            base_result = await self.predict_severity(features)
        elif prediction_type == PredictionType.SPREAD:
            base_result = await self.predict_spread(features)
        elif prediction_type == PredictionType.IMPACT:
            base_result = await self.predict_impact(features)
        else:
            raise ValueError(f"Unknown prediction type: {prediction_type}")

        # 2. XAI: Feature Importance (Simulation-driven attribution)
        importance = self._calculate_feature_importance(prediction_type, features)
        base_result["feature_importance"] = importance

        # 3. Decision Support: Resource Recommendations
        if prediction_type == PredictionType.IMPACT or (
            "predicted_casualties" in base_result
            or "predicted_damage_usd" in base_result
        ):
            cas = base_result.get("predicted_casualties", 0)
            dmg = base_result.get("predicted_damage_usd", 0)
            sev = base_result.get("predicted_severity", "medium")
            base_result["recommendations"] = self._suggest_resources(cas, dmg, sev, features)

        # 4. Ensemble Logic (Comparison with secondary models)
        if run_ensemble:
            base_result["ensemble"] = await self._run_ensemble_comparison(
                prediction_type, features, base_result
            )

        return base_result

    def _calculate_feature_importance(
        self, prediction_type: PredictionType, features: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Calculate relative contribution of each feature to the result."""
        typed_features = {}
        if prediction_type == PredictionType.SEVERITY:
            typed_features = self._build_severity_features(features).to_dict("records")[0]
        elif prediction_type == PredictionType.SPREAD:
            typed_features = self._build_spread_features(features).to_dict("records")[0]
        elif prediction_type == PredictionType.IMPACT:
            typed_features = self._build_impact_features(features).to_dict("records")[0]

        # In a real scenario, we'd use model.feature_importances_ or SHAP.
        # Here we use a weighted attribution based on the raw values and model type.
        importance_list = []
        for key, val in typed_features.items():
            if key.startswith("dtype_"):
                continue
            
            # Use relative scale: how much does this variable deviate from its nominal baseline?
            nominal = 0.0
            if "temp" in key: nominal = 25.0
            if "pres" in key: nominal = 1013.0
            if "hum" in key: nominal = 50.0
            if "pop" in key: nominal = 5000.0
            if "area" in key: nominal = 100.0

            # Absolute deviation normalized by a typical range
            range_val = 50.0 # Wide default range
            if "pres" in key: range_val = 50.0
            if "wind" in key: range_val = 100.0
            if "pop" in key: range_val = 10000.0

            deviation = abs(float(val) - nominal) / range_val
            weight = 0.5
            if "temp" in key: weight = 0.95 # Higher sensitivity
            if "wind" in key: weight = 0.9
            if "pop" in key: weight = 0.8
            if "area" in key: weight = 0.85
            
            score = (deviation + 0.1) * weight
            importance_list.append({"feature": key.replace("_", " "), "score": score})

        # Normalize to 100%
        total = sum(d["score"] for d in importance_list) or 1
        for d in importance_list:
            d["percentage"] = round((d["score"] / total) * 100, 1)
        
        return sorted(importance_list, key=lambda x: x["percentage"], reverse=True)

    def _suggest_resources(
        self, casualties: int, damage_usd: float, severity: str, features: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Map predicted impact to specific resource requirements."""
        pop = float(features.get("affected_population", features.get("population", 5000)))
        sev_idx = self._severity_index(severity) or 2  # default medium
        multiplier = 1.0 + (sev_idx * 0.25)

        # Heuristic calculations for standard disaster kits
        recs = [
            {
                "type": "Water",
                "quantity": int(pop * 3.5 * multiplier),
                "unit": "Liters",
                "priority": "Critical" if sev_idx >= 2 else "High",
                "reason": "Sustainment baseline (3.5L/person/day) scaled by severity."
            },
            {
                "type": "Emergency Food",
                "quantity": int(pop * 2 * multiplier),
                "unit": "Rations",
                "priority": "High",
                "reason": "48-hour emergency supply for affected population."
            },
            {
                "type": "Medical Kits",
                "quantity": int(max(casualties * 1.5, pop * 0.05)),
                "unit": "Units",
                "priority": "Critical" if casualties > 0 else "Medium",
                "reason": "Trauma and basic care kits based on casualty forecasts."
            }
        ]

        if "wildfire" in str(features.get("disaster_type", "")).lower():
            recs.append({
                "type": "Air Filtration",
                "quantity": int(pop * 0.1),
                "unit": "Masks",
                "priority": "Medium",
                "reason": "Smoke inhalation protection for fringe zones."
            })

        if damage_usd > 10.0:  # >10M USD damage
            recs.append({
                "type": "Mobile Shelter",
                "quantity": int(pop * 0.15),
                "unit": "Beds",
                "priority": "High",
                "reason": "Infrastructure damage implies significant housing loss."
            })

        return recs

    async def _run_ensemble_comparison(
        self, prediction_type: PredictionType, features: dict[str, Any], base_result: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare loaded ML model vs rule-based fallback to detect outliers."""
        if "fallback" in str(base_result.get("model_version", "")).lower():
            return {"status": "skipped", "reason": "Base is already fallback"}

        # Run fallback manually
        if prediction_type == PredictionType.SEVERITY:
            f_val, f_conf = self._fallback_severity(features)
            match = f_val == base_result.get("predicted_severity")
        elif prediction_type == PredictionType.SPREAD:
            f_val, f_conf = self._fallback_spread(features)
            # 20% tolerance for match
            match = abs(float(f_val) - float(base_result.get("predicted_area_km2", 0))) < (float(f_val) * 0.2)
        else:
            f_obj = self._fallback_impact(features)
            f_val = f_obj["casualties"]
            match = abs(f_val - base_result.get("predicted_casualties", 0)) < 10

        return {
            "primary_model": base_result.get("model_version", "unknown"),
            "fallback_model": "rule-v1",
            "agreement": "High" if match else "Low",
            "fallback_value": f_val,
            "variance": "Actionable" if not match else "Nominal"
        }

    # ── Model info ────────────────────────────────────────────────────────

    def get_model_info(self) -> dict[str, Any]:
        """Return current model version and metadata for health checks."""
        return {
            "version": self.model_version,
            "models_loaded": self.models_loaded,
            "severity_loaded": self.models.get("severity") is not None,
            "spread_loaded": self.models.get("spread") is not None,
            "impact_loaded": self.models.get("impact") is not None,
            "metadata": {
                k: {kk: vv for kk, vv in v.items() if kk != "classification_report"}
                for k, v in self.metadata.items()
            },
        }

    # ── Fallbacks (original rule-based logic) ─────────────────────────────

    @staticmethod
    def _fallback_severity(features: dict[str, Any]):
        def _safe_float(value: Any, default: float) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        temp = _safe_float(features.get("temperature", 25), 25.0)
        wind = _safe_float(features.get("wind_speed", 20), 20.0)
        hum = _safe_float(features.get("humidity", 60), 60.0)
        pres = _safe_float(features.get("pressure", 1013.25), 1013.25)
        dtype = str(features.get("disaster_type", "other")).lower()

        # Normalize core weather signals into 0..1 risk components.
        temp_risk = max(0.0, min(1.0, (temp - 20.0) / 20.0))
        wind_risk = max(0.0, min(1.0, wind / 80.0))
        hum_risk = max(0.0, min(1.0, hum / 100.0))
        pressure_risk = max(0.0, min(1.0, (1013.25 - pres) / 40.0))

        type_bias = {
            "hurricane": 0.22,
            "cyclone": 0.20,
            "wildfire": 0.18,
            "earthquake": 0.16,
            "flood": 0.12,
            "other": 0.08,
        }.get(dtype, 0.08)

        score = (
            temp_risk * 0.22
            + wind_risk * 0.30
            + hum_risk * 0.20
            + pressure_risk * 0.16
            + type_bias
        )

        if score >= 0.85:
            return "critical", 0.58
        if score >= 0.65:
            return "high", 0.52
        if score >= 0.45:
            return "medium", 0.47
        return "low", 0.42

    @staticmethod
    def _fallback_spread(features: dict[str, Any]):
        area = features.get("current_area", 100)
        wind = features.get("wind_speed", 20)
        predicted = area * (1 + wind * 0.005)
        return predicted, 0.45

    @staticmethod
    def _fallback_impact(features: dict[str, Any]):
        pop = float(features.get("population", features.get("affected_population", 10000)))
        sev = float(features.get("severity_score", 0.5))
        
        # Base rates that scale with severity
        # Low: 0.1%, Med: 0.5%, High: 2%, Crit: 5% (before multipliers)
        rate = 0.005
        if sev >= 0.9: rate = 0.05
        elif sev >= 0.7: rate = 0.02
        elif sev <= 0.3: rate = 0.001
        
        cas = int(pop * rate)
        # Damage: $10k per high-severity person, $2k per medium
        dmg_per_capita = 4000 * (sev ** 1.5)
        dmg = (pop * dmg_per_capita) / 1_000_000
        
        return {"casualties": cas, "economic_damage": dmg, "confidence": 0.40}

    # ── Build Training Data from Supabase ─────────────────────────────────────

    async def build_training_data_from_supabase(self) -> dict[str, Any]:
        """
        Build training datasets from Supabase for all model types.

        Queries database tables to construct training data, trains models with
        cross-validation, saves models to disk, and logs training events.

        Returns dict with training results for each model type.
        """
        results = {}
        version = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        logger.info(f"Starting Supabase-based training — version {version}")

        # ─────────────────────────────────────────────────────────────────────
        # 1. SEVERITY MODEL
        # ─────────────────────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("BUILDING: Severity Model Training Data")
        logger.info("=" * 60)

        severity_result = await self._build_severity_training_data()
        if severity_result.get("skipped"):
            logger.warning("Severity model skipped — insufficient data (< 10 rows)")
            results["severity"] = {
                "skipped": True,
                "reason": severity_result.get("reason"),
            }
        else:
            # Train and save
            train_result = await self._train_model_with_cv(
                X=severity_result["X"],
                y=severity_result["y"],
                model_type="severity",
                version=version,
                is_classification=True,
            )
            results["severity"] = train_result

        # ─────────────────────────────────────────────────────────────────────
        # 2. SPREAD MODEL
        # ─────────────────────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("BUILDING: Spread Model Training Data")
        logger.info("=" * 60)

        spread_result = await self._build_spread_training_data()
        if spread_result.get("skipped"):
            logger.warning("Spread model skipped — insufficient data (< 10 rows)")
            results["spread"] = {"skipped": True, "reason": spread_result.get("reason")}
        else:
            train_result = await self._train_model_with_cv(
                X=spread_result["X"],
                y=spread_result["y"],
                model_type="spread",
                version=version,
                is_classification=False,
            )
            results["spread"] = train_result

        # ─────────────────────────────────────────────────────────────────────
        # 3. IMPACT MODEL
        # ─────────────────────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("BUILDING: Impact Model Training Data")
        logger.info("=" * 60)

        impact_result = await self._build_impact_training_data()
        if impact_result.get("skipped"):
            logger.warning("Impact model skipped — insufficient data (< 10 rows)")
            results["impact"] = {"skipped": True, "reason": impact_result.get("reason")}
        else:
            train_result = await self._train_model_with_cv(
                X=impact_result["X"],
                y=impact_result["y"],
                model_type="impact",
                version=version,
                is_classification=False,
                is_multi_output=True,
            )
            results["impact"] = train_result

        # ─────────────────────────────────────────────────────────────────────
        # 4. DEMAND FORECASTING (SHORTFALL)
        # ─────────────────────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("BUILDING: Demand Forecasting Model Training Data")
        logger.info("=" * 60)

        demand_result = await self._build_demand_forecasting_data()
        if demand_result.get("skipped"):
            logger.warning(
                "Demand forecasting model skipped — insufficient data (< 10 rows)"
            )
            results["demand_forecasting"] = {
                "skipped": True,
                "reason": demand_result.get("reason"),
            }
        else:
            train_result = await self._train_model_with_cv(
                X=demand_result["X"],
                y=demand_result["y"],
                model_type="demand_forecasting",
                version=version,
                is_classification=False,
            )
            results["demand_forecasting"] = train_result

        # Update manifest
        await self._update_manifest(version, results)

        logger.info(f"Supabase-based training complete — version {version}")
        return results

    async def _build_severity_training_data(self) -> dict[str, Any]:
        """
        Build training data for SEVERITY model.

        Query: disasters (status != 'predicted', has non-null severity)
        Join: locations (latitude, longitude, population)
        Join: outcome_tracking (prediction_type = 'severity') for ground-truth corrections

        Features: disaster_type (one-hot), latitude, longitude, affected_population,
                  casualties (if available), month_of_year (from start_date)
        Label: actual severity (low=0, medium=1, high=2, critical=3)
        """
        try:
            # Query disasters with non-null severity and not predicted
            disasters_resp = (
                await db_admin.table("disasters")
                .select(
                    "id, type, severity, start_date, affected_population, casualties, location_id"
                )
                .neq("status", "predicted")
                .not_.is_("severity", None)
                .execute()
            )
            disasters = disasters_resp.data or []
            logger.info(f"Found {len(disasters)} disasters with severity data")

            if len(disasters) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(disasters)} rows (minimum 10)",
                }

            # Get location data
            location_ids = [d["location_id"] for d in disasters if d.get("location_id")]
            locations = {}
            if location_ids:
                loc_resp = (
                    await db_admin.table("locations")
                    .select("id, latitude, longitude, population")
                    .in_("id", location_ids)
                    .execute()
                )
                for loc in loc_resp.data or []:
                    locations[loc["id"]] = loc

            # Get outcome_tracking for ground truth
            disaster_ids = [d["id"] for d in disasters]
            outcomes = {}
            if disaster_ids:
                outcomes_resp = (
                    await db_admin.table("outcome_tracking")
                    .select("disaster_id, actual_severity, actual_casualties")
                    .eq("prediction_type", "severity")
                    .in_("disaster_id", disaster_ids)
                    .execute()
                )
                for outcome in outcomes_resp.data or []:
                    outcomes[outcome["disaster_id"]] = outcome

            # Build features
            rows = []
            for d in disasters:
                loc = locations.get(d.get("location_id"), {})
                outcome = outcomes.get(d["id"], {})

                # Use actual severity from outcome_tracking if available, else use disaster severity
                severity = outcome.get("actual_severity") or d.get("severity")
                if not severity:
                    continue

                # Get month from start_date
                start_date = d.get("start_date")
                month = 1  # default
                if start_date:
                    try:
                        if isinstance(start_date, str):
                            month = (
                                int(start_date.split("-")[1])
                                if "-" in start_date
                                else 1
                            )
                        else:
                            month = getattr(start_date, "month", 1)
                    except Exception:
                        month = 1

                row = {
                    "disaster_type": d.get("type", "other"),
                    "latitude": loc.get("latitude", 0) or 0,
                    "longitude": loc.get("longitude", 0) or 0,
                    "affected_population": d.get("affected_population", 0) or 0,
                    "casualties": outcome.get("actual_casualties")
                    or d.get("casualties", 0)
                    or 0,
                    "month_of_year": month,
                }
                row["severity_label"] = (
                    SEVERITY_ORDER.index(severity.lower())
                    if severity.lower() in SEVERITY_ORDER
                    else -1
                )
                if row["severity_label"] >= 0:
                    rows.append(row)

            if len(rows) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(rows)} valid rows after processing (minimum 10)",
                }

            df = pd.DataFrame(rows)

            # One-hot encode disaster_type
            for dt in DISASTER_TYPES:
                df[f"dtype_{dt}"] = (df["disaster_type"] == dt).astype(float)

            feature_cols = [
                "latitude",
                "longitude",
                "affected_population",
                "casualties",
                "month_of_year",
            ] + [f"dtype_{dt}" for dt in DISASTER_TYPES]

            X = df[feature_cols].astype(float)
            y = df["severity_label"].astype(int)

            logger.info(
                f"Severity training data: {len(X)} rows, {len(feature_cols)} features"
            )
            return {"X": X, "y": y, "rows": len(rows)}

        except Exception as e:
            logger.error(f"Error building severity training data: {e}")
            return {"skipped": True, "reason": str(e)}

    async def _build_spread_training_data(self) -> dict[str, Any]:
        """
        Build training data for SPREAD model.

        Query: disasters joined with predictions where prediction_type = 'spread'
        Join: outcome_tracking for ground truth

        Features: disaster_type, wind_speed (from metadata JSON), current_area (from metadata),
                  severity_numeric
        Label: predicted_area_km2 from outcome_tracking actual_value, or fallback to predictions.predicted_area_km2
        """
        try:
            # Query predictions of type spread
            preds_resp = (
                await db_admin.table("predictions")
                .select(
                    "id, disaster_id, features, metadata, affected_area_km, prediction_type"
                )
                .eq("prediction_type", "spread")
                .execute()
            )
            predictions = preds_resp.data or []
            logger.info(f"Found {len(predictions)} spread predictions")

            if len(predictions) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(predictions)} predictions (minimum 10)",
                }

            # Get disaster data for each prediction
            disaster_ids = list(
                set([p["disaster_id"] for p in predictions if p.get("disaster_id")])
            )
            disasters = {}
            if disaster_ids:
                disasters_resp = (
                    await db_admin.table("disasters")
                    .select("id, type, severity, metadata")
                    .in_("id", disaster_ids)
                    .execute()
                )
                for d in disasters_resp.data or []:
                    disasters[d["id"]] = d

            # Get outcome_tracking for ground truth
            pred_ids = [p["id"] for p in predictions]
            outcomes = {}
            if pred_ids:
                outcomes_resp = (
                    await db_admin.table("outcome_tracking")
                    .select("prediction_id, actual_area_km2")
                    .eq("prediction_type", "spread")
                    .in_("prediction_id", pred_ids)
                    .execute()
                )
                for outcome in outcomes_resp.data or []:
                    outcomes[outcome["prediction_id"]] = outcome

            # Build features
            rows = []
            severity_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}

            for p in predictions:
                if not p.get("disaster_id"):
                    continue

                disaster = disasters.get(p["disaster_id"], {})
                outcome = outcomes.get(p["id"], {})

                # Extract features from metadata JSON
                metadata = p.get("metadata", {}) or {}
                features = p.get("features", {}) or {}

                wind_speed = metadata.get("wind_speed") or features.get("wind_speed", 0)
                current_area = (
                    metadata.get("current_area")
                    or features.get("current_area_km2")
                    or p.get("affected_area_km", 0)
                    or 0
                )

                # Get severity numeric
                severity = disaster.get("severity", "low")
                severity_numeric = severity_map.get(severity.lower(), 0)

                # Get label from outcome or fallback to predicted
                label = outcome.get("actual_area_km2") or p.get("affected_area_km") or 0
                if label <= 0:
                    continue

                row = {
                    "disaster_type": disaster.get("type", "other"),
                    "wind_speed": float(wind_speed) if wind_speed else 0,
                    "current_area": float(current_area) if current_area else 0,
                    "severity_numeric": severity_numeric,
                    "label": float(label),
                }
                rows.append(row)

            if len(rows) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(rows)} valid rows (minimum 10)",
                }

            df = pd.DataFrame(rows)

            # One-hot encode disaster_type
            for dt in DISASTER_TYPES:
                df[f"dtype_{dt}"] = (df["disaster_type"] == dt).astype(float)

            feature_cols = ["wind_speed", "current_area", "severity_numeric"] + [
                f"dtype_{dt}" for dt in DISASTER_TYPES
            ]

            X = df[feature_cols].astype(float)
            y = df["label"].astype(float)

            logger.info(
                f"Spread training data: {len(X)} rows, {len(feature_cols)} features"
            )
            return {"X": X, "y": y, "rows": len(rows)}

        except Exception as e:
            logger.error(f"Error building spread training data: {e}")
            return {"skipped": True, "reason": str(e)}

    async def _build_impact_training_data(self) -> dict[str, Any]:
        """
        Build training data for IMPACT model.

        Query: disasters joined with predictions where prediction_type = 'impact'

        Features: affected_population, severity_numeric, disaster_type (one-hot)
        Label: casualties or estimated_damage from outcome_tracking actual_value
        """
        try:
            # Query predictions of type impact
            preds_resp = (
                await db_admin.table("predictions")
                .select("id, disaster_id, features, metadata, prediction_type")
                .eq("prediction_type", "impact")
                .execute()
            )
            predictions = preds_resp.data or []
            logger.info(f"Found {len(predictions)} impact predictions")

            if len(predictions) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(predictions)} predictions (minimum 10)",
                }

            # Get disaster data
            disaster_ids = list(
                set([p["disaster_id"] for p in predictions if p.get("disaster_id")])
            )
            disasters = {}
            if disaster_ids:
                disasters_resp = (
                    await db_admin.table("disasters")
                    .select("id, type, severity, affected_population, estimated_damage")
                    .in_("id", disaster_ids)
                    .execute()
                )
                for d in disasters_resp.data or []:
                    disasters[d["id"]] = d

            # Get outcome_tracking for ground truth
            pred_ids = [p["id"] for p in predictions]
            outcomes = {}
            if pred_ids:
                outcomes_resp = (
                    await db_admin.table("outcome_tracking")
                    .select("prediction_id, actual_casualties, actual_damage_usd")
                    .eq("prediction_type", "impact")
                    .in_("prediction_id", pred_ids)
                    .execute()
                )
                for outcome in outcomes_resp.data or []:
                    outcomes[outcome["prediction_id"]] = outcome

            # Build features - multi-output: [casualties, damage]
            rows = []
            severity_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}

            for p in predictions:
                if not p.get("disaster_id"):
                    continue

                disaster = disasters.get(p["disaster_id"], {})
                outcome = outcomes.get(p["id"], {})

                # Get features
                affected_pop = disaster.get("affected_population", 0) or 0
                severity = disaster.get("severity", "low")
                severity_numeric = severity_map.get(severity.lower(), 0)

                # Get labels - prefer outcome_tracking, fallback to disaster data
                casualties = (
                    outcome.get("actual_casualties")
                    or disaster.get("casualties", 0)
                    or 0
                )
                damage = (
                    outcome.get("actual_damage_usd")
                    or disaster.get("estimated_damage", 0)
                    or 0
                )

                # Convert damage to millions for consistency
                damage_millions = float(damage) / 1_000_000 if damage else 0

                if affected_pop <= 0 and casualties <= 0 and damage_millions <= 0:
                    continue

                row = {
                    "disaster_type": disaster.get("type", "other"),
                    "affected_population": float(affected_pop),
                    "severity_numeric": severity_numeric,
                    "casualties": float(casualties),
                    "damage_millions": damage_millions,
                }
                rows.append(row)

            if len(rows) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(rows)} valid rows (minimum 10)",
                }

            df = pd.DataFrame(rows)

            # One-hot encode disaster_type
            for dt in DISASTER_TYPES:
                df[f"dtype_{dt}"] = (df["disaster_type"] == dt).astype(float)

            feature_cols = ["affected_population", "severity_numeric"] + [
                f"dtype_{dt}" for dt in DISASTER_TYPES
            ]

            X = df[feature_cols].astype(float)
            y = df[["casualties", "damage_millions"]].astype(float)

            logger.info(
                f"Impact training data: {len(X)} rows, {len(feature_cols)} features, multi-output [casualties, damage]"
            )
            return {"X": X, "y": y, "rows": len(rows)}

        except Exception as e:
            logger.error(f"Error building impact training data: {e}")
            return {"skipped": True, "reason": str(e)}

    async def _build_demand_forecasting_data(self) -> dict[str, Any]:
        """
        Build training data for DEMAND FORECASTING (shortfall) model.

        Query: resource_consumption_log grouped by resource_type and date

        Features: day_of_week, month, resource_type (one-hot), quantity_consumed_yesterday,
                  quantity_consumed_7d_avg
        Label: quantity_consumed_tomorrow (shift by 1 day)
        """
        try:
            # Query resource consumption log
            resp = (
                await db_admin.table("resource_consumption_log")
                .select("id, resource_type, timestamp, quantity_consumed")
                .order("timestamp", desc=False)
                .execute()
            )
            records = resp.data or []
            logger.info(f"Found {len(records)} resource consumption records")

            if len(records) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(records)} records (minimum 10)",
                }

            # Convert to DataFrame and process
            df = pd.DataFrame(records)

            # Parse timestamp
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"])

            # Extract date features
            df["date"] = df["timestamp"].dt.date
            df["day_of_week"] = df["timestamp"].dt.dayofweek + 1  # 1=Monday, 7=Sunday
            df["month"] = df["timestamp"].dt.month

            # Group by resource_type and date to get daily consumption
            daily = (
                df.groupby(["resource_type", "date"])
                .agg({"quantity_consumed": "sum"})
                .reset_index()
            )

            # Sort by resource_type and date
            daily = daily.sort_values(["resource_type", "date"])

            # Create lagged features for each resource_type
            rows = []
            resource_types = daily["resource_type"].unique()

            for rt in resource_types:
                rt_data = daily[daily["resource_type"] == rt].copy()
                rt_data = rt_data.sort_values("date")

                # Create lagged features
                rt_data["quantity_yesterday"] = rt_data["quantity_consumed"].shift(1)
                rt_data["quantity_7d_avg"] = (
                    rt_data["quantity_consumed"]
                    .rolling(window=7, min_periods=1)
                    .mean()
                    .shift(1)
                )
                rt_data["quantity_tomorrow"] = rt_data["quantity_consumed"].shift(-1)

                # Add to rows
                for _, row in rt_data.iterrows():
                    if pd.isna(row["quantity_yesterday"]) or pd.isna(
                        row["quantity_tomorrow"]
                    ):
                        continue

                    # Parse date for features
                    if isinstance(row["date"], str):
                        date_parts = row["date"].split("-")
                        day_of_week = (
                            datetime(
                                int(date_parts[0]),
                                int(date_parts[1]),
                                int(date_parts[2]),
                            ).weekday()
                            + 1
                        )
                        month = int(date_parts[1])
                    else:
                        day_of_week = row["day_of_week"]
                        month = row["month"]

                    rows.append(
                        {
                            "resource_type": rt,
                            "day_of_week": day_of_week,
                            "month": month,
                            "quantity_yesterday": row["quantity_yesterday"],
                            "quantity_7d_avg": (
                                row["quantity_7d_avg"]
                                if not pd.isna(row["quantity_7d_avg"])
                                else row["quantity_yesterday"]
                            ),
                            "quantity_tomorrow": row["quantity_tomorrow"],
                        }
                    )

            if len(rows) < 10:
                return {
                    "skipped": True,
                    "reason": f"Only {len(rows)} valid rows after processing (minimum 10)",
                }

            df = pd.DataFrame(rows)

            # One-hot encode resource_type
            for rt in resource_types:
                df[f"resource_{rt}"] = (df["resource_type"] == rt).astype(float)

            feature_cols = [
                "day_of_week",
                "month",
                "quantity_yesterday",
                "quantity_7d_avg",
            ] + [f"resource_{rt}" for rt in resource_types]

            X = df[feature_cols].astype(float)
            y = df["quantity_tomorrow"].astype(float)

            logger.info(
                f"Demand forecasting training data: {len(X)} rows, {len(feature_cols)} features"
            )
            return {"X": X, "y": y, "rows": len(rows)}

        except Exception as e:
            logger.error(f"Error building demand forecasting data: {e}")
            return {"skipped": True, "reason": str(e)}

    async def _train_model_with_cv(
        self,
        X: pd.DataFrame,
        y: pd.Series | pd.DataFrame,
        model_type: str,
        version: str,
        is_classification: bool = False,
        is_multi_output: bool = False,
    ) -> dict[str, Any]:
        """
        Train model with cross-validation, save to disk, and log to database.

        Args:
            X: Feature DataFrame
            y: Target (Series for single output, DataFrame for multi-output)
            model_type: Type of model (severity, spread, impact, demand_forecasting)
            version: Version timestamp
            is_classification: Whether this is a classification task
            is_multi_output: Whether this is a multi-output regression
        """
        n_samples = len(X)
        cv = 3 if n_samples >= 30 else 2 if n_samples >= 10 else 1

        logger.info(f"Training {model_type} model with {n_samples} samples, cv={cv}")

        # Apply StandardScaler
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Determine model
        if is_classification:
            model = RandomForestClassifier(
                n_estimators=200,
                max_depth=15,
                min_samples_split=4,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            )
            # Cross-validation scoring
            cv_scores = cross_val_score(
                model, X_scaled, y, cv=cv, scoring="f1_weighted"
            )
            cv_mean = float(np.mean(cv_scores))
            cv_std = float(np.std(cv_scores))

            # Fit on full data
            model.fit(X_scaled, y)

            # Save model and scaler
            pipeline = Pipeline([("scaler", scaler), ("clf", model)])
            model_path = self.model_dir / f"{model_type}_model.pkl"
            joblib.dump(pipeline, model_path)

            # Save metadata
            metadata = {
                "model_type": "RandomForestClassifier",
                "n_estimators": 200,
                "train_samples": n_samples,
                "features": list(X.columns),
                "cv_score_mean": cv_mean,
                "cv_score_std": cv_std,
                "cv_folds": cv,
            }
            meta_path = self.model_dir / f"{model_type}_metadata.json"
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2, default=str)

            logger.info(
                f"{model_type} model saved — CV F1: {cv_mean:.4f} ± {cv_std:.4f}"
            )

        else:
            if is_multi_output:
                # Multi-output regression (Impact model)
                base_model = GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=5,
                    learning_rate=0.1,
                    random_state=42,
                )
                model = MultiOutputRegressor(base_model)

                # CV for multi-output - use negative MAE
                cv_scores = cross_val_score(
                    model, X_scaled, y, cv=cv, scoring="neg_mean_absolute_error"
                )
                cv_mean = float(-np.mean(cv_scores))  # Convert to positive MAE
                cv_std = float(np.std(cv_scores))

                # Fit on full data
                model.fit(X_scaled, y)

                # Save model and scaler
                pipeline = Pipeline([("scaler", scaler), ("regressor", model)])
                model_path = self.model_dir / f"{model_type}_model.pkl"
                joblib.dump(pipeline, model_path)

                # Save metadata
                metadata = {
                    "model_type": "MultiOutputRegressor(GradientBoosting)",
                    "n_estimators": 100,
                    "train_samples": n_samples,
                    "features": list(X.columns),
                    "cv_mae_mean": cv_mean,
                    "cv_mae_std": cv_std,
                    "cv_folds": cv,
                }
                meta_path = self.model_dir / f"{model_type}_metadata.json"
                with open(meta_path, "w") as f:
                    json.dump(metadata, f, indent=2, default=str)

                logger.info(
                    f"{model_type} model saved — CV MAE: {cv_mean:.4f} ± {cv_std:.4f}"
                )

            else:
                # Single output regression (Spread, Demand Forecasting)
                model = GradientBoostingRegressor(
                    n_estimators=100,
                    max_depth=5,
                    learning_rate=0.1,
                    random_state=42,
                )

                # CV scoring
                cv_scores = cross_val_score(model, X_scaled, y, cv=cv, scoring="r2")
                cv_mean = float(np.mean(cv_scores))
                cv_std = float(np.std(cv_scores))

                # Fit on full data
                model.fit(X_scaled, y)

                # Save model and scaler
                pipeline = Pipeline([("scaler", scaler), ("regressor", model)])
                model_path = self.model_dir / f"{model_type}_model.pkl"
                joblib.dump(pipeline, model_path)

                # Save metadata
                metadata = {
                    "model_type": "GradientBoostingRegressor",
                    "n_estimators": 100,
                    "train_samples": n_samples,
                    "features": list(X.columns),
                    "cv_r2_mean": cv_mean,
                    "cv_r2_std": cv_std,
                    "cv_folds": cv,
                }
                meta_path = self.model_dir / f"{model_type}_metadata.json"
                with open(meta_path, "w") as f:
                    json.dump(metadata, f, indent=2, default=str)

                logger.info(
                    f"{model_type} model saved — CV R2: {cv_mean:.4f} ± {cv_std:.4f}"
                )

        # Write retraining event to model_evaluation_reports
        await self._log_training_event(
            model_type=model_type,
            training_rows=n_samples,
            cv_score_mean=cv_mean,
            cv_score_std=cv_std,
            version=version,
        )

        return {
            "trained": True,
            "training_rows": n_samples,
            "cv_score_mean": cv_mean,
            "cv_score_std": cv_std,
            "cv_folds": cv,
            "version": version,
        }

    async def _log_training_event(
        self,
        model_type: str,
        training_rows: int,
        cv_score_mean: float,
        cv_score_std: float,
        version: str,
    ):
        """Log a retraining event to the model_evaluation_reports table."""
        try:
            from datetime import date

            record = {
                "report_date": date.today().isoformat(),
                "report_period": "retraining",
                "model_type": model_type,
                "model_version": version,
                "total_predictions": 0,
                "total_with_outcomes": training_rows,
                "accuracy": cv_score_mean if "severity" in model_type else None,
                "mae": (
                    cv_score_mean
                    if model_type in ["spread", "impact", "demand_forecasting"]
                    else None
                ),
                "r_squared": (
                    cv_score_mean
                    if model_type in ["spread", "demand_forecasting"]
                    else None
                ),
                "rmse": None,
                "mape": None,
                "retrain_triggered": True,
            }

            await db_admin.table("model_evaluation_reports").insert(record).execute()
            logger.info(f"Logged training event for {model_type} (version {version})")
        except Exception as e:
            logger.error(f"Failed to log training event: {e}")

    async def _update_manifest(self, version: str, results: dict):
        """Update the model manifest with new version and training results."""
        manifest = {
            "version": version,
            "trained_at": datetime.now(UTC).isoformat(),
            "training_source": "supabase",
            "models": {},
        }

        for model_type, result in results.items():
            if result.get("skipped"):
                manifest["models"][model_type] = {
                    "skipped": True,
                    "reason": result.get("reason"),
                }
            else:
                manifest["models"][model_type] = {
                    "trained": result.get("trained"),
                    "training_rows": result.get("training_rows"),
                    "cv_score_mean": result.get("cv_score_mean"),
                    "cv_score_std": result.get("cv_score_std"),
                }

        manifest_path = self.model_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Manifest updated → {manifest_path}")
