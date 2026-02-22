"""
Tests for NLP Triage Service — Phase 3
"""
import pytest
from app.services.nlp_service import (
    extract_urgency_signals,
    classify_resource_type,
    estimate_quantity,
    escalate_priority,
    classify_request,
    ClassificationResult,
)


class TestUrgencySignalExtraction:
    """Test urgency keyword detection."""

    def test_detects_trapped(self):
        signals = extract_urgency_signals("We are trapped under rubble, please help!")
        labels = [s.label for s in signals]
        assert "trapped" in labels

    def test_detects_life_threatening(self):
        signals = extract_urgency_signals("My mother is unconscious and not breathing")
        labels = [s.label for s in signals]
        assert "unconscious" in labels
        # Should have high severity boost
        assert any(s.severity_boost >= 3 for s in signals)

    def test_detects_infant(self):
        signals = extract_urgency_signals("I have an infant who needs formula and diapers")
        labels = [s.label for s in signals]
        assert "infant" in labels

    def test_detects_deprivation(self):
        signals = extract_urgency_signals("no water for 3 days, family of 5")
        labels = [s.label for s in signals]
        assert "prolonged_deprivation" in labels or "no_water" in labels

    def test_detects_multiple_signals(self):
        text = "Elderly woman trapped with infant, severe bleeding, no water for 2 days"
        signals = extract_urgency_signals(text)
        assert len(signals) >= 3

    def test_empty_text_returns_empty(self):
        assert extract_urgency_signals("") == []

    def test_no_signals_in_normal_text(self):
        signals = extract_urgency_signals("We need some extra blankets for comfort")
        # May or may not detect signals; key is no life-threatening ones
        critical = [s for s in signals if s.severity_boost >= 3]
        assert len(critical) == 0

    def test_deduplicates_labels(self):
        text = "trapped trapped trapped under rubble, still trapped"
        signals = extract_urgency_signals(text)
        labels = [s.label for s in signals]
        assert labels.count("trapped") == 1


class TestResourceTypeClassification:
    """Test resource type detection from text."""

    def test_classifies_water(self):
        types, scores = classify_resource_type("We desperately need clean water and bottles")
        assert "Water" in types

    def test_classifies_medical(self):
        types, scores = classify_resource_type("Need a doctor and medicine for wound treatment")
        assert "Medical" in types

    def test_classifies_food(self):
        types, scores = classify_resource_type("Need food and rations for 10 people")
        assert "Food" in types

    def test_classifies_shelter(self):
        types, scores = classify_resource_type("We need tents and blankets, our house collapsed")
        assert "Shelter" in types

    def test_classifies_evacuation(self):
        types, scores = classify_resource_type("Please send rescue helicopter, we are stranded")
        assert "Evacuation" in types

    def test_multiple_types(self):
        types, scores = classify_resource_type("Need food, water, and medical supplies urgently")
        assert len(types) >= 2

    def test_empty_text_returns_custom(self):
        types, _ = classify_resource_type("")
        assert "Custom" in types

    def test_scores_are_normalized(self):
        _, scores = classify_resource_type("water water water medicine food")
        for score in scores.values():
            assert 0 <= score <= 1.0


class TestQuantityEstimation:
    """Test quantity extraction from text."""

    def test_extracts_family_size(self):
        assert estimate_quantity("family of 6 needs help") == 6

    def test_extracts_people_count(self):
        assert estimate_quantity("There are 15 people in our group") == 15

    def test_extracts_item_count(self):
        assert estimate_quantity("We need 20 bottles of water") == 20

    def test_defaults_to_one(self):
        assert estimate_quantity("we need help") == 1

    def test_empty_text(self):
        assert estimate_quantity("") == 1

    def test_caps_at_max(self):
        assert estimate_quantity("need 99999 items") <= 9999


class TestPriorityEscalation:
    """Test priority escalation logic."""

    def test_no_escalation_without_signals(self):
        priority, escalated = escalate_priority("medium", [])
        assert priority == "medium"
        assert escalated is False

    def test_escalates_to_critical(self):
        from app.services.nlp_service import UrgencySignal
        signals = [UrgencySignal(keyword="trapped", label="trapped", severity_boost=3, offset=0)]
        priority, escalated = escalate_priority("low", signals)
        assert priority == "critical"
        assert escalated is True

    def test_escalates_from_medium_to_high(self):
        from app.services.nlp_service import UrgencySignal
        signals = [UrgencySignal(keyword="bleeding", label="injury", severity_boost=1, offset=0)]
        priority, escalated = escalate_priority("medium", signals)
        assert priority == "high"
        assert escalated is True

    def test_already_critical_stays_critical(self):
        from app.services.nlp_service import UrgencySignal
        signals = [UrgencySignal(keyword="trapped", label="trapped", severity_boost=3, offset=0)]
        priority, escalated = escalate_priority("critical", signals)
        assert priority == "critical"
        assert escalated is False


class TestFullClassification:
    """Test the complete classification pipeline."""

    def test_basic_classification(self):
        result = classify_request(
            "We need food and water for 5 people, one person is injured",
            user_priority="medium",
        )
        assert isinstance(result, ClassificationResult)
        assert len(result.resource_types) >= 1
        assert result.estimated_quantity >= 1
        assert 0 <= result.confidence <= 1

    def test_critical_escalation(self):
        result = classify_request(
            "Person trapped under collapsed building, unconscious, not breathing",
            user_priority="medium",
        )
        assert result.recommended_priority == "critical"
        assert result.priority_was_escalated is True
        assert len(result.urgency_signals) >= 1

    def test_to_dict(self):
        result = classify_request("Need water", "low")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "resource_types" in d
        assert "urgency_signals" in d
        assert "confidence" in d

    def test_multilingual_keywords_work(self):
        """Even though NLP uses English keywords, mixed text should still catch them."""
        result = classify_request(
            "Necesitamos water urgente, hay un infant enfermo",
            user_priority="medium",
        )
        assert "Water" in result.resource_types or any(
            s["label"] == "infant" for s in result.urgency_signals
        )
