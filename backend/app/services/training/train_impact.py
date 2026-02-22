"""
Train a multi-output XGBoost regressor predicting casualties and economic damage.

Uses leave-one-disaster-out cross-validation to prevent data leakage,
then trains the final model on the full training set.
"""

import json
import logging
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    from sklearn.ensemble import GradientBoostingRegressor

from app.services.training.data_pipeline import load_impact_data, DISASTER_TYPES

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


def _leave_one_disaster_out_cv(X: pd.DataFrame, y: pd.DataFrame, pipeline) -> dict:
    """
    Cross-validate by leaving each disaster-type cluster out.

    Returns aggregated metrics.
    """
    dtype_cols = [c for c in X.columns if c.startswith("dtype_")]
    all_mae_cas, all_mae_dmg = [], []

    for dt in DISASTER_TYPES:
        col = f"dtype_{dt}"
        if col not in X.columns:
            continue
        mask = X[col] == 1
        if mask.sum() < 10:
            continue

        X_train_cv = X[~mask]
        y_train_cv = y[~mask]
        X_val = X[mask]
        y_val = y[mask]

        from sklearn.base import clone
        fold_pipeline = clone(pipeline)
        fold_pipeline.fit(X_train_cv, y_train_cv)
        y_pred = fold_pipeline.predict(X_val)

        if isinstance(y_pred, np.ndarray) and y_pred.ndim == 2:
            all_mae_cas.append(mean_absolute_error(y_val.iloc[:, 0], y_pred[:, 0]))
            all_mae_dmg.append(mean_absolute_error(y_val.iloc[:, 1], y_pred[:, 1]))

    return {
        "loo_cv_mae_casualties": round(float(np.mean(all_mae_cas)), 2) if all_mae_cas else None,
        "loo_cv_mae_damage": round(float(np.mean(all_mae_dmg)), 2) if all_mae_dmg else None,
    }


def train_impact_model(
    model_dir: Path | None = None,
    random_state: int = 42,
) -> dict:
    """
    Train, evaluate, and persist the impact prediction model.

    Returns a metrics dict.
    """
    model_dir = model_dir or MODEL_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading impact dataset …")
    X_train, X_test, y_train, y_test = load_impact_data(random_state=random_state)

    logger.info(
        f"Impact data — train: {len(X_train)}, test: {len(X_test)}, "
        f"features: {X_train.shape[1]}, targets: {y_train.shape[1]}"
    )

    # Build pipeline
    if HAS_XGB:
        logger.info("Using XGBRegressor (multi-output)")
        base_reg = XGBRegressor(
            n_estimators=300,
            max_depth=7,
            learning_rate=0.08,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=random_state,
            n_jobs=-1,
            verbosity=0,
        )
    else:
        logger.warning("xgboost not installed — falling back to GradientBoostingRegressor")
        base_reg = GradientBoostingRegressor(
            n_estimators=300,
            max_depth=7,
            learning_rate=0.08,
            subsample=0.8,
            random_state=random_state,
        )

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("reg", MultiOutputRegressor(base_reg)),
    ])

    # Leave-one-disaster-out CV
    logger.info("Running leave-one-disaster-out cross-validation …")
    cv_metrics = _leave_one_disaster_out_cv(X_train, y_train, pipeline)
    logger.info(f"LOO-CV metrics: {cv_metrics}")

    # Final training on full train set
    t0 = time.time()
    pipeline.fit(X_train, y_train)
    train_time = round(time.time() - t0, 2)

    y_pred = pipeline.predict(X_test)

    # Per-target metrics
    targets = list(y_train.columns)
    metrics_per_target = {}
    for i, tgt in enumerate(targets):
        mae = mean_absolute_error(y_test.iloc[:, i], y_pred[:, i])
        rmse = np.sqrt(mean_squared_error(y_test.iloc[:, i], y_pred[:, i]))
        r2 = r2_score(y_test.iloc[:, i], y_pred[:, i])
        metrics_per_target[tgt] = {
            "mae": round(float(mae), 4),
            "rmse": round(float(rmse), 4),
            "r2": round(float(r2), 4),
        }
        logger.info(f"  {tgt} — MAE: {mae:.2f}, RMSE: {rmse:.2f}, R²: {r2:.4f}")

    # Persist
    joblib.dump(pipeline, model_dir / "impact_model.pkl")
    logger.info(f"Impact model saved → {model_dir}")

    feature_names = list(X_train.columns)
    metadata = {
        "model_type": "XGBRegressor (multi-output)" if HAS_XGB else "GBR (multi-output)",
        "n_estimators": 300,
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "features": feature_names,
        "targets": targets,
        "metrics": metrics_per_target,
        "cv_metrics": cv_metrics,
        "train_time_sec": train_time,
    }
    with open(model_dir / "impact_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    metrics = train_impact_model()
    print(f"\n✅ Impact model trained — {json.dumps(metrics['metrics'], indent=2)}")
