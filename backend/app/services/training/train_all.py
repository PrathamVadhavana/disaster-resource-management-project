"""
Master training script – trains all three models in sequence.

Usage:
    cd backend
    python -m app.services.training.train_all
"""

import logging
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


def train_all(model_dir: Path | None = None) -> dict:
    """
    Train severity, spread, and impact models.

    Returns a summary dict with per-model metrics and version info.
    """
    model_dir = model_dir or MODEL_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    t_total = time.time()

    # 1. Severity
    logger.info("=" * 60)
    logger.info("TRAINING: Severity Predictor (RandomForest + SMOTE)")
    logger.info("=" * 60)
    from app.services.training.train_severity import train_severity_model
    results["severity"] = train_severity_model(model_dir=model_dir)

    # 2. Spread
    logger.info("=" * 60)
    logger.info("TRAINING: Spread Predictor (GradientBoosting)")
    logger.info("=" * 60)
    from app.services.training.train_spread import train_spread_model
    results["spread"] = train_spread_model(model_dir=model_dir)

    # 3. Impact
    logger.info("=" * 60)
    logger.info("TRAINING: Impact Predictor (XGBoost multi-output)")
    logger.info("=" * 60)
    from app.services.training.train_impact import train_impact_model
    results["impact"] = train_impact_model(model_dir=model_dir)

    total_time = round(time.time() - t_total, 2)

    # Write combined manifest
    version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest = {
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "total_train_time_sec": total_time,
        "models": {
            "severity": {
                "file": "severity_model.pkl",
                "f1_weighted": results["severity"].get("f1_weighted"),
            },
            "spread": {
                "file": "spread_model.pkl",
                "r2": results["spread"].get("r2"),
                "mae": results["spread"].get("mae"),
            },
            "impact": {
                "file": "impact_model.pkl",
                "metrics": results["impact"].get("metrics"),
            },
        },
    }
    manifest_path = model_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"ALL MODELS TRAINED — version {version} ({total_time}s)")
    logger.info(f"Manifest → {manifest_path}")
    logger.info(f"{'=' * 60}")

    return manifest


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )
    manifest = train_all()
    print(json.dumps(manifest, indent=2))
