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
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
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


def _haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points on Earth."""
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r


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
    disaster_type = np.clip(weather_severity * 0.6 + rng.normal(0, 1, n), 1, 10)
    ngo_proximity_km = np.clip(rng.exponential(50, n), 1, 500)

    response_time_hours = np.clip(disaster_type * 1.2 + ngo_proximity_km * 0.05 + rng.normal(0, 2, n), 0.5, 120)

    resource_availability = np.clip(5.0 - ngo_proximity_km * 0.01 + rng.normal(0, 0.5, n), 0.1, 10)

    resource_quality_score = np.clip(resource_availability * 0.5 + rng.normal(3, 1, n), 1, 10)

    casualties = (
        (
            weather_severity * 8
            + disaster_type * 5
            + response_time_hours * 3
            - resource_availability * 6
            - resource_quality_score * 2
            + rng.normal(0, 10, n)
        )
        .clip(0, None)
        .astype(int)
    )

    economic_damage_usd = (
        weather_severity * 500_000
        + disaster_type * 300_000
        - resource_availability * 200_000
        - resource_quality_score * 100_000
        + rng.normal(0, 200_000, n)
    ).clip(0, None)

    return pd.DataFrame(
        {
            "weather_severity": weather_severity,
            "disaster_type": disaster_type,
            "response_time_hours": response_time_hours,
            "resource_availability": resource_availability,
            "ngo_proximity_km": ngo_proximity_km,
            "resource_quality_score": resource_quality_score,
            "casualties": casualties,
            "economic_damage_usd": economic_damage_usd,
        }
    )


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
        ate_val = float(self.ate) if self.ate is not None else 0.0
        p_val = float(self.p_value) if self.p_value is not None else None
        ci_vals = [float(v) if v is not None else 0.0 for v in self.confidence_interval]

        return {
            "treatment": self.treatment,
            "outcome": self.outcome,
            "method": self.method,
            "ate": round(ate_val, 4),
            "p_value": round(p_val, 4) if p_val is not None else None,
            "confidence_interval": [round(v, 4) for v in ci_vals],
            "refutation_passed": self.refutation_passed,
            "refutation_p_value": (
                round(float(self.refutation_p_value), 4) if self.refutation_p_value is not None else None
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
        orig_val = float(self.original_value) if self.original_value is not None else 0.0
        cf_val = float(self.counterfactual_value) if self.counterfactual_value is not None else 0.0
        diff_val = float(self.difference) if self.difference is not None else 0.0
        ci_vals = [float(v) if v is not None else 0.0 for v in self.confidence_interval]

        return {
            "original_value": round(orig_val, 2),
            "counterfactual_value": round(cf_val, 2),
            "difference": round(diff_val, 2),
            "confidence_interval": [round(v, 2) for v in ci_vals],
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------


class DisasterCausalModel:
    """Wrapper around a DoWhy CausalModel for disaster-domain inference."""

    def __init__(self, data: pd.DataFrame | None = None):

        self._data = data if data is not None else generate_synthetic_data()
        self._gml = _build_gml_graph()
        self._model_cache: dict[str, Any] = {}
        self._estimate_cache: dict[str, Any] = {}
        logger.info("DisasterCausalModel initialised with %d observations", len(self._data))

    @classmethod
    async def from_database(cls) -> DisasterCausalModel:
        """Build a causal model from real disaster data in the database."""
        from app.database import db

        try:
            # 1. Fetch data in bulk to avoid N+1 queries
            logger.info("Fetching disaster data from database for causal model...")

            # Disasters
            disasters_resp = await db.table("disasters").select("*").limit(2000).async_execute()
            disasters = disasters_resp.data or []

            if len(disasters) < 20:  # Lowered threshold slightly to be more useful in early stages
                logger.warning(
                    "Not enough disaster records (%d) for causal analysis — using synthetic data", len(disasters)
                )
                return cls()

            # Locations
            locations_resp = await db.table("locations").select("id, latitude, longitude").async_execute()
            locations = {loc["id"]: loc for loc in (locations_resp.data or [])}

            # NGOs
            ngo_resp = await db.table("users").select("id, metadata").eq("role", "ngo").async_execute()
            ngos = ngo_resp.data or []

            # Resource Requests
            requests_resp = await db.table("resource_requests").select("disaster_id, priority, status").async_execute()
            requests = requests_resp.data or []
            requests_by_disaster = {}
            for req in requests:
                dis_id = req.get("disaster_id")
                if dis_id:
                    requests_by_disaster.setdefault(dis_id, []).append(req)

            # Mobilizations (needed for both assignments and NGO locations)
            mobs_resp = (
                await db.table("ngo_mobilization").select("id, disaster_id, ngo_id, location_id").async_execute()
            )
            mobs = mobs_resp.data or []
            mob_map = {m["id"]: m for m in mobs}

            # Build NGO -> Location mapping from both user metadata and mobilizations
            ngo_locations = {}
            for ngo in ngos:
                ngo_id = ngo["id"]
                # Priority 1: User metadata
                loc_id = ngo.get("metadata", {}).get("location_id")
                if loc_id:
                    ngo_locations[ngo_id] = loc_id
                else:
                    # Priority 2: Latest mobilization
                    for m in mobs:
                        if m["ngo_id"] == ngo_id and m.get("location_id"):
                            ngo_locations[ngo_id] = m["location_id"]
                            break

            # Volunteer Assignments
            assignments_resp = (
                await db.table("volunteer_assignments").select("mobilization_id, assigned_at").async_execute()
            )
            assignments = assignments_resp.data or []
            assignments_by_disaster = {}
            for assignment in assignments:
                mob_id = assignment.get("mobilization_id")
                if mob_id and mob_id in mob_map:
                    dis_id = mob_map[mob_id].get("disaster_id")
                    if dis_id:
                        assignments_by_disaster.setdefault(dis_id, []).append(assignment)

            # 2. Process rows
            rows = []
            for d in disasters:
                dis_id = d["id"]
                loc_id = d.get("location_id")
                location = locations.get(loc_id)

                if not location:
                    continue

                severity_score = cls._map_severity_to_score(d.get("severity", "medium"))
                response_time_hours = cls._calculate_response_time(
                    d["created_at"], assignments_by_disaster.get(dis_id, [])
                )
                resource_count = len(requests_by_disaster.get(dis_id, []))

                # Calculate NGO distance using pre-fetched data
                ngo_distance_km = cls._calculate_nearest_ngo_distance_fast(
                    float(location["latitude"]), float(location["longitude"]), ngo_locations, locations
                )

                resource_quality_score = cls._calculate_resource_quality_score(requests_by_disaster.get(dis_id, []))

                rows.append(
                    {
                        "weather_severity": severity_score,
                        "disaster_type": cls._map_disaster_type_to_score(d.get("type", "other")),
                        "response_time_hours": response_time_hours,
                        "resource_availability": resource_count,
                        "ngo_proximity_km": ngo_distance_km,
                        "resource_quality_score": resource_quality_score,
                        "casualties": int(d.get("casualties", 0) or 0),
                        "economic_damage_usd": float(d.get("estimated_damage", 0) or 0),
                    }
                )

            if not rows:
                return cls()

            df = pd.DataFrame(rows)
            df = df.fillna(df.mean(numeric_only=True))

            return cls(data=df)

        except Exception as e:
            logger.warning("Failed to query disasters for causal model: %s", e)
            return cls()

    # ------------------------------------------------------------------
    # Field mapping methods
    # ------------------------------------------------------------------

    @staticmethod
    def _map_severity_to_score(severity_str: str) -> float:
        """Map severity string to numeric score (low=1, medium=5, high=7, critical=10)."""
        severity_mapping = {"low": 1.0, "medium": 5.0, "high": 7.0, "critical": 10.0}
        return severity_mapping.get(severity_str.lower(), 5.0)  # Default to medium

    @staticmethod
    def _map_disaster_type_to_score(type_str: str) -> float:
        """Map disaster type to numeric score for modeling purposes."""
        type_mapping = {
            "earthquake": 8.0,
            "flood": 6.0,
            "hurricane": 9.0,
            "tornado": 7.0,
            "wildfire": 5.0,
            "tsunami": 10.0,
            "drought": 3.0,
            "landslide": 6.0,
            "volcano": 7.0,
            "other": 4.0,
        }
        return type_mapping.get(type_str.lower(), 4.0)

    @staticmethod
    def _calculate_response_time(disaster_created_at: str, assignments: list) -> float:
        """Calculate response time from disaster creation to first assignment in hours."""
        if not assignments:
            return 24.0  # Default response time if no assignments

        try:
            from datetime import datetime

            disaster_time = datetime.fromisoformat(disaster_created_at.replace("Z", "+00:00"))

            # Find earliest assignment
            earliest_assignment = None
            for assignment in assignments:
                assigned_at = assignment.get("assigned_at")
                if assigned_at:
                    assignment_time = datetime.fromisoformat(assigned_at.replace("Z", "+00:00"))
                    if earliest_assignment is None or assignment_time < earliest_assignment:
                        earliest_assignment = assignment_time

            if earliest_assignment is not None and disaster_time is not None:
                time_diff = earliest_assignment - disaster_time
                return max(0.5, float(time_diff.total_seconds() or 0) / 3600)  # Minimum 30 minutes

        except Exception as e:
            logger.warning("Error calculating response time: %s", e)

        return 24.0  # Default fallback

    @staticmethod
    def _calculate_nearest_ngo_distance_fast(
        disaster_lat: float, disaster_lon: float, ngo_locations: dict[str, str], locations: dict[str, dict]
    ) -> float:
        """Calculate distance from disaster to nearest NGO using pre-fetched data."""
        if not ngo_locations:
            return 100.0

        min_distance = float("inf")
        for ngo_id, loc_id in ngo_locations.items():
            if loc_id in locations:
                loc = locations[loc_id]
                dist = _haversine_distance(disaster_lat, disaster_lon, float(loc["latitude"]), float(loc["longitude"]))
                if dist < min_distance:
                    min_distance = dist

        return min_distance if min_distance != float("inf") else 100.0

    @staticmethod
    def _calculate_resource_quality_score(requests: list) -> float:
        """Calculate resource quality score based on request fulfillment and priority."""
        if not requests:
            return 3.0  # Default low quality if no requests

        total_score = 0.0
        count = 0

        for req in requests:
            # Base score from priority (convert text to numeric)
            priority_scores = {"high": 8.0, "medium": 5.0, "low": 2.0}
            priority_score = priority_scores.get(req.get("priority", "medium").lower(), 5.0)

            # Adjust based on status (completed requests get higher score)
            status = req.get("status", "pending")
            if status in ["completed", "delivered"]:
                priority_score += 2.0
            elif status in ["rejected", "closed"]:
                priority_score -= 2.0

            # Consider NLP confidence if available
            nlp_confidence = req.get("nlp_confidence", 0.5)
            priority_score *= 0.5 + nlp_confidence * 0.5  # Scale by confidence

            total_score += priority_score
            count += 1

        return (total_score / count) if count > 0 else 3.0

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
                est = m.estimate_effect(ident, method_name="backdoor.linear_regression")
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
            identified,
            method_name=method,
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
        ci_lo = original_value + float(est.confidence_interval[0] or 0.0) * delta_treatment
        ci_hi = original_value + float(est.confidence_interval[1] or 0.0) * delta_treatment
        ci = (min(ci_lo, ci_hi), max(ci_lo, ci_hi))

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
        treatments = []
        for src, dst in CAUSAL_EDGES:
            if dst == outcome_var:
                treatments.append(src)
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
        treatments = []
        for src, dst in CAUSAL_EDGES:
            if dst == outcome_var:
                treatments.append(src)
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
            try:
                current_val = float(observation.get(t, self._data[t].mean()))
            except (KeyError, AttributeError):
                current_val = 0.0
            cf_diff = float(-cf.difference) if cf.difference is not None else 0.0
            ci_vals = [float(v) if v is not None else 0.0 for v in cf.confidence_interval]

            candidates.append(
                {
                    "variable": t,
                    "current_value": round(current_val, 2),
                    "proposed_value": round(float(new_val), 2),
                    "estimated_reduction": round(cf_diff, 2),
                    "confidence_interval": [round(v, 2) for v in ci_vals],
                    "explanation": cf.explanation,
                }
            )

        candidates.sort(key=lambda c: float(c.get("estimated_reduction", 0)), reverse=True)
        return candidates[:k] if len(candidates) >= k else candidates

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
