"""
ml/tft_model.py – Temporal Fusion Transformer wrapper for multi-horizon
severity forecasting using pytorch-forecasting.

Provides:
  • build_tft_datasets()         – convert a pandas DataFrame into
                                   pytorch-forecasting TimeSeriesDataSet
  • create_tft_model()           – instantiate a TFT with quantile loss
  • TFTSeverityForecaster class  – high-level wrapper for inference
"""

from __future__ import annotations

import logging
import warnings
from datetime import UTC
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Suppress pytorch-forecasting / lightning verbose warnings during import
warnings.filterwarnings("ignore", category=UserWarning, module="pytorch_forecasting")
warnings.filterwarnings("ignore", category=UserWarning, module="lightning")

# Forecast horizons in hours
FORECAST_HORIZONS = [6, 12, 24, 48]

# Quantiles for uncertainty bands
QUANTILES = [0.1, 0.5, 0.9]

# Severity index to label mapping (matches training data pipeline)
SEVERITY_INV = {0: "low", 1: "medium", 2: "high", 3: "critical"}

# Default model directory
MODEL_DIR = Path(__file__).resolve().parent / "models" / "tft_severity"


# ─── Dataset Construction ───────────────────────────────────────────────────


def build_tft_datasets(
    df: pd.DataFrame,
    max_encoder_length: int = 96,
    max_prediction_length: int = 48,
    val_fraction: float = 0.2,
    batch_size: int = 32,
) -> tuple[Any, Any, Any, Any]:
    """Convert a pandas DataFrame into pytorch-forecasting datasets.

    Uses a time-based split: training covers timesteps up to a cutoff,
    validation predicts the last ``max_prediction_length`` steps per group.
    Both splits see all groups so categorical encodings stay consistent.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: group_id, time_idx, severity_numeric,
        temperature_2m, wind_speed_10m, precipitation, relative_humidity_2m,
        hour_sin, hour_cos, dow_sin, dow_cos, month_sin, month_cos,
        disaster_type, latitude, longitude.
    max_encoder_length : int
        Number of past timesteps the encoder sees.
    max_prediction_length : int
        Number of future timesteps to predict.
    val_fraction : float
        Fraction of each series reserved for validation (by time).
    batch_size : int
        DataLoader batch size.

    Returns
    -------
    training_dataset, validation_dataset, train_dataloader, val_dataloader
    """
    from pytorch_forecasting import TimeSeriesDataSet
    from pytorch_forecasting.data import GroupNormalizer

    df = df.copy()

    # Ensure proper types
    df["group_id"] = df["group_id"].astype(str)
    df["time_idx"] = df["time_idx"].astype(int)
    df["severity_numeric"] = df["severity_numeric"].astype(float)

    # Ensure all weather columns are float
    weather_cols = ["temperature_2m", "wind_speed_10m", "precipitation", "relative_humidity_2m"]
    for col in weather_cols:
        df[col] = df[col].astype(float)

    # Static category: disaster_type
    df["disaster_type"] = df["disaster_type"].astype(str)

    # ── Time-based split ──────────────────────────────────────────────
    # Training uses all data (the model randomly samples encoder→decoder
    # windows).  Validation with predict=True only takes the *last*
    # possible prediction window per group, giving a clean holdout.
    #
    # To create a proper train/val split: truncate training to
    # max_time_idx - max_prediction_length so the last decoder window
    # is reserved for validation.
    max_time_idx = df["time_idx"].max()
    training_cutoff = max_time_idx - max_prediction_length

    train_df = df[df["time_idx"] <= training_cutoff].reset_index(drop=True)

    # Time-varying known reals (cyclical encodings – known at all future times)
    time_varying_known_reals = [
        "time_idx",
        "hour_sin",
        "hour_cos",
        "dow_sin",
        "dow_cos",
        "month_sin",
        "month_cos",
    ]

    # Time-varying unknown reals (weather – only known for past)
    time_varying_unknown_reals = [
        "temperature_2m",
        "wind_speed_10m",
        "precipitation",
        "relative_humidity_2m",
        "severity_numeric",
    ]

    # Static categoricals
    static_categoricals = ["disaster_type"]

    # Static reals
    static_reals = ["latitude", "longitude"]

    training_dataset = TimeSeriesDataSet(
        train_df,
        time_idx="time_idx",
        target="severity_numeric",
        group_ids=["group_id"],
        max_encoder_length=max_encoder_length,
        max_prediction_length=max_prediction_length,
        time_varying_known_reals=time_varying_known_reals,
        time_varying_unknown_reals=time_varying_unknown_reals,
        static_categoricals=static_categoricals,
        static_reals=static_reals,
        target_normalizer=GroupNormalizer(groups=["group_id"], transformation=None),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
        allow_missing_timesteps=True,
    )

    # Validation: full data, predict=True → only the last decoder window
    validation_dataset = TimeSeriesDataSet.from_dataset(
        training_dataset,
        df,
        predict=True,
        stop_randomization=True,
    )

    train_dataloader = training_dataset.to_dataloader(train=True, batch_size=batch_size, num_workers=0)
    val_dataloader = validation_dataset.to_dataloader(train=False, batch_size=batch_size, num_workers=0)

    return training_dataset, validation_dataset, train_dataloader, val_dataloader


