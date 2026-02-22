"""
Constraint-based resource allocation engine.

Uses PuLP to formulate and solve a Mixed-Integer Linear Program (MILP) that
maximises disaster-zone coverage while minimising weighted delivery distance.

Decision variables
------------------
x[i][j]  ∈ {0, 1}  — whether resource *i* is allocated to need *j*.

Objective
---------
Maximise  Σ_j  (urgency_j × coverage_j)
        – λ Σ_ij x_ij × dist_ij
        + μ Σ_ij x_ij × expiry_score_i

Constraints
-----------
* Each resource allocated at most once.
* Quantity supplied to a need ≤ quantity of the resource.
* Distance cap: x_ij = 0 when dist_ij > max_distance_km.
* Type matching: x_ij = 0 when resource type ≠ required type.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pulp

from app.services.distance import haversine

logger = logging.getLogger(__name__)

# ── Data classes ──────────────────────────────────────────────────────────


@dataclass
class AvailableResource:
    """A resource that can be allocated."""

    id: str
    resource_type: str
    quantity: float
    priority: int  # 1-10
    location_lat: float
    location_lng: float
    location_id: str
    # Optional shelf-life / expiry fields for perishables
    expiry_date: Optional[datetime] = None


@dataclass
class ResourceNeed:
    """A single requirement from the disaster zone."""

    need_type: str
    quantity: float
    urgency: float = 5.0  # 1-10 scale
    zone_lat: float = 0.0
    zone_lng: float = 0.0


@dataclass
class PriorityWeights:
    """User-tunable weights fed into the objective function."""

    urgency_weight: float = 1.0
    distance_weight: float = 0.3
    expiry_weight: float = 0.2
    coverage_weight: float = 1.0


@dataclass
class AllocationResult:
    """Output of the optimiser."""

    allocations: List[Dict[str, Any]] = field(default_factory=list)
    unmet_needs: List[Dict[str, Any]] = field(default_factory=list)
    coverage_pct: float = 0.0
    estimated_delivery_km: float = 0.0
    optimization_score: float = 0.0
    solver_status: str = "not_solved"


# ── Helpers ───────────────────────────────────────────────────────────────


def _expiry_score(resource: AvailableResource, now: datetime | None = None) -> float:
    """
    Return a score in [0, 1] — higher means closer to expiry → prefer this
    resource for allocation so it doesn't go to waste.

    Non-perishable resources (no expiry date) get a neutral score of 0.5.
    """
    if resource.expiry_date is None:
        return 0.5
    now = now or datetime.utcnow()
    days_left = max((resource.expiry_date - now).total_seconds() / 86400, 0)
    # Sigmoid-like decay: 1 when days_left=0, ~0 when days_left≥90
    return math.exp(-0.05 * days_left)


# ── Solver ────────────────────────────────────────────────────────────────


def solve_allocation(
    resources: List[AvailableResource],
    needs: List[ResourceNeed],
    weights: PriorityWeights | None = None,
    max_distance_km: float = 500.0,
) -> AllocationResult:
    """
    Run the LP/MILP allocation optimiser.

    Parameters
    ----------
    resources : available resources from the database.
    needs     : list of requirements for a disaster zone.
    weights   : tunable objective-function weights.
    max_distance_km : hard cap — resources further than this are excluded.

    Returns
    -------
    AllocationResult with the optimised allocation plan.
    """
    weights = weights or PriorityWeights()
    result = AllocationResult()

    if not resources or not needs:
        result.solver_status = "trivial_empty"
        result.unmet_needs = [
            {"type": n.need_type, "quantity": n.quantity, "urgency": n.urgency}
            for n in needs
        ]
        return result

    n_res = len(resources)
    n_needs = len(needs)

    # ── Pre-compute distance & eligibility matrices ───────────────────
    dist: List[List[float]] = []
    eligible: List[List[bool]] = []
    for i, r in enumerate(resources):
        row_dist: List[float] = []
        row_elig: List[bool] = []
        for j, n in enumerate(needs):
            d = haversine(r.location_lat, r.location_lng, n.zone_lat, n.zone_lng)
            row_dist.append(d)
            # Eligible if same type, within distance, and enough quantity
            row_elig.append(
                r.resource_type == n.need_type
                and d <= max_distance_km
                and r.quantity >= n.quantity
            )
        dist.append(row_dist)
        eligible.append(row_elig)

    # ── Build MILP ────────────────────────────────────────────────────
    prob = pulp.LpProblem("ResourceAllocation", pulp.LpMaximize)

    # Binary decision variables
    x = [
        [
            pulp.LpVariable(f"x_{i}_{j}", cat=pulp.LpBinary)
            for j in range(n_needs)
        ]
        for i in range(n_res)
    ]

    # Objective: weighted coverage – distance penalty + expiry bonus
    now = datetime.utcnow()
    obj_terms = []
    for i in range(n_res):
        exp_s = _expiry_score(resources[i], now)
        for j in range(n_needs):
            if not eligible[i][j]:
                # Force ineligible pairs to zero
                prob += x[i][j] == 0, f"ineligible_{i}_{j}"
                continue
            urgency_val = needs[j].urgency * weights.urgency_weight
            coverage_val = (needs[j].quantity / max(sum(n.quantity for n in needs), 1)) * weights.coverage_weight
            dist_penalty = (dist[i][j] / max(max_distance_km, 1)) * weights.distance_weight
            expiry_bonus = exp_s * weights.expiry_weight

            obj_terms.append(
                x[i][j] * (urgency_val + coverage_val + expiry_bonus - dist_penalty)
            )

    if obj_terms:
        prob += pulp.lpSum(obj_terms), "TotalObjective"
    else:
        # Nothing eligible — return immediately
        result.solver_status = "infeasible_no_eligible"
        result.unmet_needs = [
            {"type": n.need_type, "quantity": n.quantity, "urgency": n.urgency}
            for n in needs
        ]
        return result

    # Constraint 1: each resource allocated to at most one need
    for i in range(n_res):
        prob += (
            pulp.lpSum(x[i][j] for j in range(n_needs)) <= 1,
            f"one_alloc_{i}",
        )

    # Constraint 2: each need satisfied by at most one resource
    # (extend to multi-source in future phases)
    for j in range(n_needs):
        prob += (
            pulp.lpSum(x[i][j] for i in range(n_res)) <= 1,
            f"one_source_{j}",
        )

    # ── Solve ─────────────────────────────────────────────────────────
    solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=30)
    prob.solve(solver)
    result.solver_status = pulp.LpStatus[prob.status]

    if prob.status != pulp.constants.LpStatusOptimal:
        logger.warning("Solver did not find an optimal solution: %s", result.solver_status)
        result.unmet_needs = [
            {"type": n.need_type, "quantity": n.quantity, "urgency": n.urgency}
            for n in needs
        ]
        return result

    # ── Extract solution ──────────────────────────────────────────────
    met_indices: set[int] = set()
    total_dist = 0.0
    for i in range(n_res):
        for j in range(n_needs):
            if pulp.value(x[i][j]) and pulp.value(x[i][j]) > 0.5:
                met_indices.add(j)
                total_dist += dist[i][j]
                result.allocations.append(
                    {
                        "resource_id": resources[i].id,
                        "type": resources[i].resource_type,
                        "quantity": needs[j].quantity,
                        "location": resources[i].location_id,
                        "distance_km": round(dist[i][j], 2),
                        "expiry_date": (
                            resources[i].expiry_date.isoformat()
                            if resources[i].expiry_date
                            else None
                        ),
                    }
                )

    for j in range(n_needs):
        if j not in met_indices:
            result.unmet_needs.append(
                {
                    "type": needs[j].need_type,
                    "quantity": needs[j].quantity,
                    "urgency": needs[j].urgency,
                }
            )

    result.coverage_pct = round(
        len(met_indices) / n_needs * 100 if n_needs else 0, 2
    )
    result.estimated_delivery_km = round(total_dist, 2)
    result.optimization_score = round(
        len(met_indices) / n_needs if n_needs else 0, 4
    )

    return result
