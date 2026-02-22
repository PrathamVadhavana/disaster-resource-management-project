"""
Train a GradientBoostingRegressor for disaster spread (area) prediction.

Output: predicted affected km² with confidence interval.
"""

import json
import logging
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.services.training.data_pipeline import load_spread_data

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


def train_spread_model(
    model_dir: Path | None = None,
    random_state: int = 42,
) -> dict:
    """
    Train, evaluate, and persist the spread prediction model.

    Also trains upper/lower quantile regressors for confidence intervals.
    Returns a metrics dict.
    """
    model_dir = model_dir or MODEL_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading spread dataset …")
    X_train, X_test, y_train, y_test = load_spread_data(random_state=random_state)

    logger.info(
        f"Spread data — train: {len(X_train)}, test: {len(X_test)}, "
        f"features: {X_train.shape[1]}"
    )

    # ── Mean predictor ────────────────────────────────────────────────────
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("reg", GradientBoostingRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.8,
            min_samples_leaf=5,
            random_state=random_state,
        )),
    ])

    t0 = time.time()
    pipeline.fit(X_train, y_train)
    train_time = round(time.time() - t0, 2)

    y_pred = pipeline.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    logger.info(f"Spread model — MAE: {mae:.2f}, RMSE: {rmse:.2f}, R²: {r2:.4f}")

    # ── Quantile regressors for confidence interval ───────────────────────
    lower_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("reg", GradientBoostingRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.08,
            loss="quantile",
            alpha=0.1,
            random_state=random_state,
        )),
    ])
    upper_pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("reg", GradientBoostingRegressor(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.08,
            loss="quantile",
            alpha=0.9,
            random_state=random_state,
        )),
    ])

    lower_pipeline.fit(X_train, y_train)
    upper_pipeline.fit(X_train, y_train)

    # Persist
    joblib.dump(pipeline, model_dir / "spread_model.pkl")
    joblib.dump(lower_pipeline, model_dir / "spread_lower.pkl")
    joblib.dump(upper_pipeline, model_dir / "spread_upper.pkl")
    logger.info(f"Spread models saved → {model_dir}")

    feature_names = list(X_train.columns)
    metadata = {
        "model_type": "GradientBoostingRegressor",
        "n_estimators": 300,
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "features": feature_names,
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
        "train_time_sec": train_time,
    }
    with open(model_dir / "spread_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    metrics = train_spread_model()
    print(f"\n✅ Spread model trained — R²: {metrics['r2']}, MAE: {metrics['mae']}")