# ─── Model Factory ──────────────────────────────────────────────────────────


def create_tft_model(
    training_dataset: Any,
    learning_rate: float = 1e-3,
    hidden_size: int = 32,
    attention_head_size: int = 2,
    dropout: float = 0.1,
    hidden_continuous_size: int = 16,
) -> Any:
    """Create a TemporalFusionTransformer configured for quantile regression.

    Quantile outputs at 10th, 50th, 90th percentile provide uncertainty bands.
    """
    from pytorch_forecasting import TemporalFusionTransformer
    from pytorch_forecasting.metrics import QuantileLoss

    model = TemporalFusionTransformer.from_dataset(
        training_dataset,
        learning_rate=learning_rate,
        hidden_size=hidden_size,
        attention_head_size=attention_head_size,
        dropout=dropout,
        hidden_continuous_size=hidden_continuous_size,
        loss=QuantileLoss(quantiles=QUANTILES),
        optimizer="adam",
        log_interval=10,
        reduce_on_plateau_patience=4,
    )

    logger.info(
        "TFT model created: %d parameters",
        sum(p.numel() for p in model.parameters()),
    )
    return model


# ─── Inference Wrapper ──────────────────────────────────────────────────────


class TFTSeverityForecaster:
    """High-level wrapper for loading a trained TFT and running inference."""

    def __init__(self, model_path: str | Path | None = None):
        self.model = None
        self.model_path = Path(model_path) if model_path else MODEL_DIR / "best_model.ckpt"
        self._loaded = False

    def load(self) -> bool:
        """Load the trained TFT checkpoint. Returns True on success."""
        if self._loaded and self.model is not None:
            return True

        if not self.model_path.exists():
            logger.warning("TFT checkpoint not found at %s", self.model_path)
            return False

        try:
            from pytorch_forecasting import TemporalFusionTransformer

            self.model = TemporalFusionTransformer.load_from_checkpoint(str(self.model_path))
            self.model.eval()
            self._loaded = True
            logger.info("TFT model loaded from %s", self.model_path)
            return True
        except Exception as e:
            logger.error("Failed to load TFT model: %s", e)
            return False

    def predict_from_features(
        self,
        features: dict[str, Any],
    ) -> dict[str, Any]:
        """Run inference on a single feature dict (from the API).

        Constructs a minimal time-series input from the provided weather
        features and returns multi-horizon severity predictions with
        uncertainty bounds.

        Parameters
        ----------
        features : dict
            Keys: temperature, humidity, wind_speed, pressure (or
            temperature_2m, relative_humidity_2m, wind_speed_10m, precipitation).

        Returns
        -------
        dict with keys:
            severity_6h, severity_12h, severity_24h, severity_48h,
            lower_bound, upper_bound, confidence_score, model_version
        """
        if not self._loaded:
            if not self.load():
                return self._fallback_prediction(features)

        try:
            input_df = self._build_input_df(features)
            return self._run_inference(input_df)
        except Exception as e:
            logger.error("TFT inference failed: %s", e)
            return self._fallback_prediction(features)

    def _build_input_df(self, features: dict[str, Any]) -> pd.DataFrame:
        """Build a DataFrame suitable for TFT inference from raw features."""
        import math
        from datetime import datetime, timedelta

        temp = float(features.get("temperature", features.get("temperature_2m", 25)))
        wind = float(features.get("wind_speed", features.get("wind_speed_10m", 15)))
        precip = float(features.get("precipitation", 0))
        humidity = float(features.get("humidity", features.get("relative_humidity_2m", 60)))
        disaster_type = features.get("disaster_type", "other")
        lat = float(features.get("latitude", 0))
        lon = float(features.get("longitude", 0))

        now = datetime.now(UTC)
        rows = []

        # Create 96 timesteps: 48 encoder + 48 decoder
        encoder_len = 48
        decoder_len = 48
        total_steps = encoder_len + decoder_len
        for t in range(total_steps):
            dt = now - timedelta(hours=encoder_len - t)
            hour = dt.hour
            dow = dt.weekday()
            month = dt.month

            # For encoder steps, use provided weather; decoder steps get 0
            if t < encoder_len:
                t_temp = temp
                t_wind = max(0, wind)
                t_precip = max(0, precip)
                t_hum = np.clip(humidity, 0, 100)
                sev = 0.0
            else:
                t_temp = 0.0
                t_wind = 0.0
                t_precip = 0.0
                t_hum = 0.0
                sev = 0.0

            rows.append(
                {
                    "datetime": dt,
                    "temperature_2m": round(t_temp, 1),
                    "wind_speed_10m": round(t_wind, 1),
                    "precipitation": round(t_precip, 2),
                    "relative_humidity_2m": round(t_hum, 1),
                    "hour_sin": round(math.sin(2 * math.pi * hour / 24), 4),
                    "hour_cos": round(math.cos(2 * math.pi * hour / 24), 4),
                    "dow_sin": round(math.sin(2 * math.pi * dow / 7), 4),
                    "dow_cos": round(math.cos(2 * math.pi * dow / 7), 4),
                    "month_sin": round(math.sin(2 * math.pi * month / 12), 4),
                    "month_cos": round(math.cos(2 * math.pi * month / 12), 4),
                    "group_id": "inference_0",
                    "time_idx": t,
                    "severity_numeric": sev,
                    "disaster_type": disaster_type,
                    "latitude": lat,
                    "longitude": lon,
                }
            )

        return pd.DataFrame(rows)

    def _run_inference(self, input_df: pd.DataFrame) -> dict[str, Any]:
        """Run actual TFT inference and extract multi-horizon predictions."""
        from pytorch_forecasting import TimeSeriesDataSet
        from pytorch_forecasting.data import GroupNormalizer

        # Build a dataset matching training schema
        dataset = TimeSeriesDataSet(
            input_df,
            time_idx="time_idx",
            target="severity_numeric",
            group_ids=["group_id"],
            max_encoder_length=48,
            max_prediction_length=48,
            time_varying_known_reals=[
                "time_idx",
                "hour_sin",
                "hour_cos",
                "dow_sin",
                "dow_cos",
                "month_sin",
                "month_cos",
            ],
            time_varying_unknown_reals=[
                "temperature_2m",
                "wind_speed_10m",
                "precipitation",
                "relative_humidity_2m",
                "severity_numeric",
            ],
            static_categoricals=["disaster_type"],
            static_reals=["latitude", "longitude"],
            target_normalizer=GroupNormalizer(groups=["group_id"], transformation=None),
            add_relative_time_idx=True,
            add_target_scales=True,
            add_encoder_length=True,
            allow_missing_timesteps=True,
        )

        dataloader = dataset.to_dataloader(train=False, batch_size=1, num_workers=0)
        predictions = self.model.predict(dataloader, mode="quantiles", return_x=False)

        # predictions shape: (batch, prediction_length, n_quantiles)
        pred = predictions[0].cpu().numpy()  # (48, 3) for quantiles [0.1, 0.5, 0.9]

        # Extract at specific horizons (index = horizon - 1 since prediction starts at t+1)
        horizon_map = {6: 5, 12: 11, 24: 23, 48: 47}

        result = {}
        lower_bounds = {}
        upper_bounds = {}

        for h in FORECAST_HORIZONS:
            idx = horizon_map[h]
            if idx < len(pred):
                q10, q50, q90 = pred[idx]
                # Clamp to valid severity range [0, 3]
                severity_val = float(np.clip(q50, 0, 3))
                severity_int = int(round(severity_val))
                severity_int = min(3, max(0, severity_int))

                result[f"severity_{h}h"] = SEVERITY_INV[severity_int]
                lower_bounds[f"severity_{h}h"] = float(np.clip(q10, 0, 3))
                upper_bounds[f"severity_{h}h"] = float(np.clip(q90, 0, 3))
            else:
                result[f"severity_{h}h"] = "medium"
                lower_bounds[f"severity_{h}h"] = 1.0
                upper_bounds[f"severity_{h}h"] = 1.0

        # Overall confidence: inverse of average uncertainty width
        widths = [upper_bounds[f"severity_{h}h"] - lower_bounds[f"severity_{h}h"] for h in FORECAST_HORIZONS]
        avg_width = np.mean(widths)
        confidence = float(np.clip(1.0 - avg_width / 3.0, 0.1, 0.99))

        return {
            **result,
            "lower_bound": lower_bounds,
            "upper_bound": upper_bounds,
            "confidence_score": round(confidence, 4),
            "model_version": "tft-v1",
            "predicted_severity": result["severity_6h"],  # backwards compat
        }

    @staticmethod
    def _fallback_prediction(features: dict[str, Any]) -> dict[str, Any]:
        """Rule-based fallback when TFT model is unavailable."""

        temp = float(features.get("temperature", features.get("temperature_2m", 25)))
        wind = float(features.get("wind_speed", features.get("wind_speed_10m", 15)))
        humidity = float(features.get("humidity", features.get("relative_humidity_2m", 60)))

        score = (temp * 0.3 + wind * 0.5 + humidity * 0.2) / 100.0
        if score > 0.75:
            sev_idx = 3
        elif score > 0.50:
            sev_idx = 2
        elif score > 0.30:
            sev_idx = 1
        else:
            sev_idx = 0

        sev_label = SEVERITY_INV[sev_idx]

        return {
            "severity_6h": sev_label,
            "severity_12h": sev_label,
            "severity_24h": sev_label,
            "severity_48h": sev_label,
            "lower_bound": {f"severity_{h}h": max(0, sev_idx - 1) for h in FORECAST_HORIZONS},
            "upper_bound": {f"severity_{h}h": min(3, sev_idx + 1) for h in FORECAST_HORIZONS},
            "confidence_score": 0.40,
            "model_version": "fallback",
            "predicted_severity": sev_label,
        }
