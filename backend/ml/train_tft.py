"""
ml/train_tft.py – Training script for the Temporal Fusion Transformer
severity forecaster.

Usage:
    python -m ml.train_tft                    # synthetic data (default)
    python -m ml.train_tft --emdat data.csv   # real EM-DAT data
    python -m ml.train_tft --synthetic --epochs 30 --batch-size 64

Features:
    • Validation loss tracking with early stopping
    • Model checkpoint saving (best epoch)
    • Per-horizon evaluation: MAE, RMSE, coverage probability
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Suppress noisy warnings
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("train_tft")

# Paths
BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models" / "tft_severity"
DATA_DIR = BASE_DIR.parent / "training_data" / "tft_processed"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train TFT severity forecaster")
    p.add_argument("--emdat", type=str, default=None, help="Path to EM-DAT CSV. If omitted, uses synthetic data.")
    p.add_argument("--synthetic", action="store_true", help="Force synthetic dataset generation (no API calls)")
    p.add_argument("--max-events", type=int, default=200, help="Max events to use from EM-DAT (default: 200)")
    p.add_argument("--epochs", type=int, default=20, help="Max training epochs (default: 20)")
    p.add_argument("--batch-size", type=int, default=32, help="Batch size (default: 32)")
    p.add_argument("--lr", type=float, default=1e-3, help="Learning rate (default: 1e-3)")
    p.add_argument("--hidden-size", type=int, default=32, help="TFT hidden size (default: 32)")
    p.add_argument("--gpu", action="store_true", help="Use GPU if available")
    return p.parse_args()


async def prepare_dataset(args: argparse.Namespace) -> pd.DataFrame:
    """Load or generate the TFT training dataset."""
    from ml.data_pipeline import _generate_synthetic_dataset, build_tft_dataset

    cached_path = DATA_DIR / "tft_dataset.parquet"

    if args.synthetic:
        logger.info("Generating synthetic dataset (--synthetic flag)")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return _generate_synthetic_dataset(DATA_DIR, n_events=args.max_events)

    if args.emdat:
        logger.info("Building dataset from EM-DAT CSV: %s", args.emdat)
        return await build_tft_dataset(
            emdat_csv=args.emdat,
            max_events=args.max_events,
            output_dir=DATA_DIR,
        )

    if cached_path.exists():
        logger.info("Loading cached dataset from %s", cached_path)
        return pd.read_parquet(cached_path)

    logger.info("No dataset found. Generating synthetic dataset.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _generate_synthetic_dataset(DATA_DIR, n_events=args.max_events)


def train(args: argparse.Namespace, dataset: pd.DataFrame) -> Path:
    """Train the TFT model and save the best checkpoint.

    Returns the path to the best model checkpoint.
    """
    import lightning.pytorch as pl
    import torch
    from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint

    from ml.tft_model import build_tft_datasets, create_tft_model

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("Dataset: %d rows, %d groups", len(dataset), dataset["group_id"].nunique())

    # Build datasets
    training_dataset, val_dataset, train_dl, val_dl = build_tft_datasets(
        dataset,
        max_encoder_length=48,
        max_prediction_length=48,
        val_fraction=0.2,
        batch_size=args.batch_size,
    )

    logger.info("Training samples: %d, Validation samples: %d", len(training_dataset), len(val_dataset))

    # Create model
    model = create_tft_model(
        training_dataset,
        learning_rate=args.lr,
        hidden_size=args.hidden_size,
        attention_head_size=2,
        dropout=0.1,
        hidden_continuous_size=max(8, args.hidden_size // 2),
    )

    # Callbacks
    early_stop = EarlyStopping(
        monitor="val_loss",
        patience=5,
        mode="min",
        verbose=True,
    )
    checkpoint_cb = ModelCheckpoint(
        dirpath=str(MODEL_DIR),
        filename="best_model",
        monitor="val_loss",
        mode="min",
        save_top_k=1,
        verbose=True,
    )

    # Trainer
    accelerator = "gpu" if (args.gpu and torch.cuda.is_available()) else "cpu"
    trainer = pl.Trainer(
        max_epochs=args.epochs,
        accelerator=accelerator,
        devices=1,
        gradient_clip_val=0.1,
        callbacks=[early_stop, checkpoint_cb],
        enable_progress_bar=True,
        enable_model_summary=True,
        log_every_n_steps=5,
        default_root_dir=str(MODEL_DIR),
    )

    logger.info("Starting training (max %d epochs, %s)…", args.epochs, accelerator)
    trainer.fit(model, train_dataloaders=train_dl, val_dataloaders=val_dl)

    best_path = Path(checkpoint_cb.best_model_path)
    logger.info("Best checkpoint: %s  (val_loss=%.4f)", best_path, checkpoint_cb.best_model_score or 0)

    # Also save as a standard path for the inference wrapper
    standard_path = MODEL_DIR / "best_model.ckpt"
    if best_path != standard_path and best_path.exists():
        import shutil

        shutil.copy2(best_path, standard_path)
        logger.info("Copied best checkpoint → %s", standard_path)

    return standard_path


def evaluate(model_path: Path, dataset: pd.DataFrame) -> None:
    """Evaluate the trained TFT model: MAE, RMSE, coverage probability per horizon."""
    import torch
    from pytorch_forecasting import TemporalFusionTransformer

    from ml.tft_model import FORECAST_HORIZONS, build_tft_datasets

    logger.info("=" * 60)
    logger.info("Model Evaluation")
    logger.info("=" * 60)

    # Load model
    model = TemporalFusionTransformer.load_from_checkpoint(str(model_path))
    model.eval()

    # Build validation dataset
    _, val_dataset, _, val_dl = build_tft_datasets(
        dataset,
        max_encoder_length=48,
        max_prediction_length=48,
        val_fraction=0.2,
        batch_size=32,
    )

    # Get predictions
    predictions = model.predict(val_dl, mode="quantiles", return_x=True)
    pred_values = predictions.output  # (n_samples, pred_length, n_quantiles)
    actuals = torch.cat([y[0] for x, y in iter(val_dl)], dim=0)  # (n_samples, pred_length)

    pred_np = pred_values.cpu().numpy()
    actual_np = actuals.cpu().numpy()

    horizon_indices = {6: 5, 12: 11, 24: 23, 48: 47}

    print("\n" + "=" * 72)
    print(f"{'Horizon':>10s}  {'MAE':>8s}  {'RMSE':>8s}  {'Coverage':>10s}  {'Avg Width':>10s}")
    print("-" * 72)

    for h in FORECAST_HORIZONS:
        idx = horizon_indices[h]
        if idx >= pred_np.shape[1] or idx >= actual_np.shape[1]:
            print(f"  t+{h:2d}h    — not enough prediction steps —")
            continue

        # Quantile predictions: q10=0, q50=1, q90=2
        q10 = pred_np[:, idx, 0]
        q50 = pred_np[:, idx, 1]
        q90 = pred_np[:, idx, 2]
        actual = actual_np[:, idx]

        # MAE and RMSE (against median prediction)
        errors = q50 - actual
        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors**2)))

        # Coverage probability: fraction of actuals within [q10, q90]
        in_interval = (actual >= q10) & (actual <= q90)
        coverage = float(np.mean(in_interval))

        # Average prediction interval width
        avg_width = float(np.mean(q90 - q10))

        print(f"  t+{h:2d}h    {mae:8.4f}  {rmse:8.4f}  {coverage:10.2%}  {avg_width:10.4f}")

    print("=" * 72)

    # Overall summary
    all_q50 = pred_np[:, :, 1].flatten()
    all_actual = actual_np.flatten()
    valid_mask = np.isfinite(all_q50) & np.isfinite(all_actual)
    overall_mae = float(np.mean(np.abs(all_q50[valid_mask] - all_actual[valid_mask])))
    overall_rmse = float(np.sqrt(np.mean((all_q50[valid_mask] - all_actual[valid_mask]) ** 2)))
    print(f"\n  Overall MAE:  {overall_mae:.4f}")
    print(f"  Overall RMSE: {overall_rmse:.4f}")

    # Coverage across all steps
    all_q10 = pred_np[:, :, 0].flatten()[valid_mask]
    all_q90 = pred_np[:, :, 2].flatten()[valid_mask]
    all_act = all_actual[valid_mask]
    overall_coverage = float(np.mean((all_act >= all_q10) & (all_act <= all_q90)))
    print(f"  Overall 80% PI coverage: {overall_coverage:.2%}")
    print("  (target: ~80%)")
    print()


def main() -> None:
    args = parse_args()

    # Phase 1: Prepare data
    logger.info("Phase 1: Preparing dataset")
    dataset = asyncio.run(prepare_dataset(args))

    if dataset is None or len(dataset) == 0:
        logger.error("No dataset available. Aborting.")
        sys.exit(1)

    logger.info("Dataset loaded: %d rows, %d groups", len(dataset), dataset["group_id"].nunique())

    # Phase 2: Train
    logger.info("Phase 2: Training TFT model")
    best_path = train(args, dataset)

    # Phase 3: Evaluate
    logger.info("Phase 3: Evaluating model")
    try:
        evaluate(best_path, dataset)
    except Exception as e:
        logger.error("Evaluation failed: %s", e)
        logger.info("Training completed successfully. Run evaluation separately if needed.")

    logger.info("Done. Model saved to %s", MODEL_DIR)


if __name__ == "__main__":
    main()
