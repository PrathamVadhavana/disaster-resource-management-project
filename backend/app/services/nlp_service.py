"""
NLP Triage Service — Phase 3
Auto-classification of victim requests, urgency signal extraction,
and priority escalation using rule-based keyword/NER analysis.
Zero external API dependencies — works fully offline.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Urgency keyword banks ──────────────────────────────────────────────────────
# Each tuple is (pattern, label, severity_boost)
# severity_boost: how many priority levels to escalate (0 = tag only, 2 = auto-critical)
URGENCY_RULES: list[tuple[str, str, int]] = [
    # Life-threatening — auto-elevate to critical
    (r"\b(unconscious|unresponsive|not breathing|cardiac arrest|no pulse)\b", "unconscious", 3),
    (r"\b(trapped|pinned|buried|stuck under|can't move|cannot move)\b", "trapped", 3),
    (r"\b(heavy bleeding|hemorrhag|severe bleed|blood loss|bleeding badly)\b", "severe_bleeding", 3),
    (r"\b(drowning|submerged|underwater|can't breathe)\b", "drowning", 3),
    (r"\b(crush(ed|ing)?|crushed by|pinned under)\b", "crush_injury", 3),
    (r"\b(not moving|paralyz|can't feel|numb)\b", "immobile", 2),
    (r"\b(heart attack|stroke|cardiac|choking)\b", "medical_emergency", 3),
    (r"\b(burning|on fire|fire nearby|smoke inhalation)\b", "fire_immediate", 3),
    (r"\b(building collaps|structure collaps|roof caving)\b", "collapse_imminent", 3),
    # Vulnerable populations — escalate 2 levels
    (r"\b(infant|newborn|baby|toddler|2 year|3 year)\b", "infant", 2),
    (r"\b(elderly|senior|aged|old (man|woman|person)|grandmother|grandfather)\b", "elderly", 2),
    (r"\b(pregnant|expecting|in labor|contractions)\b", "pregnant", 2),
    (r"\b(disabled|wheelchair|disability|mobility impaired|visually impaired)\b", "disabled", 2),
    (r"\b(alone|by myself|no one else|isolated|stranded alone)\b", "isolated", 1),
    # Deprivation signals — escalate 1-2 levels
    (r"\bno (water|food|medicine) for \d+ (day|hour)", "prolonged_deprivation", 2),
    (r"\b(haven'?t eaten|no food for|starving|malnourished)\b", "starvation", 2),
    (r"\b(dehydrat|starv|fainting from hunger)\w*\b", "dehydration_starvation", 2),
    (r"\b(no (clean )?water|no drinking water|water supply cut)\b", "no_water", 1),
    (r"\b(no food|hungry|starving|empty stomach)\b", "no_food", 1),
    (r"\b(no shelter|homeless|exposed to (rain|cold|heat)|sleeping outside)\b", "no_shelter", 1),
    (r"\b(no medic(ine|ation)|out of med|need (insulin|inhaler|epipen))\b", "no_medicine", 1),
    (r"\b(power out|no electricity|no lights)\b", "no_power", 1),
    # Medical urgency — escalate 1-2 levels
    (r"\b(bleeding|wound|injur|fracture|broken bone|sprain|cut)\b", "injury", 1),
    (r"\b(infection|fever|sepsis|vomiting|diarrhea|sick)\b", "infection", 1),
    (r"\b(diabete?s|insulin|blood sugar)\b", "chronic_medical", 1),
    (r"\b(asthma|inhaler|breathing difficult|shortness of breath|wheez)\b", "respiratory", 1),
    (r"\b(chest pain|heart|palpitation|blood pressure)\b", "cardiac_symptom", 2),
    (r"\b(seizure|convuls|epilep)\b", "seizure", 2),
    (r"\b(allergic reaction|anaphyla|swelling|throat clos)\b", "allergic", 2),
    (r"\b(hypothermia|heat stroke|heat exhaustion)\b", "temperature_extreme", 2),
    # Scale indicators
    (r"\b(\d{2,}) (people|persons|family members?|families)\b", "large_group", 1),
    (r"\b(children|kids|young ones)\b", "children_present", 1),
    (r"\b(entire family|whole family|family of)\b", "family_group", 1),
    # Emotional distress signals
    (r"\b(help me|please help|emergency|urgent|desperate|scared|terrified)\b", "emotional_distress", 0),
    (r"\b(dying|going to die|won'?t survive|critical condition)\b", "life_threatening_language", 3),
    (r"\b(running out of time|time is running out|need help now|immediately)\b", "time_critical", 1),
]

PRIORITY_LEVELS = ["low", "medium", "high", "critical"]

# ── Resource type classification keywords ──────────────────────────────────────
RESOURCE_KEYWORDS: dict[str, list[str]] = {
    "Food": [
        "food",
        "meal",
        "rice",
        "bread",
        "ration",
        "nutrition",
        "hungry",
        "starving",
        "eat",
        "cook",
        "canned",
        "supplies",
        "grocery",
    ],
    "Water": [
        "water",
        "drink",
        "thirst",
        "dehydrat",
        "purif",
        "clean water",
        "bottled water",
        "gallons",
    ],
    "Medical": [
        "medic",
        "doctor",
        "nurse",
        "ambulance",
        "hospital",
        "first aid",
        "bandage",
        "insulin",
        "inhaler",
        "medicine",
        "drug",
        "pharma",
        "wound",
        "bleeding",
        "injury",
        "fracture",
        "pain",
        "fever",
        "infection",
        "antibiot",
    ],
    "Shelter": [
        "shelter",
        "tent",
        "tarp",
        "blanket",
        "roof",
        "housing",
        "sleep",
        "camp",
        "refuge",
        "cover",
        "mattress",
    ],
    "Clothing": [
        "cloth",
        "shirt",
        "pants",
        "jacket",
        "coat",
        "shoe",
        "warm",
        "winter gear",
        "diaper",
    ],
    "Evacuation": [
        "evacuat",
        "transport",
        "rescue",
        "helicopter",
        "boat",
        "vehicle",
        "trapped",
        "stranded",
        "airlift",
    ],
    "Volunteers": [
        "volunteer",
        "helper",
        "manpower",
        "people to help",
        "assistance",
        "hands",
    ],
    "Financial Aid": [
        "money",
        "cash",
        "fund",
        "financial",
        "donation",
        "payment",
    ],
}

# ── Disaster type classification keywords ────────────────────────────────────
DISASTER_KEYWORDS: dict[str, list[str]] = {
    "earthquake": ["earthquake", "quake", "tremor", "ground shake", "collapsed", "debris", "aftershock", "shake"],
    "flood": ["flood", "water rise", "drowning", "submerged", "overflow", "river", "rain", "wash away", "inundated", "flooding"],
    "hurricane": ["hurricane", "cyclone", "typhoon", "storm surge", "strong wind", "gale", "storm"],
    "tornado": ["tornado", "twister", "funnel cloud", "windstorm"],
    "wildfire": ["wildfire", "forest fire", "smoke", "burning", "flames", "fire", "bushfire"],
    "tsunami": ["tsunami", "tidal wave", "giant wave"],
    "drought": ["drought", "dry", "no rain", "water shortage", "no water"],
    "landslide": ["landslide", "mudslide", "rockfall"],
    "volcano": ["volcano", "eruption", "ash", "lava"],
    "medical_emergency": ["medical", "injury", "sick", "hospital", "doctor", "medicine", "emergency"],
}

# ── Semantic phrase rules (higher confidence than single keywords) ─────────────
# Phrases that unambiguously map to a resource type
PHRASE_RULES: list[tuple[str, str, float]] = [
    (r"need(s)?\s+(clean\s+)?water", "Water", 0.9),
    (r"need(s)?\s+food", "Food", 0.9),
    (r"(medical|first.?aid)\s+(help|attention|care|supplies)", "Medical", 0.9),
    (r"need(s)?\s+(a\s+)?shelter", "Shelter", 0.9),
    (r"need(s)?\s+(to\s+be\s+)?evacuat", "Evacuation", 0.9),
    (r"need(s)?\s+cloth", "Clothing", 0.85),
    (r"(house|home|building)\s+(collapse|destroy|damage)", "Shelter", 0.85),
    (r"run(ning)?\s+out\s+of\s+(food|water|medicine)", "Food", 0.85),
    (r"(no|without)\s+(access\s+to\s+)?(food|water|medicine)", "Food", 0.85),
    (r"(financial|monetary)\s+(help|aid|assistance|support)", "Financial Aid", 0.9),
]


@dataclass
class UrgencySignal:
    """A single detected urgency signal in the text."""

    keyword: str  # matched text span
    label: str  # canonical label e.g. "trapped"
    severity_boost: int  # how many levels to escalate
    offset: int  # char offset in original text


@dataclass
class ClassificationResult:
    """Full NLP triage result for a victim request."""

    # Auto-detected resource type(s)
    resource_types: list[str] = field(default_factory=list)
    resource_type_scores: dict[str, float] = field(default_factory=dict)
    # Auto-detected disaster type
    disaster_type: str | None = None
    disaster_type_confidence: float = 0.0
    # Priority recommendation
    recommended_priority: str = "medium"
    priority_confidence: float = 0.5
    original_priority: str | None = None  # what user submitted
    priority_was_escalated: bool = False
    # Estimated quantity (heuristic)
    estimated_quantity: int = 1
    # Urgency signals
    urgency_signals: list[dict] = field(default_factory=list)
    # Overall confidence
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return {
            "resource_types": self.resource_types,
            "resource_type_scores": self.resource_type_scores,
            "disaster_type": self.disaster_type,
            "disaster_type_confidence": self.disaster_type_confidence,
            "recommended_priority": self.recommended_priority,
            "confidence": self.confidence,
            "urgency_signals": self.urgency_signals
        }


# ── Core functions ─────────────────────────────────────────────────────────────


def extract_urgency_signals(text: str) -> list[UrgencySignal]:
    """Scan text for urgency keywords using regex-based NER."""
    if not text:
        return []
    signals: list[UrgencySignal] = []
    seen_labels: set[str] = set()
    text_lower = text.lower()

    for pattern, label, boost in URGENCY_RULES:
        for match in re.finditer(pattern, text_lower):
            if label not in seen_labels:
                signals.append(
                    UrgencySignal(
                        keyword=match.group(0),
                        label=label,
                        severity_boost=boost,
                        offset=match.start(),
                    )
                )
                seen_labels.add(label)
    # Sort by severity (highest first)
    signals.sort(key=lambda s: s.severity_boost, reverse=True)
    return signals


def classify_resource_type(text: str) -> tuple[list[str], dict[str, float]]:
    """Classify free text into resource type(s) with confidence scores.

    Uses a two-pass strategy:
    1. Phrase rules — high-confidence patterns like "need clean water"
    2. Keyword bag-of-words — broader coverage with lower base confidence
    """
    if not text:
        return ["Custom"], {"Custom": 0.3}

    text_lower = text.lower()
    scores: dict[str, float] = {}

    # Pass 1: phrase rules (high confidence)
    for pattern, rtype, conf in PHRASE_RULES:
        if re.search(pattern, text_lower):
            scores[rtype] = max(scores.get(rtype, 0), conf)

    # Pass 2: keyword bag-of-words
    for rtype, keywords in RESOURCE_KEYWORDS.items():
        kw_score = 0.0
        for kw in keywords:
            matches = len(re.findall(rf"\b{re.escape(kw)}\w*\b", text_lower))
            if matches:
                kw_score += matches * (1.0 if len(kw) > 4 else 0.6)
        if kw_score > 0:
            normalised = min(kw_score / 3.0, 1.0)
            scores[rtype] = max(scores.get(rtype, 0), normalised)

    if not scores:
        return ["Custom"], {"Custom": 0.3}

    # Sort by score descending
    sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary_types = [t for t, s in sorted_types if s >= 0.3]
    if not primary_types:
        primary_types = [sorted_types[0][0]]

    return primary_types, dict(sorted_types)


def classify_disaster_type(text: str) -> tuple[str | None, float]:
    """Detect the most likely disaster type from free text."""
    if not text:
        return None, 0.0

    text_lower = text.lower()
    best_type = None
    max_matches = 0

    for d_type, keywords in DISASTER_KEYWORDS.items():
        matches = 0
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\w*\b", text_lower):
                matches += 1
        if matches > max_matches:
            max_matches = matches
            best_type = d_type

    confidence = min(max_matches * 0.4, 0.9) if best_type else 0.0
    return best_type, confidence


def estimate_quantity(text: str) -> int:
    """Extract quantity hints from free text."""
    if not text:
        return 1

    text_lower = text.lower()

    # Look for explicit numbers with context
    patterns = [
        r"(\d+)\s*(people|persons|family members?|families|adults|children|kids)",
        r"(\d+)\s*(bottles?|gallons?|liters?|litres?|packs?|boxes?|kits?|units?|bags?|cans?)",
        r"need\s+(\d+)",
        r"(\d+)\s*(of us|of them|mouths?)",
        r"family of (\d+)",
    ]

    max_qty = 1
    for pattern in patterns:
        for match in re.finditer(pattern, text_lower):
            try:
                qty = int(match.group(1))
                max_qty = max(max_qty, qty)
            except (ValueError, IndexError):
                pass

    return min(max_qty, 9999)  # cap at reasonable max


def escalate_priority(base_priority: str, signals: list[UrgencySignal]) -> tuple[str, bool]:
    """Compute escalated priority based on urgency signals."""
    if not signals:
        return base_priority, False

    base_idx = PRIORITY_LEVELS.index(base_priority) if base_priority in PRIORITY_LEVELS else 1
    max_boost = max(s.severity_boost for s in signals)
    new_idx = min(base_idx + max_boost, len(PRIORITY_LEVELS) - 1)
    new_priority = PRIORITY_LEVELS[new_idx]
    escalated = new_idx > base_idx

    return new_priority, escalated


def classify_request(
    description: str,
    user_priority: str = "medium",
    user_resource_type: str | None = None,
) -> ClassificationResult:
    """
    Run the full NLP triage pipeline on a request description.
    Returns classification with resource type, priority, quantity, and urgency signals.
    """
    result = ClassificationResult()
    result.original_priority = user_priority

    # 1. Extract urgency signals
    signals = extract_urgency_signals(description)
    result.urgency_signals = [
        {"keyword": s.keyword, "label": s.label, "severity_boost": s.severity_boost} for s in signals
    ]

    # 2. Classify resource type
    types, scores = classify_resource_type(description)
    result.resource_types = types
    result.resource_type_scores = scores

    # 3. Estimate quantity
    result.estimated_quantity = estimate_quantity(description)

    # 4. Classify disaster type
    d_type, d_conf = classify_disaster_type(description)
    result.disaster_type = d_type
    result.disaster_type_confidence = d_conf

    # 5. Escalate priority based on urgency signals
    recommended, escalated = escalate_priority(user_priority, signals)
    result.recommended_priority = recommended
    result.priority_was_escalated = escalated

    # 6. Compute overall confidence
    type_conf = max(scores.values()) if scores else 0.3
    signal_conf = min(len(signals) * 0.15 + 0.4, 0.95) if signals else 0.4
    result.priority_confidence = signal_conf
    # Factor in disaster type if detected
    combined_conf = (type_conf + signal_conf + (d_conf if d_type else 0.4)) / 3
    result.confidence = round(float(combined_conf), 3)

    return result


# ── ML-Based NLP Classification Service ─────────────────────────────────────────


class NLPService:
    """
    ML-based NLP classification service using TF-IDF + LogisticRegression.
    Supports retraining from feedback and fallback to rule-based classification.
    """

    MIN_TRAINING_SAMPLES = 20
    MIN_URGENCY_TRAINING_SAMPLES = 15
    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self):
        self.model_dir = Path(__file__).parent.parent / "models"
        self.model_dir.mkdir(exist_ok=True)
        self.resource_type_model_path = self.model_dir / "nlp_resource_type_pipeline.pkl"
        self.priority_model_path = self.model_dir / "nlp_priority_pipeline.pkl"
        self.urgency_model_path = self.model_dir / "nlp_urgency_model.pkl"
        self.urgency_vectorizer_path = self.model_dir / "nlp_urgency_vectorizer.pkl"
        self.resource_type_pipeline = None
        self.priority_pipeline = None
        self.urgency_model = None
        self.urgency_vectorizer = None
        self._load_models()

    def _load_models(self) -> None:
        """Load trained pipelines from disk if available."""
        try:
            import joblib
            
            if self.resource_type_model_path.exists():
                self.resource_type_pipeline = joblib.load(self.resource_type_model_path)
                logger.info(f"Loaded resource type pipeline from {self.resource_type_model_path}")
            
            if self.priority_model_path.exists():
                self.priority_pipeline = joblib.load(self.priority_model_path)
                logger.info(f"Loaded priority pipeline from {self.priority_model_path}")
            
            if self.urgency_model_path.exists() and self.urgency_vectorizer_path.exists():
                self.urgency_model = joblib.load(self.urgency_model_path)
                self.urgency_vectorizer = joblib.load(self.urgency_vectorizer_path)
                logger.info(f"Loaded urgency model from {self.urgency_model_path}")
        except Exception as e:
            logger.warning(f"Could not load ML pipelines: {e}")

    def _save_pipeline(self, pipeline: Any, path: Path) -> None:
        """Save a sklearn pipeline to disk."""
        import joblib
        joblib.dump(pipeline, path)
        logger.info(f"Saved pipeline to {path}")

    def _extract_keyword_features(self, text: str) -> dict[str, float]:
        """Extract keyword match scores as features."""
        if not text:
            return {kw: 0.0 for kw in RESOURCE_KEYWORDS.keys()}
        
        text_lower = text.lower()
        features = {}
        
        for rtype, keywords in RESOURCE_KEYWORDS.items():
            kw_score = 0.0
            for kw in keywords:
                matches = len(re.findall(rf"\b{re.escape(kw)}\w*\b", text_lower))
                if matches:
                    kw_score += matches
            features[rtype] = min(kw_score / 3.0, 1.0)
        
        # Also add disaster type keyword features
        for dtype, keywords in DISASTER_KEYWORDS.items():
            kw_score = 0.0
            for kw in keywords:
                matches = len(re.findall(rf"\b{re.escape(kw)}\w*\b", text_lower))
                if matches:
                    kw_score += matches
            features[f"disaster_{dtype}"] = min(kw_score / 2.0, 1.0)
        
        # Urgency rule features
        urgency_score = 0.0
        for pattern, label, boost in URGENCY_RULES:
            if re.search(pattern, text_lower):
                urgency_score += boost
        features["urgency_keyword_score"] = min(urgency_score / 5.0, 1.0)
        
        return features

    def _extract_text_features(self, text: str, created_at: datetime | None = None) -> dict[str, float]:
        """Extract basic text features."""
        if not text:
            return {
                "char_count": 0.0,
                "exclamation_count": 0.0,
                "question_count": 0.0,
                "hour_of_day": 12.0  # default to noon
            }
        
        return {
            "char_count": min(len(text) / 500.0, 1.0),  # normalize to 0-1
            "exclamation_count": min(text.count("!") / 5.0, 1.0),
            "question_count": min(text.count("?") / 3.0, 1.0),
            "hour_of_day": (created_at.hour if created_at else 12) / 24.0
        }

    async def build_urgency_model(self) -> dict[str, Any]:
        """
        Build an ML-based urgency scoring model from verified request data.
        
        Queries resource_requests joined with request_verifications,
        filters by verification_status in ('trusted', 'false_alarm', 'dubious'),
        and trains a GradientBoostingClassifier.
        
        Features:
        - TF-IDF of description
        - Character count
        - Exclamation marks count
        - Question marks count
        - Keyword match scores
        - Hour of day of submission
        
        Labels (soft):
        - 1.0 if 'trusted'
        - 0.0 if 'false_alarm'
        - 0.5 if 'dubious'
        
        Returns:
            dict with success, rows_used, model_metrics, timestamp
        """
        from app.database import db_admin
        
        # Query resource_requests joined with request_verifications
        try:
            # First get all verified requests
            response = await db_admin.table("resource_requests").select(
                "id, description, created_at"
            ).execute()
            requests_data = response.data or []
        except Exception as e:
            logger.error(f"Error querying resource_requests: {e}")
            return {"success": False, "error": str(e)}
        
        # Get verifications for these requests
        request_ids = [r["id"] for r in requests_data]
        if not request_ids:
            logger.info("No resource requests found")
            return {"success": False, "error": "No resource requests found"}
        
        try:
            verif_response = await db_admin.table("request_verifications").select(
                "request_id, verification_status, created_at"
).in_("request_id", request_ids).in_("verification_status", ["trusted", "false_alarm", "dubious"]).execute()
            verif_data = verif_response.data or []
        except Exception as e:
            logger.error(f"Error querying request_verifications: {e}")
            return {"success": False, "error": str(e)}
        
        # Map verifications to requests (use most recent verification per request)
        verif_by_request: dict[str, dict] = {}
        for v in verif_data:
            req_id = v.get("request_id")
            if req_id and (req_id not in verif_by_request or v.get("created_at", "") > verif_by_request[req_id].get("created_at", "")):
                verif_by_request[req_id] = v
        
        # Build training data
        training_samples = []
        for req in requests_data:
            req_id = req.get("id")
            description = req.get("description") or ""
            created_at_str = req.get("created_at")
            
            if not description or len(description) < 5:
                continue
            
            verif = verif_by_request.get(req_id)
            if not verif:
                continue
            
            status = verif.get("verification_status")
            if status not in ["trusted", "false_alarm", "dubious"]:
                continue
            
            # Create label (soft labels)
            if status == "trusted":
                label = 1.0
            elif status == "false_alarm":
                label = 0.0
            else:  # dubious
                label = 0.5
            
            # Parse created_at
            created_at = None
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                except:
                    pass
            
            training_samples.append({
                "description": description,
                "created_at": created_at,
                "label": label
            })
        
        # Check minimum samples requirement
        if len(training_samples) < self.MIN_URGENCY_TRAINING_SAMPLES:
            logger.info(f"Insufficient urgency training data: {len(training_samples)} < {self.MIN_URGENCY_TRAINING_SAMPLES}")
            return {
                "success": False,
                "rows_used": len(training_samples),
                "error": f"Insufficient training data. Need at least {self.MIN_URGENCY_TRAINING_SAMPLES} samples.",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Prepare feature matrices
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.ensemble import GradientBoostingClassifier
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_squared_error, r2_score
            import scipy.sparse as sp
            # Extract text data
            texts = [s["description"] for s in training_samples]
            labels = np.array([s["label"] for s in training_samples])
            
            # Build TF-IDF vectorizer
            self.urgency_vectorizer = TfidfVectorizer(
                max_features=1000, 
                ngram_range=(1, 2), 
                min_df=1
            )
            tfidf_features = self.urgency_vectorizer.fit_transform(texts)
            
            # Build additional features
            additional_features = []
            for i, sample in enumerate(training_samples):
                text = sample["description"]
                created_at = sample["created_at"]
                
                # Text features
                text_feats = self._extract_text_features(text, created_at)
                
                # Keyword features
                keyword_feats = self._extract_keyword_features(text)
                
                # Combine all features
                all_feats = list(text_feats.values()) + list(keyword_feats.values())
                additional_features.append(all_feats)
            
            additional_features = np.array(additional_features)
            
            # Combine TF-IDF with additional features
            import scipy.sparse as sp
            X_combined = sp.hstack([tfidf_features, sp.csr_matrix(additional_features)])
            
            # Train-test split
            X_train, X_test, y_train, y_test = train_test_split(
                X_combined, labels, test_size=0.2, random_state=42
            )
            
            # Train GradientBoostingClassifier
            self.urgency_model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
                loss="ls"  # least squares for regression-like output
            )
            self.urgency_model.fit(X_train, y_train)
            
            # Evaluate
            y_pred = self.urgency_model.predict(X_test)
            mse = mean_squared_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            
            # Save model and vectorizer
            import joblib
            joblib.dump(self.urgency_model, self.urgency_model_path)
            joblib.dump(self.urgency_vectorizer, self.urgency_vectorizer_path)
            logger.info(f"Saved urgency model to {self.urgency_model_path}")
            
            logger.info(f"Built urgency model: {len(training_samples)} samples, mse={mse:.3f}, r2={r2:.3f}")
            
            return {
                "success": True,
                "rows_used": len(training_samples),
                "mse": round(mse, 4),
                "r2_score": round(r2, 4),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error building urgency model: {e}")
            return {"success": False, "error": str(e), "timestamp": datetime.utcnow().isoformat()}

    def get_urgency_score(self, description: str, created_at: datetime | None = None) -> tuple[float, str]:
        """
        Get urgency score (0-1) for a description.
        
        Uses ML model if available, otherwise falls back to rule-based.
        
        Returns:
            tuple of (score, method) where method is 'ml_model' or 'rule_based'
        """
        if self.urgency_model is not None and self.urgency_vectorizer is not None:
            try:
                # Extract TF-IDF features
                tfidf_features = self.urgency_vectorizer.transform([description])
                
                # Extract additional features
                text_feats = self._extract_text_features(description, created_at)
                keyword_feats = self._extract_keyword_features(description)
                
                additional = np.array([list(text_feats.values()) + list(keyword_feats.values())])
                import scipy.sparse as sp
                X_combined = sp.hstack([tfidf_features, sp.csr_matrix(additional)])
                
                # Get probability/score from model
                # For GradientBoostingClassifier, we use predict_proba or decision_function
                if hasattr(self.urgency_model, "predict_proba"):
                    proba = self.urgency_model.predict_proba(X_combined)
                    # Use the probability of the positive class (1.0)
                    score = float(proba[0][1]) if len(proba[0]) > 1 else float(proba[0][0])
                else:
                    score = float(self.urgency_model.predict(X_combined)[0])
                
                # Ensure score is in 0-1 range
                score = max(0.0, min(1.0, score))
                
                return score, "ml_model"
                
            except Exception as e:
                logger.warning(f"ML urgency scoring failed: {e}")
        
        # Fall back to rule-based urgency scoring
        signals = extract_urgency_signals(description)
        
        # Calculate score based on signals
        if not signals:
            score = 0.5  # default medium
        else:
            # Higher score = more urgent
            max_boost = max(s.severity_boost for s in signals)
            # Map severity_boost (0-3) to score (0.3-1.0)
            score = 0.3 + (max_boost / 3.0) * 0.7
        
        return score, "rule_based"

    def is_urgency_model_available(self) -> bool:
        """Check if urgency ML model is loaded and ready."""
        return self.urgency_model is not None and self.urgency_vectorizer is not None

    async def retrain_from_feedback(self) -> dict[str, Any]:
        """
        Retrain ML models from feedback data.
        
        Returns:
            dict with keys: rows_used, model_accuracy, timestamp, success
        """
        from app.database import db_admin
        
        # Query feedback rows not yet used in training
        try:
            feedback_response = await db_admin.table("nlp_training_feedback").select("*").eq("used_in_training", False).execute()
            feedback_rows = feedback_response.data or []
        except Exception as e:
            logger.error(f"Error querying feedback: {e}")
            return {"success": False, "error": str(e)}

        # Query resource_requests with nlp_classification
        try:
            base_response = await db_admin.table("resource_requests").select("id, description, resource_type, priority, nlp_classification").not_.is_("nlp_classification", "null").execute()
            base_rows = base_response.data or []
        except Exception as e:
            logger.error(f"Error querying resource_requests: {e}")
            base_rows = []

        # Build training data: (description, resource_type, priority)
        training_data: list[tuple[str, str, str]] = []

        # Add base corpus from resource_requests
        for row in base_rows:
            desc = row.get("description") or ""
            if not desc or len(desc) < 5:
                continue
            
            # Use nlp_classification if available, otherwise use resource_type
            nlp_class = row.get("nlp_classification")
            if nlp_class and isinstance(nlp_class, dict):
                resource_type = nlp_class.get("resource_type") or row.get("resource_type")
            else:
                resource_type = row.get("resource_type")
            
            priority = row.get("priority") or "medium"
            
            if resource_type and desc:
                training_data.append((desc, resource_type, priority))

        # Add feedback corrections
        for row in feedback_rows:
            # Get the original request to get description
            try:
                req_response = await db_admin.table("resource_requests").select("description").eq("id", row.get("request_id")).execute()
                req_data = req_response.data
                if req_data:
                    desc = req_data[0].get("description") or ""
                else:
                    desc = ""
            except:
                desc = ""
            
            if not desc or len(desc) < 5:
                continue
            
            # Use corrected values if available, else use original
            corrected_type = row.get("corrected_resource_type")
            corrected_priority = row.get("corrected_priority")
            
            # We need to get original classification from the request
            # For now, use corrected values as the label
            if corrected_type:
                resource_type = corrected_type
            else:
                continue  # Skip if no correction
            
            priority = corrected_priority or "medium"
            training_data.append((desc, resource_type, priority))

        # Check minimum samples requirement
        if len(training_data) < self.MIN_TRAINING_SAMPLES:
            logger.info(f"Insufficient training data: {len(training_data)} < {self.MIN_TRAINING_SAMPLES}")
            return {
                "success": False,
                "rows_used": len(training_data),
                "error": f"Insufficient training data. Need at least {self.MIN_TRAINING_SAMPLES} samples.",
                "timestamp": datetime.utcnow().isoformat()
            }

        # Prepare training arrays
        texts = [t[0] for t in training_data]
        resource_types = [t[1] for t in training_data]
        priorities = [t[2] for t in training_data]

        # Normalize priorities to buckets
        priority_buckets = []
        for p in priorities:
            p_lower = p.lower() if p else "medium"
            if p_lower in ["low", "medium", "high", "critical"]:
                priority_buckets.append(p_lower)
            elif p_lower in ["1", "2"]:
                priority_buckets.append("low")
            elif p_lower in ["3", "4"]:
                priority_buckets.append("medium")
            elif p_lower in ["5", "6"]:
                priority_buckets.append("high")
            else:
                priority_buckets.append("medium")

        # Build TF-IDF + LogisticRegression pipelines
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import accuracy_score

            # Train resource type classifier
            X_train_rt, X_test_rt, y_train_rt, y_test_rt = train_test_split(
                texts, resource_types, test_size=0.2, random_state=42
            )

            self.resource_type_pipeline = Pipeline([
                ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=1)),
                ("clf", LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced"))
            ])
            self.resource_type_pipeline.fit(X_train_rt, y_train_rt)

            # Evaluate
            rt_accuracy = accuracy_score(y_test_rt, self.resource_type_pipeline.predict(X_test_rt))

            # Train priority classifier
            X_train_p, X_test_p, y_train_p, y_test_p = train_test_split(
                texts, priority_buckets, test_size=0.2, random_state=42
            )

            self.priority_pipeline = Pipeline([
                ("tfidf", TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=1)),
                ("clf", LogisticRegression(max_iter=1000, random_state=42, class_weight="balanced"))
            ])
            self.priority_pipeline.fit(X_train_p, y_train_p)

            # Evaluate
            p_accuracy = accuracy_score(y_test_p, self.priority_pipeline.predict(X_test_p))

            # Save pipelines
            self._save_pipeline(self.resource_type_pipeline, self.resource_type_model_path)
            self._save_pipeline(self.priority_pipeline, self.priority_model_path)

            # Mark feedback rows as used_in_training
            feedback_ids = [row["id"] for row in feedback_rows]
            if feedback_ids:
                try:
                    await db_admin.table("nlp_training_feedback").update({"used_in_training": True}).in_("id", feedback_ids).execute()
                except Exception as e:
                    logger.warning(f"Could not mark feedback as used: {e}")

            logger.info(f"Retrained NLP models: {len(training_data)} samples, rt_acc={rt_accuracy:.3f}, p_acc={p_accuracy:.3f}")

            return {
                "success": True,
                "rows_used": len(training_data),
                "resource_type_accuracy": round(rt_accuracy, 3),
                "priority_accuracy": round(p_accuracy, 3),
                "timestamp": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error during training: {e}")
            return {"success": False, "error": str(e), "timestamp": datetime.utcnow().isoformat()}

    def classify(self, description: str, user_priority: str = "medium") -> dict[str, Any]:
        """
        Classify text using ML model if available and confident, else fall back to rule-based.
        
        Returns:
            dict with classification results and method_used ('ml_model' or 'rule_based')
        """
        # Try ML model first
        if self.resource_type_pipeline is not None and self.priority_pipeline is not None:
            try:
                # Get predictions with probabilities
                rt_pred = self.resource_type_pipeline.predict([description])[0]
                rt_proba = self.resource_type_pipeline.predict_proba([description])
                rt_conf = max(rt_proba[0]) if hasattr(rt_proba[0], "__len__") else 0.5

                p_pred = self.priority_pipeline.predict([description])[0]
                p_proba = self.priority_pipeline.predict_proba([description])
                p_conf = max(p_proba[0]) if hasattr(p_proba[0], "__len__") else 0.5

                # Use ML model if confidence above threshold
                if rt_conf >= self.CONFIDENCE_THRESHOLD:
                    return {
                        "resource_types": [rt_pred],
                        "resource_type_scores": {rt_pred: round(rt_conf, 3)},
                        "recommended_priority": p_pred,
                        "priority_confidence": round(p_conf, 3),
                        "confidence": round((rt_conf + p_conf) / 2, 3),
                        "method_used": "ml_model",
                        "urgency_signals": extract_urgency_signals(description)
                    }
            except Exception as e:
                logger.warning(f"ML classification failed: {e}")

        # Fall back to rule-based classification
        result = classify_request(
            description=description,
            user_priority=user_priority,
        )
        
        return {
            "resource_types": result.resource_types,
            "resource_type_scores": result.resource_type_scores,
            "recommended_priority": result.recommended_priority,
            "priority_confidence": result.priority_confidence,
            "original_priority": result.original_priority,
            "priority_was_escalated": result.priority_was_escalated,
            "estimated_quantity": result.estimated_quantity,
            "urgency_signals": result.urgency_signals,
            "confidence": result.confidence,
            "method_used": "rule_based"
        }

    def is_ml_model_available(self) -> bool:
        """Check if ML models are loaded and ready."""
        return self.resource_type_pipeline is not None and self.priority_pipeline is not None


# Singleton instance
_nlp_service: NLPService | None = None


def get_nlp_service() -> NLPService:
    """Get or create the NLP service singleton."""
    global _nlp_service
    if _nlp_service is None:
        _nlp_service = NLPService()
    return _nlp_service
