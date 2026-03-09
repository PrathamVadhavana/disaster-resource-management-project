"""
ml/nlp_service.py – DistilBERT-backed NLP priority scoring service.

Provides three core functions consumed by the victim-request endpoint:
  1. predict_priority(description)       → { predicted_priority, confidence }
  2. extract_needs(description)          → [ { resource_type, quantity, sub_type } ]
  3. find_semantic_duplicates(new, existing) → [ duplicate_id_indices ]

The module lazy-loads the fine-tuned model on first call so it does NOT block
application startup when the model files are missing (falls back gracefully to
the existing rule-based NLP service).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent
_MODEL_DIR = _BASE_DIR / "models" / "distilbert-crisis-urgency"
_LABEL_MAP_PATH = _BASE_DIR / "models" / "label_map.json"

# ---------------------------------------------------------------------------
# Lazy-loaded singletons (populated by _ensure_model / _ensure_embedder)
# ---------------------------------------------------------------------------
_model = None
_tokenizer = None
_label_map: dict[int, str] = {0: "critical", 1: "high", 2: "medium", 3: "low"}
_model_load_attempted = False

_embedder_model = None
_embedder_load_attempted = False


# ---------------------------------------------------------------------------
# Model loading helpers
# ---------------------------------------------------------------------------

def _ensure_model() -> bool:
    """Load the fine-tuned DistilBERT model + tokenizer (once).

    Returns True when the model is ready, False on failure.
    """
    global _model, _tokenizer, _label_map, _model_load_attempted

    if _model is not None:
        return True
    if _model_load_attempted:
        return False  # already tried and failed

    _model_load_attempted = True

    try:
        import torch
        from transformers import (
            DistilBertForSequenceClassification,
            DistilBertTokenizerFast,
        )
    except ImportError:
        logger.warning(
            "torch / transformers not installed – "
            "DistilBERT NLP service unavailable (falling back to rule-based)."
        )
        return False

    if not _MODEL_DIR.exists():
        logger.warning(
            "Fine-tuned model not found at %s – "
            "run `python -m ml.train_nlp` first. Falling back to rule-based.",
            _MODEL_DIR,
        )
        return False

    try:
        _tokenizer = DistilBertTokenizerFast.from_pretrained(str(_MODEL_DIR))
        _model = DistilBertForSequenceClassification.from_pretrained(str(_MODEL_DIR))
        _model.eval()

        # Load label map if available
        if _LABEL_MAP_PATH.exists():
            with open(_LABEL_MAP_PATH) as f:
                lm = json.load(f)
                _label_map = {int(k): v for k, v in lm.get("id2label", _label_map).items()}

        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model.to(device)
        logger.info("DistilBERT crisis model loaded on %s", device)
        return True
    except Exception as exc:
        logger.error("Failed to load DistilBERT model: %s", exc)
        _model = None
        _tokenizer = None
        return False


def _ensure_embedder() -> bool:
    """Load a sentence-transformer model for semantic similarity (once).

    Uses distilbert-base-nli-stsb-mean-tokens for lightweight embeddings.
    Falls back to TF-IDF if unavailable.
    """
    global _embedder_model, _embedder_load_attempted

    if _embedder_model is not None:
        return True
    if _embedder_load_attempted:
        return False

    _embedder_load_attempted = True

    try:
        from sentence_transformers import SentenceTransformer

        _embedder_model = SentenceTransformer("distilbert-base-nli-stsb-mean-tokens")
        logger.info("Sentence-transformer loaded for duplicate detection")
        return True
    except ImportError:
        logger.warning(
            "sentence-transformers not installed – "
            "duplicate detection will use TF-IDF cosine similarity."
        )
        return False
    except Exception as exc:
        logger.error("Failed to load sentence-transformer: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 1. predict_priority
# ---------------------------------------------------------------------------

def predict_priority(description: str) -> dict[str, Any]:
    """Predict urgency class for a free-text disaster request.

    Returns
    -------
    dict
        {
            "predicted_priority": "critical" | "high" | "medium" | "low",
            "confidence": float (0-1),
            "probabilities": { "critical": float, "high": float, ... },
            "model": "distilbert" | "rule-based",
        }
    """
    if not description or not description.strip():
        return {
            "predicted_priority": "medium",
            "confidence": 0.0,
            "probabilities": {},
            "model": "none",
        }

    # ── Try DistilBERT first ──
    if _ensure_model():
        return _predict_with_distilbert(description)

    # ── Fallback: rule-based (reuse existing nlp_service) ──
    return _predict_rule_based(description)


def _predict_with_distilbert(text: str) -> dict[str, Any]:
    """Run inference through the fine-tuned DistilBERT model."""
    import torch

    inputs = _tokenizer(
        text,
        truncation=True,
        padding="max_length",
        max_length=128,
        return_tensors="pt",
    )
    device = next(_model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        logits = _model(**inputs).logits

    probs = torch.nn.functional.softmax(logits, dim=-1).squeeze().cpu().numpy()
    pred_id = int(np.argmax(probs))
    confidence = float(probs[pred_id])
    predicted_label = _label_map.get(pred_id, "medium")

    probabilities = {
        _label_map.get(i, f"class_{i}"): round(float(probs[i]), 4)
        for i in range(len(probs))
    }

    return {
        "predicted_priority": predicted_label,
        "confidence": round(confidence, 4),
        "probabilities": probabilities,
        "model": "distilbert",
    }


def _predict_rule_based(text: str) -> dict[str, Any]:
    """Lightweight rule-based fallback using the existing keyword banks."""
    from app.services.nlp_service import (
        extract_urgency_signals,
        escalate_priority,
    )

    signals = extract_urgency_signals(text)
    priority, _ = escalate_priority("medium", signals)

    # Derive rough confidence from signal strength
    if not signals:
        confidence = 0.35
    else:
        max_boost = max(s.severity_boost for s in signals)
        confidence = min(0.4 + max_boost * 0.15 + len(signals) * 0.05, 0.80)

    return {
        "predicted_priority": priority,
        "confidence": round(confidence, 4),
        "probabilities": {},
        "model": "rule-based",
    }


# ---------------------------------------------------------------------------
# 2. extract_needs
# ---------------------------------------------------------------------------

# Detailed resource extraction patterns: (regex, resource_type, sub_type_label)
_NEED_PATTERNS: list[tuple[str, str, str]] = [
    # Water
    (r"(\d+)\s*(bottles?|gallons?|liters?|litres?)\s*(of\s+)?(clean\s+)?water", "Water", "drinking_water"),
    (r"(clean|drinking|potable)\s+water", "Water", "drinking_water"),
    (r"water\s+(purif|filter|tablet)", "Water", "purification"),
    (r"\bwater\b", "Water", "general"),
    # Food
    (r"(\d+)\s*(meals?|rations?|food\s+packs?|boxes?\s+of\s+food)", "Food", "prepared_meals"),
    (r"(canned|dry|non.?perishable)\s+food", "Food", "non_perishable"),
    (r"(baby|infant)\s+food", "Food", "baby_food"),
    (r"(rice|bread|grain|flour|wheat)", "Food", "staples"),
    (r"\bfood\b", "Food", "general"),
    # Medical
    (r"(ambulance|paramedic|ems)", "Medical", "emergency_transport"),
    (r"(first\s*aid\s+kit|bandage|gauze|antiseptic)", "Medical", "first_aid"),
    (r"(insulin|inhaler|epinephrine|epipen)", "Medical", "chronic_medication"),
    (r"(antibiotic|medicine|medication|drug|pharma)", "Medical", "medication"),
    (r"(doctor|nurse|medic|surgeon)", "Medical", "personnel"),
    (r"\bmedical\b", "Medical", "general"),
    # Shelter
    (r"(\d+)\s*(tents?|tarps?|shelters?)", "Shelter", "tent"),
    (r"(blanket|sleeping\s+bag|mattress)", "Shelter", "bedding"),
    (r"(temporary|emergency)\s+(housing|shelter)", "Shelter", "temporary_housing"),
    (r"\bshelter\b", "Shelter", "general"),
    # Clothing
    (r"(warm|winter)\s+(cloth|jacket|coat)", "Clothing", "winter_wear"),
    (r"(diaper|nappy)", "Clothing", "baby_supplies"),
    (r"(shoe|boot|footwear)", "Clothing", "footwear"),
    (r"\bcloth(es|ing)\b", "Clothing", "general"),
    # Evacuation
    (r"(evacuat|airlift|rescue\s+team)", "Evacuation", "rescue"),
    (r"(transport|vehicle|bus|truck|boat|helicopter)", "Evacuation", "transport"),
    # Financial
    (r"(cash|money|financial|monetary|fund)", "Financial Aid", "monetary"),
    # Volunteers
    (r"(volunteer|helper|manpower|personnel)", "Volunteers", "general"),
]

# Quantity extraction patterns per resource mention
_QTY_PATTERNS = [
    r"(\d+)\s*(bottles?|gallons?|liters?|litres?|packs?|boxes?|bags?|kits?|units?|tents?|blankets?|meals?|rations?|cans?|cases?|sets?|pairs?)",
    r"(\d+)\s*(people|persons?|families?|children|kids|adults?)",
    r"need\s+(\d+)",
    r"(\d+)\s+of\s+",
]


def extract_needs(description: str) -> list[dict[str, Any]]:
    """Extract structured resource needs from free-text description.

    Returns
    -------
    list[dict]
        [
            {
                "resource_type": "Water",
                "quantity": 10,
                "sub_type": "drinking_water"
            },
            ...
        ]
    """
    if not description or not description.strip():
        return []

    text_lower = description.lower()
    seen_types: dict[str, dict] = {}  # resource_type → best match info

    for pattern, resource_type, sub_type in _NEED_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            # Extract quantity if present in the match
            quantity = 1
            for group in match.groups():
                if group and group.isdigit():
                    quantity = max(quantity, int(group))
                    break

            # If no quantity in this pattern, scan surrounding context
            if quantity == 1:
                # Look for quantity near this match (within 60 chars)
                start = max(0, match.start() - 60)
                end = min(len(text_lower), match.end() + 60)
                context = text_lower[start:end]
                for qp in _QTY_PATTERNS:
                    qm = re.search(qp, context)
                    if qm:
                        for g in qm.groups():
                            if g and g.isdigit():
                                quantity = max(quantity, int(g))
                                break
                        if quantity > 1:
                            break

            quantity = min(quantity, 99999)  # sanity cap

            # Keep best (most specific) match per resource type
            if resource_type not in seen_types or sub_type != "general":
                seen_types[resource_type] = {
                    "resource_type": resource_type,
                    "quantity": quantity,
                    "sub_type": sub_type,
                }
            elif quantity > seen_types[resource_type]["quantity"]:
                seen_types[resource_type]["quantity"] = quantity

    return list(seen_types.values())


# ---------------------------------------------------------------------------
# 3. find_semantic_duplicates
# ---------------------------------------------------------------------------

def find_semantic_duplicates(
    new_desc: str,
    existing_descs: list[str],
    threshold: float = 0.85,
) -> list[int]:
    """Find indices of existing descriptions that are semantically similar.

    Parameters
    ----------
    new_desc : str
        The new request description to check.
    existing_descs : list[str]
        List of existing request descriptions.
    threshold : float
        Cosine similarity threshold (0–1). Default 0.85.

    Returns
    -------
    list[int]
        Indices into ``existing_descs`` that are considered duplicates,
        sorted by similarity (highest first).
    """
    if not new_desc or not existing_descs:
        return []

    # ── Try sentence-transformer embeddings first ──
    if _ensure_embedder():
        return _duplicates_with_embeddings(new_desc, existing_descs, threshold)

    # ── Fallback: TF-IDF cosine similarity ──
    return _duplicates_with_tfidf(new_desc, existing_descs, threshold)


def _duplicates_with_embeddings(
    new_desc: str,
    existing_descs: list[str],
    threshold: float,
) -> list[int]:
    """Compute cosine similarity using sentence-transformer embeddings."""
    all_texts = [new_desc] + existing_descs
    embeddings = _embedder_model.encode(all_texts, convert_to_numpy=True)

    new_emb = embeddings[0]
    existing_embs = embeddings[1:]

    # Cosine similarity
    norm_new = np.linalg.norm(new_emb)
    if norm_new == 0:
        return []

    similarities = []
    for i, emb in enumerate(existing_embs):
        norm_e = np.linalg.norm(emb)
        if norm_e == 0:
            continue
        cos_sim = float(np.dot(new_emb, emb) / (norm_new * norm_e))
        if cos_sim >= threshold:
            similarities.append((i, cos_sim))

    # Sort by similarity descending
    similarities.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in similarities]


def _duplicates_with_tfidf(
    new_desc: str,
    existing_descs: list[str],
    threshold: float,
) -> list[int]:
    """Fallback duplicate detection using scikit-learn TF-IDF."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    all_texts = [new_desc] + existing_descs
    try:
        vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
        )
        tfidf_matrix = vectorizer.fit_transform(all_texts)
    except ValueError:
        return []

    new_vec = tfidf_matrix[0:1]
    existing_vecs = tfidf_matrix[1:]

    sims = cosine_similarity(new_vec, existing_vecs).flatten()

    duplicates = []
    for i, sim in enumerate(sims):
        if sim >= threshold:
            duplicates.append((i, float(sim)))

    duplicates.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in duplicates]


# ---------------------------------------------------------------------------
# Convenience: combined analysis for the endpoint
# ---------------------------------------------------------------------------

def analyze_request(description: str, existing_descs: Optional[list[str]] = None) -> dict[str, Any]:
    """Run all three NLP analyses in one call.

    Returns
    -------
    dict
        {
            "priority":   { predicted_priority, confidence, ... },
            "needs":      [ { resource_type, quantity, sub_type } ],
            "duplicates": [ int index ]  (only if existing_descs provided),
        }
    """
    result: dict[str, Any] = {
        "priority": predict_priority(description),
        "needs": extract_needs(description),
    }
    if existing_descs:
        result["duplicates"] = find_semantic_duplicates(description, existing_descs)
    return result
