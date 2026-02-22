"""
Train a RandomForestClassifier with SMOTE for disaster severity prediction.

Target: >80 % weighted-F1 on held-out test data.
"""

import json
import logging
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

try:
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline as ImbPipeline
    HAS_IMBLEARN = True
except ImportError:
    HAS_IMBLEARN = False

from app.services.training.data_pipeline import load_severity_data, SEVERITY_ORDER

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"


def train_severity_model(
    model_dir: Path | None = None,
    random_state: int = 42,
) -> dict:
    """
    Train, evaluate, and persist the severity prediction model.

    Returns a metrics dict.
    """
    model_dir = model_dir or MODEL_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading severity dataset …")
    X_train, X_test, y_train, y_test = load_severity_data(random_state=random_state)

    logger.info(
        f"Severity data — train: {len(X_train)}, test: {len(X_test)}, "
        f"features: {X_train.shape[1]}"
    )

    # Build pipeline with SMOTE for class imbalance
    if HAS_IMBLEARN:
        logger.info("Using SMOTE for class imbalance handling")
        pipeline = ImbPipeline([
            ("scaler", StandardScaler()),
            ("smote", SMOTE(random_state=random_state, k_neighbors=3)),
            ("clf", RandomForestClassifier(
                n_estimators=500,
                max_depth=25,
                min_samples_split=4,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            )),
        ])
    else:
        logger.warning(
            "imbalanced-learn not installed — falling back to class_weight='balanced'"
        )
        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(
                n_estimators=500,
                max_depth=25,
                min_samples_split=4,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            )),
        ])

    t0 = time.time()
    pipeline.fit(X_train, y_train)
    train_time = round(time.time() - t0, 2)

    y_pred = pipeline.predict(X_test)
    f1_weighted = f1_score(y_test, y_pred, average="weighted")
    f1_macro = f1_score(y_test, y_pred, average="macro")

    report = classification_report(
        y_test, y_pred,
        target_names=SEVERITY_ORDER,
        output_dict=True,
    )

    logger.info(f"Severity model — F1 weighted: {f1_weighted:.4f}, macro: {f1_macro:.4f}")
    logger.info(
        classification_report(y_test, y_pred, target_names=SEVERITY_ORDER)
    )

    # Persist model
    model_path = model_dir / "severity_model.pkl"
    joblib.dump(pipeline, model_path)
    logger.info(f"Model saved → {model_path}")

    # Persist metadata
    feature_names = list(X_train.columns)
    metadata = {
        "model_type": "RandomForestClassifier",
        "smote": HAS_IMBLEARN,
        "n_estimators": 500,
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "features": feature_names,
        "target_names": SEVERITY_ORDER,
        "f1_weighted": round(f1_weighted, 4),
        "f1_macro": round(f1_macro, 4),
        "classification_report": report,
        "train_time_sec": train_time,
    }
    meta_path = model_dir / "severity_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)

    return metadata


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    metrics = train_severity_model()
    print(f"\n✅ Severity model trained — F1 weighted: {metrics['f1_weighted']}")
