"""
Explainability Service — Phase 3 Enhancement
=============================================

Provides human-readable explanations for AI decisions:
- Why a particular priority was assigned to a resource request
- Why certain resources were recommended
- What data points influenced predictions
- Causal reasoning chains for disaster outcomes
- Confidence breakdowns for AI recommendations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExplanationChain:
    """A chain of reasoning steps that led to a conclusion."""
    conclusion: str
    reasoning_steps: list[str] = field(default_factory=list)
    confidence: float = 0.0
    data_sources: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "conclusion": self.conclusion,
            "reasoning_steps": self.reasoning_steps,
            "confidence": round(self.confidence, 2),
            "data_sources": self.data_sources,
            "caveats": self.caveats,
        }

    def to_markdown(self) -> str:
        parts = [f"**{self.conclusion}**\n"]
        if self.reasoning_steps:
            parts.append("**Reasoning:**")
            for i, step in enumerate(self.reasoning_steps, 1):
                parts.append(f"{i}. {step}")
            parts.append("")
        if self.data_sources:
            parts.append("**Data Sources:** " + ", ".join(self.data_sources))
        if self.caveats:
            parts.append("\n**⚠️ Caveats:**")
            for caveat in self.caveats:
                parts.append(f"- {caveat}")
        label = "High" if self.confidence >= 0.8 else "Medium" if self.confidence >= 0.5 else "Low"
        parts.append(f"\n*Confidence: {label} ({self.confidence:.0%})*")
        return "\n".join(parts)


class ExplainabilityService:
    """Generates human-readable explanations for AI decisions."""

    async def explain_priority_assignment(self, request: dict, context: dict, assigned_priority: str) -> ExplanationChain:
        steps, factors, confidence = [], [], 0.7
        if request.get("has_medical_needs") or request.get("medical_details"):
            steps.append(f"Medical needs detected: '{request.get('medical_details', 'injuries mentioned')}' → escalated to HIGH priority")
            factors.append("medical_needs"); confidence += 0.1
        desc = (request.get("description") or "").lower()
        crit_kw = ["trapped","buried","unconscious","drowning","severe bleeding","building collapse","no water","medical emergency","fire spreading"]
        found = [k for k in crit_kw if k in desc]
        if found:
            steps.append(f"Critical urgency signals found: {', '.join(found)} → priority boosted to CRITICAL")
            factors.append("critical_keywords"); confidence += 0.15
        disaster = context.get("focused_disaster") or {}
        if disaster:
            steps.append(f"Active {disaster.get('type','disaster')} '{disaster.get('title','')}' detected → priority boosted by 1 level")
            factors.append("active_disaster_proximity"); confidence += 0.05
        people = request.get("people_count") or request.get("head_count") or 1
        if people > 5:
            steps.append(f"Large group size ({people} people) → priority boosted by 1 level")
            factors.append("large_group"); confidence += 0.05
        vuln_kw = ["elderly","children","disabled","pregnant","infant","baby"]
        if any(v in desc for v in vuln_kw):
            steps.append("Vulnerable population detected (elderly/children/disabled) → priority boosted")
            factors.append("elderly_children"); confidence += 0.05
        inv = context.get("inventory_summary") or {}
        low = inv.get("low_stock", [])
        rt = request.get("resource_type", "")
        if rt and rt in low:
            steps.append(f"Resource '{rt}' is in low stock → consider expediting procurement")
            factors.append("resource_scarcity")
        if not steps:
            steps.append("Standard priority assigned based on description analysis"); confidence = 0.6
        caveats = []
        if confidence < 0.7: caveats.append("Limited data available — priority may need manual review")
        if not request.get("location"): caveats.append("No location provided — proximity-based factors not applied")
        return ExplanationChain(conclusion=f"Priority assigned: **{assigned_priority.upper()}**", reasoning_steps=steps, confidence=min(confidence,1.0), data_sources=["resource_request","disaster_context","inventory_data"], caveats=caveats)

    async def explain_resource_recommendation(self, resource_type: str, context: dict) -> ExplanationChain:
        steps = []
        gaps = context.get("supply_demand_gaps") or {}
        gap_list = gaps.get("gaps", [])
        match = next((g for g in gap_list if g.get("type","").lower() == resource_type.lower()), None)
        if match:
            cov, dem, sup = match.get("coverage_pct",0), match.get("demand",0), match.get("supply",0)
            steps.append(f"Supply-demand analysis: {resource_type} — {dem} demanded, {sup} available ({cov}% coverage)")
            if cov < 50: steps.append(f"Critical shortage — {resource_type} urgently needed")
            elif cov < 80: steps.append(f"Moderate shortage — additional {resource_type} recommended")
        req_sum = context.get("resource_requests_summary") or {}
        by_t = req_sum.get("by_type",{})
        if resource_type in by_t:
            steps.append(f"Recent demand: {by_t[resource_type]} {resource_type} requests in last 24h")
        inv = context.get("inventory_summary") or {}
        by_ti = inv.get("by_type",{})
        if resource_type in by_ti:
            qty = by_ti[resource_type].get("total_quantity",0)
            if qty < 50: steps.append(f"Current inventory: {qty} units — below safe threshold")
        return ExplanationChain(conclusion=f"Recommendation: **{resource_type}** resources", reasoning_steps=steps if steps else ["Based on general disaster response protocols"], confidence=0.75 if steps else 0.5, data_sources=["supply_demand_analysis","request_patterns","inventory_data"])

    async def explain_causal_insight(self, treatment: str, outcome: str, ate: float, ci: tuple[float,float], refutation_passed: bool|None) -> ExplanationChain:
        names = {"response_time_hours":"Response Time","casualties":"Casualties","resource_availability":"Resource Availability","economic_damage_usd":"Economic Damage","weather_severity":"Weather Severity","ngo_proximity_km":"NGO Proximity","resource_quality_score":"Resource Quality","disaster_type":"Disaster Type"}
        tn, on = names.get(treatment, treatment.replace("_"," ").title()), names.get(outcome, outcome.replace("_"," ").title())
        steps = []
        if ate > 0: steps.append(f"Each 1-unit increase in {tn} → {ate:.2f} unit increase in {on}")
        else: steps.append(f"Each 1-unit increase in {tn} → {abs(ate):.2f} unit decrease in {on}")
        lo, hi = ci
        steps.append(f"95% confidence interval: [{lo:.2f}, {hi:.2f}]")
        if refutation_passed is True: steps.append("✅ Placebo refutation passed — effect likely causal")
        elif refutation_passed is False: steps.append("⚠️ Placebo refutation failed — effect may be confounded")
        if abs(ate) > 5: steps.append(f"**Strong effect**: Small changes in {tn} significantly impact {on}")
        elif abs(ate) > 1: steps.append(f"**Moderate effect**: {tn} meaningfully influences {on}")
        else: steps.append(f"**Weak effect**: {tn} has limited direct impact on {on}")
        caveats = []
        if refutation_passed is None: caveats.append("Refutation not performed — interpret with caution")
        if lo * hi < 0: caveats.append("CI crosses zero — effect may not be significant")
        return ExplanationChain(conclusion=f"Causal Effect: **{tn}** → **{on}**", reasoning_steps=steps, confidence=0.85 if refutation_passed else 0.6, data_sources=["causal_model","historical_disaster_data"], caveats=caveats)

    async def explain_anomaly(self, anomaly_type: str, metric_name: str, metric_value: float, expected_range: dict, anomaly_score: float) -> ExplanationChain:
        steps, lo, hi = [], expected_range.get("lower",0), expected_range.get("upper",100)
        if metric_value > hi: steps.append(f"{metric_name} ({metric_value:.1f}) is {metric_value-hi:.1f} above upper bound ({hi:.1f})")
        elif metric_value < lo: steps.append(f"{metric_name} ({metric_value:.1f}) is {lo-metric_value:.1f} below lower bound ({lo:.1f})")
        steps.append(f"Anomaly score: {anomaly_score:.2f} (threshold: 0.7)")
        if anomaly_score > 0.9: steps.append("**Critical anomaly** — requires immediate investigation")
        elif anomaly_score > 0.7: steps.append("**Significant anomaly** — should be reviewed soon")
        return ExplanationChain(conclusion=f"Anomaly Detected: **{anomaly_type}** in {metric_name}", reasoning_steps=steps, confidence=min(anomaly_score,1.0), data_sources=["anomaly_detection","historical_baselines"])

    def format_explanation_for_chat(self, explanation: ExplanationChain) -> str:
        return explanation.to_markdown()