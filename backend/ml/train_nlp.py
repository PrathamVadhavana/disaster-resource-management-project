"""
train_nlp.py – Fine-tune DistilBERT on CrisisNLP for 4-class urgency classification.

=== CrisisNLP Dataset ===
Download from: https://crisisnlp.qcri.org/lrec2016/lrec2016.html
Direct link  : https://crisisnlp.qcri.org/data/lrec2016/CrisisNLP_labeled_data_crowdflower.zip

After downloading:
  1. Unzip to  backend/ml/data/CrisisNLP_labeled_data_crowdflower/
  2. The folder should contain CSV files per disaster event.
  3. Run this script:  python -m ml.train_nlp

If you don't have the dataset yet, the script can generate synthetic training
data so you can verify the pipeline works end-to-end (use --synthetic flag).

Output:
  backend/ml/models/distilbert-crisis-urgency/   (saved model + tokenizer)
  backend/ml/models/label_map.json               (label ↔ id mapping)
  Prints sklearn classification report (precision / recall / F1 per class).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LABEL_MAP = {"critical": 0, "high": 1, "medium": 2, "low": 3}
ID_TO_LABEL = {v: k for k, v in LABEL_MAP.items()}
NUM_LABELS = len(LABEL_MAP)

# CrisisNLP original labels → our 4-class mapping
CRISISNLP_LABEL_MAP: dict[str, str] = {
    # Infrastructure / Utilities → medium
    "infrastructure_and_utilities_damage":        "medium",
    "infrastructure damage":                      "medium",
    # Injured / dead / found → critical
    "injured_or_dead_people":                     "critical",
    "injured or dead people":                     "critical",
    "dead":                                       "critical",
    "deaths":                                     "critical",
    "injured":                                    "high",
    # Missing / trapped → critical
    "missing_trapped_or_found_people":            "critical",
    "missing, trapped, or found people":          "critical",
    "missing people":                             "critical",
    # Displaced → high
    "displaced_and_evacuations":                  "high",
    "displaced people and evacuations":           "high",
    "displaced":                                  "high",
    "evacuation":                                 "high",
    # Donation / volunteer → low
    "donation_and_volunteering":                  "low",
    "donations and volunteering":                 "low",
    "money":                                      "low",
    "volunteer":                                  "low",
    "donation_needs_or_offers_or_டn_response":    "low",
    # Sympathy / emotional → low
    "sympathy_and_emotional_support":             "low",
    "sympathy and emotional support":             "low",
    "sympathy":                                   "low",
    "prayers":                                    "low",
    # Caution / advice → medium
    "caution_and_advice":                         "medium",
    "caution and advice":                         "medium",
    "advice":                                     "medium",
    "warnings":                                   "medium",
    # Other useful → medium
    "other_useful_info":                          "medium",
    "other useful information":                   "medium",
    "useful information":                         "medium",
    "informative":                                "medium",
    "information":                                "medium",
    # Not labelled / irrelevant → low
    "not_related_or_irrelevant":                  "low",
    "not related or irrelevant":                  "low",
    "not applicable":                             "low",
    "irrelevant":                                 "low",
    "not related":                                "low",
    "not_labeled":                                "low",
    # Requests → high
    "requests_or_urgent_needs":                   "high",
    "needs":                                      "high",
    "urgent needs":                               "critical",
    "request":                                    "high",
    "search and rescue":                          "critical",
    # Affected individuals → high
    "affected_individuals":                       "high",
    "affected individuals":                       "high",
    "affected":                                   "high",
    # Personal → low
    "personal":                                   "low",
    "personal only":                              "low",
}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "CrisisNLP_labeled_data_crowdflower"
MODEL_DIR = BASE_DIR / "models" / "distilbert-crisis-urgency"


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_crisisnlp_data(data_dir: Path) -> pd.DataFrame:
    """Load and merge all CrisisNLP CSV files into a single DataFrame.

    Expected CSV columns (may vary by file):
      - 'tweet_text' or 'text'  → free-text description
      - 'label' or 'class_label' or 'choose_one_category' → original class
    """
    all_rows: list[dict] = []
    csv_files = list(data_dir.rglob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found in {data_dir}. "
            "Download CrisisNLP data first — see docstring at the top of this file."
        )
    logger.info("Found %d CSV files in %s", len(csv_files), data_dir)

    for csv_path in csv_files:
        try:
            df = pd.read_csv(csv_path, encoding="utf-8", on_bad_lines="skip")
        except Exception:
            try:
                df = pd.read_csv(csv_path, encoding="latin-1", on_bad_lines="skip")
            except Exception as e:
                logger.warning("Skipping %s: %s", csv_path.name, e)
                continue

        # Identify text column
        text_col = None
        for candidate in ("tweet_text", "text", "tweet", "message", "content"):
            if candidate in df.columns:
                text_col = candidate
                break
        if text_col is None:
            # Fall back to first non-label string column
            for col in df.columns:
                if col.lower() not in ("label", "class_label", "choose_one_category", "class"):
                    if df[col].dtype == object:
                        text_col = col
                        break
        if text_col is None:
            logger.warning("Skipping %s: no text column detected", csv_path.name)
            continue

        # Identify label column
        label_col = None
        for candidate in ("label", "class_label", "choose_one_category", "class", "category"):
            if candidate in df.columns:
                label_col = candidate
                break
        if label_col is None:
            logger.warning("Skipping %s: no label column detected", csv_path.name)
            continue

        for _, row in df.iterrows():
            text = str(row[text_col]).strip()
            raw_label = str(row[label_col]).strip().lower().replace(" ", "_")
            if not text or text.lower() == "nan" or len(text) < 10:
                continue
            mapped = CRISISNLP_LABEL_MAP.get(raw_label)
            if mapped is None:
                # Try partial match
                for key, val in CRISISNLP_LABEL_MAP.items():
                    if key in raw_label or raw_label in key:
                        mapped = val
                        break
            if mapped is None:
                mapped = "medium"  # default fallback
            all_rows.append({"text": text, "label": mapped})

    df_out = pd.DataFrame(all_rows)
    logger.info(
        "Loaded %d samples. Distribution:\n%s",
        len(df_out),
        df_out["label"].value_counts().to_string(),
    )
    return df_out


def generate_synthetic_data(n_per_class: int = 500) -> pd.DataFrame:
    """Generate synthetic training data for pipeline testing."""
    templates: dict[str, list[str]] = {
        "critical": [
            "People are trapped under collapsed building, need immediate rescue",
            "Multiple casualties, severe injuries, need ambulance now",
            "Children drowning in floodwater, please send help immediately",
            "Elderly person unconscious and not breathing, cardiac arrest",
            "Heavy bleeding from crush injury, no medical supplies available",
            "Family buried under rubble for 2 days, running out of air",
            "Pregnant woman in labor with no medical assistance available",
            "Gas leak causing explosions, people trapped inside building",
            "Bridge collapsed with vehicles, multiple people in river",
            "Infant not breathing after being pulled from debris",
        ],
        "high": [
            "We have been without water for 3 days, children are dehydrated",
            "Need medical attention for infected wound, fever getting worse",
            "Displaced family of 8 with no shelter, rain expected tonight",
            "Running out of insulin, diabetic patient needs medication urgently",
            "Roof collapsed, family exposed to elements, need temporary shelter",
            "Evacuation needed, water levels rising rapidly in our area",
            "Elderly residents stranded on second floor, mobility issues",
            "Food supplies exhausted for community of 50 people",
            "Road blocked by landslide, village cut off from supplies",
            "Multiple families with small children need evacuation transport",
        ],
        "medium": [
            "We need food supplies for our shelter, running low on rations",
            "Request for blankets and warm clothing for displaced families",
            "Infrastructure damage to water pipeline, need repair assistance",
            "Need tents for temporary housing, current shelter is overcrowded",
            "Medical supplies running low at local clinic, need resupply",
            "Power lines down in residential area, need utility repair",
            "Roads damaged, need heavy equipment for debris clearance",
            "Community kitchen running low on cooking fuel and utensils",
            "Need water purification tablets for contaminated well water",
            "School building partially damaged, need structural assessment",
        ],
        "low": [
            "Want to volunteer for disaster relief, have medical training",
            "Offering donation of clothing and household items",
            "Requesting information about relief distribution schedule",
            "Prayers and support for all affected families",
            "Looking for updates on power restoration timeline",
            "Want to donate money to relief fund, how can I contribute",
            "Sharing safety tips for earthquake preparedness",
            "Thank you to all volunteers working in the relief camps",
            "Requesting information about shelter locations for future reference",
            "Offering free counseling services for trauma support",
        ],
    }

    rows = []
    for label, tmpls in templates.items():
        for i in range(n_per_class):
            base = random.choice(tmpls)
            # Add slight variation
            noise_words = [
                "please", "urgently", "ASAP", "help", "SOS",
                "desperate", "emergency", "request", "need", "",
            ]
            prefix = random.choice(["", "", "", f"{random.choice(noise_words)} - "])
            suffix = random.choice(
                ["", "", f" ({random.randint(1, 20)} people)", " #disaster", " #help"]
            )
            rows.append({"text": f"{prefix}{base}{suffix}", "label": label})

    df = pd.DataFrame(rows)
    logger.info(
        "Generated %d synthetic samples. Distribution:\n%s",
        len(df),
        df["label"].value_counts().to_string(),
    )
    return df


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    data_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    synthetic: bool = False,
    epochs: int = 4,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    max_length: int = 128,
    test_size: float = 0.2,
    seed: int = 42,
) -> None:
    """Fine-tune DistilBERT for 4-class urgency classification."""

    # ── Guard: check torch + transformers are installed ──
    try:
        import torch
        from transformers import (
            DistilBertTokenizerFast,
            DistilBertForSequenceClassification,
            Trainer,
            TrainingArguments,
            EarlyStoppingCallback,
        )
        from datasets import Dataset
    except ImportError as e:
        logger.error(
            "Missing dependency: %s\n"
            "Install with: pip install torch transformers datasets",
            e,
        )
        sys.exit(1)

    data_dir = data_dir or DATA_DIR
    output_dir = output_dir or MODEL_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    # ── Load data ──
    if synthetic:
        logger.info("Using SYNTHETIC training data (for pipeline testing only)")
        df = generate_synthetic_data(n_per_class=600)
    else:
        df = load_crisisnlp_data(data_dir)

    if len(df) < 100:
        logger.error("Too few samples (%d). Need at least 100.", len(df))
        sys.exit(1)

    # Encode labels
    df["label_id"] = df["label"].map(LABEL_MAP)
    df = df.dropna(subset=["label_id"])
    df["label_id"] = df["label_id"].astype(int)

    # Stratified split
    train_df, test_df = train_test_split(
        df, test_size=test_size, random_state=seed, stratify=df["label_id"]
    )
    logger.info("Train: %d  |  Test: %d", len(train_df), len(test_df))

    # ── Tokeniser ──
    model_name = "distilbert-base-uncased"
    tokenizer = DistilBertTokenizerFast.from_pretrained(model_name)

    def tokenize_fn(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            padding="max_length",
            max_length=max_length,
        )

    train_ds = Dataset.from_pandas(train_df[["text", "label_id"]].rename(columns={"label_id": "labels"}))
    test_ds = Dataset.from_pandas(test_df[["text", "label_id"]].rename(columns={"label_id": "labels"}))

    train_ds = train_ds.map(tokenize_fn, batched=True, remove_columns=["text"])
    test_ds = test_ds.map(tokenize_fn, batched=True, remove_columns=["text"])

    train_ds.set_format("torch")
    test_ds.set_format("torch")

    # ── Model ──
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("Training on device: %s", device)

    model = DistilBertForSequenceClassification.from_pretrained(
        model_name,
        num_labels=NUM_LABELS,
        id2label=ID_TO_LABEL,
        label2id=LABEL_MAP,
    )

    # ── Metrics ──
    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        acc = (preds == labels).mean()
        return {"accuracy": float(acc)}

    # ── Training arguments ──
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_steps=int(0.1 * epochs * (len(train_ds) // batch_size + 1)),
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        logging_steps=50,
        save_total_limit=2,
        fp16=torch.cuda.is_available(),
        report_to="none",
        seed=seed,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=test_ds,
        processing_class=tokenizer,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    # ── Train ──
    logger.info("Starting fine-tuning of %s …", model_name)
    trainer.train()

    # ── Save model + tokenizer ──
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # Save label map
    label_map_path = output_dir.parent / "label_map.json"
    with open(label_map_path, "w") as f:
        json.dump({"label2id": LABEL_MAP, "id2label": ID_TO_LABEL}, f, indent=2)
    logger.info("Model saved to %s", output_dir)
    logger.info("Label map saved to %s", label_map_path)

    # ── Evaluation ──
    logger.info("\n" + "=" * 60)
    logger.info("MODEL EVALUATION")
    logger.info("=" * 60)

    predictions_output = trainer.predict(test_ds)
    preds = np.argmax(predictions_output.predictions, axis=-1)
    true_labels = test_df["label_id"].values

    target_names = [ID_TO_LABEL[i] for i in range(NUM_LABELS)]
    report = classification_report(
        true_labels,
        preds,
        target_names=target_names,
        digits=4,
    )
    print("\n" + report)
    logger.info("Classification Report:\n%s", report)

    # Save report to file
    report_path = output_dir.parent / "evaluation_report.txt"
    with open(report_path, "w") as f:
        f.write(f"Model: {model_name} fine-tuned on CrisisNLP\n")
        f.write(f"Train samples: {len(train_df)}  |  Test samples: {len(test_df)}\n")
        f.write(f"Epochs: {epochs}  |  Batch size: {batch_size}  |  LR: {learning_rate}\n")
        f.write(f"Max length: {max_length}\n\n")
        f.write(report)
    logger.info("Evaluation report saved to %s", report_path)
    logger.info("Done!")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fine-tune DistilBERT on CrisisNLP for urgency classification"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Path to CrisisNLP CSV directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MODEL_DIR,
        help="Where to save the fine-tuned model",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic data instead of CrisisNLP (for testing the pipeline)",
    )
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    train(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        synthetic=args.synthetic,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        max_length=args.max_length,
        test_size=args.test_size,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
