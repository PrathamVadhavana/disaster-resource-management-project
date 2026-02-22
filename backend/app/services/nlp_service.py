"""
NLP Triage Service — Phase 3
Auto-classification of victim requests, urgency signal extraction,
and priority escalation using rule-based keyword/NER analysis.
Zero external API dependencies — works fully offline.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# ── Urgency keyword banks ──────────────────────────────────────────────────────
# Each tuple is (pattern, label, severity_boost)
# severity_boost: how many priority levels to escalate (0 = tag only, 2 = auto-critical)
URGENCY_RULES: list[tuple[str, str, int]] = [
    # Life-threatening — auto-elevate to critical
    (r"\b(unconscious|unresponsive|not breathing|cardiac arrest)\b", "unconscious", 3),
    (r"\b(trapped|pinned|buried|stuck under)\b", "trapped", 3),
    (r"\b(heavy bleeding|hemorrhag|severe bleed|blood loss)\b", "severe_bleeding", 3),
    (r"\b(drowning|submerged)\b", "drowning", 3),
    (r"\b(crush(ed|ing)?)\b", "crush_injury", 3),
    (r"\b(not moving|paralyz)\b", "immobile", 2),
    # Vulnerable populations — escalate 2 levels
    (r"\b(infant|newborn|baby|toddler)\b", "infant", 2),
    (r"\b(elderly|senior|aged|old (man|woman|person))\b", "elderly", 2),
    (r"\b(pregnant|expecting)\b", "pregnant", 2),
    (r"\b(disabled|wheelchair|disability)\b", "disabled", 2),
    # Deprivation signals — escalate 1-2 levels
    (r"\bno (water|food|medicine) for \d+ day", "prolonged_deprivation", 2),
    (r"\b(dehydrat|starv)\w*\b", "dehydration_starvation", 2),
    (r"\b(no (clean )?water)\b", "no_water", 1),
    (r"\b(no food|hungry|starving)\b", "no_food", 1),
    (r"\b(no shelter|homeless|exposed)\b", "no_shelter", 1),
    (r"\b(no medic(ine|ation)|out of med)\b", "no_medicine", 1),
    # Medical urgency — escalate 1-2 levels
    (r"\b(bleeding|wound|injur|fracture|broken bone)\b", "injury", 1),
    (r"\b(infection|fever|sepsis)\b", "infection", 1),
    (r"\b(diabete?s|insulin)\b", "chronic_medical", 1),
    (r"\b(asthma|inhaler|breathing difficult)\b", "respiratory", 1),
    (r"\b(chest pain|heart)\b", "cardiac_symptom", 2),
    (r"\b(seizure|convuls)\b", "seizure", 2),
    # Scale indicators
    (r"\b(\d{2,}) (people|persons|family members|families)\b", "large_group", 1),
    (r"\b(children|kids)\b", "children_present", 1),
]

PRIORITY_LEVELS = ["low", "medium", "high", "critical"]

# ── Resource type classification keywords ──────────────────────────────────────
RESOURCE_KEYWORDS: dict[str, list[str]] = {
    "Food": [
        "food", "meal", "rice", "bread", "ration", "nutrition", "hungry",
        "starving", "eat", "cook", "canned", "supplies", "grocery",
    ],
    "Water": [
        "water", "drink", "thirst", "dehydrat", "purif", "clean water",
        "bottled water", "gallons",
    ],
    "Medical": [
        "medic", "doctor", "nurse", "ambulance", "hospital", "first aid",
        "bandage", "insulin", "inhaler", "medicine", "drug", "pharma",
        "wound", "bleeding", "injury", "fracture", "pain", "fever",
        "infection", "antibiot",
    ],
    "Shelter": [
        "shelter", "tent", "tarp", "blanket", "roof", "housing", "sleep",
        "camp", "refuge", "cover", "mattress",
    ],
    "Clothing": [
        "cloth", "shirt", "pants", "jacket", "coat", "shoe", "warm",
        "winter gear", "diaper",
    ],
    "Evacuation": [
        "evacuat", "transport", "rescue", "helicopter", "boat", "vehicle",
        "trapped", "stranded", "airlift",
    ],
    "Volunteers": [
        "volunteer", "helper", "manpower", "people to help", "assistance",
        "hands",
    ],
    "Financial Aid": [
        "money", "cash", "fund", "financial", "donation", "payment",
    ],
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
    keyword: str            # matched text span
    label: str              # canonical label e.g. "trapped"
    severity_boost: int     # how many levels to escalate
    offset: int             # char offset in original text


@dataclass
class ClassificationResult:
    """Full NLP triage result for a victim request."""
    # Auto-detected resource type(s)
    resource_types: list[str] = field(default_factory=list)
    resource_type_scores: dict[str, float] = field(default_factory=dict)
    # Priority recommendation
    recommended_priority: str = "medium"
    priority_confidence: float = 0.5
    original_priority: str | None = None       # what user submitted
    priority_was_escalated: bool = False
    # Estimated quantity (heuristic)
    estimated_quantity: int = 1
    # Urgency signals
    urgency_signals: list[dict] = field(default_factory=list)
    # Overall confidence
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)


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
                signals.append(UrgencySignal(
                    keyword=match.group(0),
                    label=label,
                    severity_boost=boost,
                    offset=match.start(),
                ))
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
        {"keyword": s.keyword, "label": s.label, "severity_boost": s.severity_boost}
        for s in signals
    ]

    # 2. Classify resource type
    types, scores = classify_resource_type(description)
    result.resource_types = types
    result.resource_type_scores = scores

    # 3. Estimate quantity
    result.estimated_quantity = estimate_quantity(description)

    # 4. Escalate priority based on urgency signals
    recommended, escalated = escalate_priority(user_priority, signals)
    result.recommended_priority = recommended
    result.priority_was_escalated = escalated

    # 5. Compute overall confidence
    type_conf = max(scores.values()) if scores else 0.3
    signal_conf = min(len(signals) * 0.15 + 0.4, 0.95) if signals else 0.4
    result.priority_confidence = signal_conf
    result.confidence = round((type_conf + signal_conf) / 2, 3)

    return result
