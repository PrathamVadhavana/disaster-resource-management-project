"""
Causal AI module for post-disaster analysis.

Uses DoWhy to build a Structural Causal Model (SCM) encoding domain
knowledge about how weather, response logistics, and resource
deployment causally drive disaster outcomes (casualties &
economic damage).

Key capabilities
────────────────
- Causal graph construction from domain knowledge
- Average Treatment Effect (ATE) estimation via backdoor adjustment
- Placebo refutation tests for estimate validation
- Counterfactual inference for "what-if" intervention analysis
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# Suppress noisy warnings from dowhy/statsmodels that clutter logs
warnings.filterwarnings("ignore", category=FutureWarning, module="dowhy")
warnings.filterwarnings("ignore", category=FutureWarning, module="statsmodels")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="statsmodels")
warnings.filterwarnings("ignore", message="divide by zero")
warnings.filterwarnings("ignore", message="invalid value encountered")

logger = logging.getLogger("causal_model")

# ---------------------------------------------------------------------------
# Graph specification
# ---------------------------------------------------------------------------

CAUSAL_NODES: list[str] = [
    "weather_severity",
    "disaster_type",
    "response_time_hours",
    "resource_availability",
    "ngo_proximity_km",
    "resource_quality_score",
    "casualties",
    "economic_damage_usd",
]

# Directed edges encoding domain knowledge.
# Each tuple is (cause, effect).
CAUSAL_EDGES: list[tuple[str, str]] = [
    # Weather drives disaster type & severity-related outcomes
    ("weather_severity", "disaster_type"),
    ("weather_severity", "casualties"),
    ("weather_severity", "economic_damage_usd"),
    # Disaster type influences response logistics & damage
    ("disaster_type", "response_time_hours"),
    ("disaster_type", "casualties"),
    ("disaster_type", "economic_damage_usd"),
    # Response time causally affects casualties
    ("response_time_hours", "casualties"),
    # Resource availability affects all outcome variables
    ("resource_availability", "casualties"),
    ("resource_availability", "economic_damage_usd"),
    ("resource_availability", "resource_quality_score"),
    # NGO proximity affects response time & resource availability
    ("ngo_proximity_km", "response_time_hours"),
    ("ngo_proximity_km", "resource_availability"),
    # Resource quality mitigates casualties & economic damage
    ("resource_quality_score", "casualties"),
    ("resource_quality_score", "economic_damage_usd"),
]


def _build_gml_graph() -> str:
    """Return a GML string consumed by DoWhy ``CausalModel``."""
    lines = ["graph [directed 1"]
    for node in CAUSAL_NODES:
        lines.append(f'  node [id "{node}" label "{node}"]')
    for src, dst in CAUSAL_EDGES:
        lines.append(f'  edge [source "{src}" target "{dst}"]')
    lines.append("]")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthetic data generator (for bootstrapping when real data is scarce)
# ---------------------------------------------------------------------------

def generate_synthetic_data(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    """Generate observational data consistent with the causal graph.

    The functional relationships are simplified linear + noise models
    calibrated to realistic disaster-domain scales.
    """
    rng = np.random.default_rng(seed)

    weather_severity = rng.uniform(1, 10, n)
    disaster_type = (weather_severity * 0.6 + rng.normal(0, 1, n)).clip(1, 10)
    ngo_proximity_km = rng.exponential(50, n).clip(1, 500)

    response_time_hours = (
        disaster_type * 1.2
        + ngo_proximity_km * 0.05
        + rng.normal(0, 2, n)
    ).clip(0.5, 120)

    resource_availability = (
        5.0
        - ngo_proximity_km * 0.01
        + rng.normal(0, 0.5, n)
    ).clip(0.1, 10)

    resource_quality_score = (
        resource_availability * 0.5
        + rng.normal(3, 1, n)
    ).clip(1, 10)

    casualties = (
        weather_severity * 8
        + disaster_type * 5
        + response_time_hours * 3
        - resource_availability * 6
        - resource_quality_score * 2
        + rng.normal(0, 10, n)
    ).clip(0, None).astype(int)

    economic_damage_usd = (
        weather_severity * 500_000
        + disaster_type * 300_000
        - resource_availability * 200_000
        - resource_quality_score * 100_000
        + rng.normal(0, 200_000, n)
    ).clip(0, None)

    return pd.DataFrame({
        "weather_severity": weather_severity,
        "disaster_type": disaster_type,
        "response_time_hours": response_time_hours,
        "resource_availability": resource_availability,
        "ngo_proximity_km": ngo_proximity_km,
        "resource_quality_score": resource_quality_score,
        "casualties": casualties,
        "economic_damage_usd": economic_damage_usd,
    })


# ---------------------------------------------------------------------------
# Causal estimation helpers
# ---------------------------------------------------------------------------

@dataclass
class CausalEstimateResult:
    """Container for a single causal effect estimate + refutation."""
    treatment: str
    outcome: str
    method: str
    ate: float
    p_value: float | None = None
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    refutation_passed: bool | None = None
    refutation_p_value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "treatment": self.treatment,
            "outcome": self.outcome,
            "method": self.method,
            "ate": round(self.ate, 4),
            "p_value": round(self.p_value, 4) if self.p_value is not None else None,
            "confidence_interval": [round(v, 4) for v in self.confidence_interval],
            "refutation_passed": self.refutation_passed,
            "refutation_p_value": (
                round(self.refutation_p_value, 4)
                if self.refutation_p_value is not None
                else None
            ),
        }


@dataclass
class CounterfactualResult:
    """Container for a counterfactual query result."""
    original_value: float
    counterfactual_value: float
    difference: float
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_value": round(self.original_value, 2),
            "counterfactual_value": round(self.counterfactual_value, 2),
            "difference": round(self.difference, 2),
            "confidence_interval": [round(v, 2) for v in self.confidence_interval],
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class DisasterCausalModel:
    """Wrapper around a DoWhy CausalModel for disaster-domain inference."""

    def __init__(self, data: pd.DataFrame | None = None):
        import dowhy  # deferred import – heavy dependency

        self._data = data if data is not None else generate_synthetic_data()
        self._gml = _build_gml_graph()
        self._model_cache: dict[str, Any] = {}
        self._estimate_cache: dict[str, Any] = {}
        logger.info(
            "DisasterCausalModel initialised with %d observations", len(self._data)
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self, treatment: str, outcome: str):
        """Build (or retrieve cached) DoWhy CausalModel."""
        import dowhy

        key = f"{treatment}->{outcome}"
        if key not in self._model_cache:
            model = dowhy.CausalModel(
                data=self._data,
                treatment=treatment,
                outcome=outcome,
                graph=self._gml,
            )
            self._model_cache[key] = model
        return self._model_cache[key]

    # ------------------------------------------------------------------
    # ATE estimation via backdoor
    # ------------------------------------------------------------------

    def estimate_ate(
        self,
        treatment: str,
        outcome: str,
        *,
        method: str = "backdoor.linear_regression",
        compute_ci: bool = True,
    ) -> CausalEstimateResult:
        """Estimate the Average Treatment Effect using the backdoor criterion.

        Parameters
        ----------
        treatment : str
            Name of the treatment variable (must be in CAUSAL_NODES).
        outcome : str
            Name of the outcome variable (must be in CAUSAL_NODES).
        method : str
            DoWhy estimation method name.
        compute_ci : bool
            Whether to compute bootstrap CI (slower). Default True.

        Returns
        -------
        CausalEstimateResult
        """
        model = self._get_model(treatment, outcome)
        identified = model.identify_effect(proceed_when_unidentifiable=True)
        estimate = model.estimate_effect(
            identified,
            method_name=method,
        )

        ate = float(estimate.value)

        # Derive a CI via bootstrap if requested (slower)
        if compute_ci:
            ci = self._bootstrap_ci(treatment, outcome, ate)
        else:
            # Fast fallback: approximate CI from standard error
            se = abs(ate) * 0.1  # rough 10% SE estimate
            ci = (ate - 1.96 * se, ate + 1.96 * se)

        result = CausalEstimateResult(
            treatment=treatment,
            outcome=outcome,
            method=method,
            ate=ate,
            confidence_interval=ci,
        )
        self._estimate_cache[f"{treatment}->{outcome}"] = result
        return result

    def _bootstrap_ci(
        self,
        treatment: str,
        outcome: str,
        point_estimate: float,
        n_bootstrap: int = 30,
        alpha: float = 0.05,
    ) -> tuple[float, float]:
        """Quick bootstrap confidence interval for the ATE."""
        import dowhy

        ates: list[float] = []
        sample_size = min(len(self._data), 400)  # subsample for speed
        for _ in range(n_bootstrap):
            sample = self._data.sample(sample_size, replace=True)
            try:
                m = dowhy.CausalModel(
                    data=sample,
                    treatment=treatment,
                    outcome=outcome,
                    graph=self._gml,
                )
                ident = m.identify_effect(proceed_when_unidentifiable=True)
                est = m.estimate_effect(
                    ident, method_name="backdoor.linear_regression"
                )
                ates.append(float(est.value))
            except Exception:
                continue

        if len(ates) < 10:
            se = abs(point_estimate) * 0.1
            return (point_estimate - 1.96 * se, point_estimate + 1.96 * se)

        lo = float(np.percentile(ates, 100 * alpha / 2))
        hi = float(np.percentile(ates, 100 * (1 - alpha / 2)))
        return (lo, hi)

    # ------------------------------------------------------------------
    # Refutation (placebo treatment test)
    # ------------------------------------------------------------------

    def refute_estimate(
        self,
        treatment: str,
        outcome: str,
        *,
        method: str = "backdoor.linear_regression",
        placebo_type: str = "placebo_treatment_refuter",
    ) -> CausalEstimateResult:
        """Estimate + refutation in one call.

        The placebo refuter replaces the real treatment with random noise.
        If the resulting "effect" is near zero (high p-value), the
        original estimate is considered robust.
        """
        result = self.estimate_ate(treatment, outcome, method=method)

        model = self._get_model(treatment, outcome)
        identified = model.identify_effect(proceed_when_unidentifiable=True)
        estimate = model.estimate_effect(
            identified, method_name=method,
        )

        try:
            refutation = model.refute_estimate(
                identified,
                estimate,
                method_name=placebo_type,
                placebo_type="permute",
                num_simulations=100,
            )
            ref_p = getattr(refutation, "refutation_result", {})
            if isinstance(ref_p, dict):
                p_val = ref_p.get("p_value", None)
            else:
                p_val = getattr(refutation, "p_value", None)

            result.refutation_passed = p_val is None or float(p_val) > 0.05
            result.refutation_p_value = float(p_val) if p_val is not None else None
        except Exception as exc:
            logger.warning("Refutation failed for %s->%s: %s", treatment, outcome, exc)
            result.refutation_passed = None
            result.refutation_p_value = None

        return result

    # ------------------------------------------------------------------
    # Pre-defined domain estimates
    # ------------------------------------------------------------------

    def estimate_response_time_on_casualties(self) -> CausalEstimateResult:
        """Effect of response_time_hours on casualties."""
        return self.refute_estimate("response_time_hours", "casualties")

    def estimate_resource_availability_on_damage(self) -> CausalEstimateResult:
        """Effect of resource_availability on economic_damage_usd."""
        return self.refute_estimate("resource_availability", "economic_damage_usd")

    # ------------------------------------------------------------------
    # Counterfactual analysis
    # ------------------------------------------------------------------

    def counterfactual(
        self,
        observation: dict[str, float],
        intervention_var: str,
        new_value: float,
        outcome_var: str = "casualties",
    ) -> CounterfactualResult:
        """Estimate the counterfactual outcome under an intervention.

        Uses the estimated ATE to project what *would have happened* if
        ``intervention_var`` had been set to ``new_value`` (all else
        being structurally equal).

        Parameters
        ----------
        observation : dict
            Current factual observation (must include all CAUSAL_NODES).
        intervention_var : str
            The variable we intervene on.
        new_value : float
            The counterfactual value for ``intervention_var``.
        outcome_var : str
            The outcome to predict (default ``"casualties"``).

        Returns
        -------
        CounterfactualResult
        """
        if intervention_var not in CAUSAL_NODES:
            raise ValueError(f"Unknown intervention variable: {intervention_var}")
        if outcome_var not in CAUSAL_NODES:
            raise ValueError(f"Unknown outcome variable: {outcome_var}")

        # Get or compute the ATE for this pair
        cache_key = f"{intervention_var}->{outcome_var}"
        if cache_key in self._estimate_cache:
            est = self._estimate_cache[cache_key]
        else:
            est = self.estimate_ate(intervention_var, outcome_var, compute_ci=False)

        original_value = float(observation.get(outcome_var, 0))
        delta_treatment = new_value - float(observation.get(intervention_var, 0))
        counterfactual_value = original_value + est.ate * delta_treatment
        counterfactual_value = max(0, counterfactual_value)

        diff = counterfactual_value - original_value

        # Propagate CI
        ci_lo = original_value + est.confidence_interval[0] * delta_treatment
        ci_hi = original_value + est.confidence_interval[1] * delta_treatment
        ci = (min(ci_lo, ci_hi), max(ci_lo, ci_hi))

        direction = "increase" if delta_treatment > 0 else "decrease"
        abs_delta = abs(delta_treatment)
        explanation = (
            f"If {intervention_var} had been {'increased' if delta_treatment > 0 else 'decreased'} "
            f"by {abs_delta:.2f} units (from {observation.get(intervention_var, 0):.2f} to "
            f"{new_value:.2f}), the estimated effect on {outcome_var} would be a change of "
            f"{diff:+.1f} (ATE per unit = {est.ate:.4f})."
        )

        return CounterfactualResult(
            original_value=original_value,
            counterfactual_value=counterfactual_value,
            difference=diff,
            confidence_interval=ci,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Ranked root causes
    # ------------------------------------------------------------------

    def rank_root_causes(self, outcome_var: str = "casualties") -> list[CausalEstimateResult]:
        """Rank all upstream causes of ``outcome_var`` by absolute ATE.

        Returns a list sorted descending by ``|ATE|``.
        """
        # Find all edges pointing into outcome_var
        treatments = [src for src, dst in CAUSAL_EDGES if dst == outcome_var]
        results: list[CausalEstimateResult] = []
        for t in treatments:
            try:
                # Skip bootstrap for ranking (fast); CI computed on demand
                est = self.estimate_ate(t, outcome_var, compute_ci=False)
                results.append(est)
            except Exception as exc:
                logger.warning("Could not estimate %s->%s: %s", t, outcome_var, exc)

        results.sort(key=lambda r: abs(r.ate), reverse=True)
        return results

    # ------------------------------------------------------------------
    # Top-K counterfactual interventions
    # ------------------------------------------------------------------

    def top_counterfactual_interventions(
        self,
        observation: dict[str, float],
        outcome_var: str = "casualties",
        k: int = 3,
    ) -> list[dict[str, Any]]:
        """Find the top-*k* single-variable interventions that would
        reduce ``outcome_var`` the most.

        For each upstream cause we test a ±1 standard-deviation shift
        in the direction that reduces the outcome.
        """
        treatments = [src for src, dst in CAUSAL_EDGES if dst == outcome_var]
        candidates: list[dict[str, Any]] = []

        for t in treatments:
            try:
                # Use cached ATE or compute without bootstrap for speed
                cache_key = f"{t}->{outcome_var}"
                if cache_key in self._estimate_cache:
                    est = self._estimate_cache[cache_key]
                else:
                    est = self.estimate_ate(t, outcome_var, compute_ci=False)
            except Exception:
                continue

            # Decide direction: if ATE > 0 we decrease treatment; if ATE < 0 we increase
            std = float(self._data[t].std())
            best_delta = -std if est.ate > 0 else std
            new_val = float(observation.get(t, self._data[t].mean())) + best_delta

            cf = self.counterfactual(observation, t, new_val, outcome_var)
            candidates.append({
                "variable": t,
                "current_value": round(float(observation.get(t, self._data[t].mean())), 2),
                "proposed_value": round(new_val, 2),
                "estimated_reduction": round(-cf.difference, 2),
                "confidence_interval": [round(v, 2) for v in cf.confidence_interval],
                "explanation": cf.explanation,
            })

        candidates.sort(key=lambda c: c["estimated_reduction"], reverse=True)
        return candidates[:k]

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_graph_edges(self) -> list[dict[str, str]]:
        """Return edges for visualisation."""
        return [{"source": s, "target": t} for s, t in CAUSAL_EDGES]

    @property
    def data(self) -> pd.DataFrame:
        return self._data

    def update_data(self, new_data: pd.DataFrame) -> None:
        """Replace the underlying dataset and clear caches."""
        self._data = new_data
        self._model_cache.clear()
        self._estimate_cache.clear()
        logger.info("Causal model data updated (%d rows)", len(new_data))
