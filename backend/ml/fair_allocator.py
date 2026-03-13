"""
Fairness-constrained resource allocator.

Takes base allocation from the existing GAT / LP engine and applies
post-processing fairness constraints:
  • Rural access multiplier           (1.3× when < 5 NGOs within 20 km)
  • Vulnerability priority bump       (victims with index > 0.7)
  • Historical underservice compensator (+20% when score > 2)

Also computes a 10-point Pareto frontier between pure-efficiency and
pure-equity for the admin fairness slider.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.allocation_engine import (
    AllocationResult,
    AvailableResource,
    PriorityWeights,
    ResourceNeed,
    solve_allocation,
)
from ml.fairness_metrics import (
    HistoricalRecord,
    ZoneAllocation,
    ZoneDemographics,
    compute_fairness_report,
    equity_score,
    gini_per_capita,
    historical_underservice_scores,
    vulnerability_index,
    vulnerability_scores,
)

logger = logging.getLogger(__name__)


# ── Configuration constants ───────────────────────────────────────────────────

RURAL_NGO_THRESHOLD = 5  # < 5 NGOs within 20 km → "under-served rural"
RURAL_MULTIPLIER = 1.3  # 30 % resource uplift for rural zones
VULNERABILITY_PRIORITY_CUTOFF = 0.7  # bump priority when vuln index > this
UNDERSERVICE_THRESHOLD = 2  # compensatory boost when score > 2
UNDERSERVICE_BONUS = 0.20  # +20 % resources
PARETO_POINTS = 10  # number of frontier points


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class FairAllocationPlan:
    """A single allocation plan with associated scores."""

    plan_index: int = 0
    equity_weight: float = 0.0  # 0 = pure efficiency, 1 = pure equity
    allocations: list[dict[str, Any]] = field(default_factory=list)
    efficiency_score: float = 0.0  # coverage-based
    equity_score: float = 0.0  # fairness-based
    gini: float = 0.0
    zone_allocations: dict[str, float] = field(default_factory=dict)
    adjustments_applied: list[str] = field(default_factory=list)


@dataclass
class ParetoFrontier:
    """Collection of allocation plans on the Pareto frontier."""

    plans: list[FairAllocationPlan] = field(default_factory=list)
    disaster_id: str | None = None


# ── Fairness Adjustments ──────────────────────────────────────────────────────


def apply_rural_multiplier(
    allocations: list[dict[str, Any]],
    zone_demographics: dict[str, ZoneDemographics],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Multiply resource quantities by 1.3× for zones flagged as rural
    with fewer than 5 NGOs within 20 km.
    """
    adjusted = []
    notes: list[str] = []

    for alloc in allocations:
        a = copy.deepcopy(alloc)
        zone_id = a.get("zone_id") or a.get("location", "")
        zone = zone_demographics.get(zone_id)

        if zone and zone.is_rural and zone.ngo_count_within_20km < RURAL_NGO_THRESHOLD:
            original_qty = a.get("quantity", 0)
            boosted = round(original_qty * RURAL_MULTIPLIER, 2)
            a["quantity"] = boosted
            a["rural_boost_applied"] = True
            notes.append(f"Zone {zone_id}: rural boost {original_qty} → {boosted}")
        adjusted.append(a)

    return adjusted, notes


def apply_vulnerability_priority(
    allocations: list[dict[str, Any]],
    zone_demographics: dict[str, ZoneDemographics],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Bump the priority of allocations going to zones whose vulnerability
    index exceeds the cutoff (0.7).  The bump moves priority to the
    maximum (10) so that dispatching systems handle them first.
    """
    notes: list[str] = []
    vuln_map = vulnerability_scores(list(zone_demographics.values()))

    for alloc in allocations:
        zone_id = alloc.get("zone_id") or alloc.get("location", "")
        vuln = vuln_map.get(zone_id, 0.0)
        if vuln > VULNERABILITY_PRIORITY_CUTOFF:
            old_prio = alloc.get("priority", 5)
            alloc["priority"] = 10
            alloc["vulnerability_bump"] = True
            notes.append(
                f"Zone {zone_id}: vuln {vuln:.2f} > {VULNERABILITY_PRIORITY_CUTOFF} → priority {old_prio} → 10"
            )

    return allocations, notes


def apply_underservice_compensation(
    allocations: list[dict[str, Any]],
    underservice_map: dict[str, int],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Add +20 % resources to zones historically underserved (score > 2).
    """
    notes: list[str] = []

    for alloc in allocations:
        zone_id = alloc.get("zone_id") or alloc.get("location", "")
        score = underservice_map.get(zone_id, 0)
        if score > UNDERSERVICE_THRESHOLD:
            original_qty = alloc.get("quantity", 0)
            bonus = round(original_qty * UNDERSERVICE_BONUS, 2)
            alloc["quantity"] = round(original_qty + bonus, 2)
            alloc["underservice_bonus_applied"] = True
            notes.append(
                f"Zone {zone_id}: underservice score {score} > {UNDERSERVICE_THRESHOLD} "
                f"→ +{bonus} ({UNDERSERVICE_BONUS * 100:.0f}%)"
            )

    return allocations, notes


# ── Scoring helpers ───────────────────────────────────────────────────────────


def _efficiency_score(result: AllocationResult) -> float:
    """Fraction of needs met (coverage percentage normalised to 0-1)."""
    # Handle edge cases where coverage_pct might be None, 0, or undefined
    coverage_pct = getattr(result, "coverage_pct", 0.0) or 0.0

    # If no needs exist, efficiency is 1.0 (perfect since nothing to allocate)
    if not hasattr(result, "allocations") or not result.allocations:
        # Check if there are any needs at all
        needs_count = getattr(result, "unmet_needs", []) or []
        if not needs_count and not hasattr(result, "unmet_needs"):
            return 1.0

    # Normalize to 0-1 range, ensuring we don't divide by zero
    efficiency = max(0.0, min(1.0, coverage_pct / 100.0))

    # Additional safety: if we have allocations but 0% coverage, calculate manually
    if efficiency == 0.0 and hasattr(result, "allocations") and result.allocations:
        # Calculate efficiency based on actual allocations vs needs
        total_allocated = sum(a.get("quantity", 0) for a in result.allocations)
        total_needs = sum(u.get("quantity", 0) for u in getattr(result, "unmet_needs", []))

        if total_needs > 0:
            efficiency = min(1.0, total_allocated / total_needs)
        else:
            efficiency = 1.0

    return efficiency


def _equity_from_allocations(
    allocations: list[dict[str, Any]],
    zones: list[ZoneDemographics],
) -> float:
    """Compute equity score from a list of allocation dicts."""
    zone_alloc: dict[str, float] = {}
    for a in allocations:
        zid = a.get("zone_id") or a.get("location", "")
        zone_alloc[zid] = zone_alloc.get(zid, 0.0) + a.get("quantity", 0.0)

    alloc_list = [zone_alloc.get(z.zone_id, 0.0) for z in zones]
    pop_list = [z.population for z in zones]
    gini = gini_per_capita(alloc_list, pop_list)
    vuln_map = vulnerability_scores(zones)
    return equity_score(gini, vuln_map, zone_alloc)


# ── Fair allocation pipeline ─────────────────────────────────────────────────


def fair_allocate(
    resources: list[AvailableResource],
    needs: list[ResourceNeed],
    zones: list[ZoneDemographics],
    historical_records: list[HistoricalRecord],
    weights: PriorityWeights | None = None,
    max_distance_km: float = 500.0,
    equity_weight: float = 0.5,
) -> FairAllocationPlan:
    """
    Run the base allocator then apply fairness post-processing.

    Parameters
    ----------
    equity_weight : 0 = pure efficiency (no adjustments),
                    1 = full fairness adjustments applied.
    """
    # 1. Base allocation from existing LP solver
    base_result = solve_allocation(resources, needs, weights, max_distance_km)

    # 2. Enrich allocations with zone_id (use location field)
    allocations = copy.deepcopy(base_result.allocations)
    for a in allocations:
        if "zone_id" not in a:
            a["zone_id"] = a.get("location", "")

    all_notes: list[str] = []
    zone_demo_map = {z.zone_id: z for z in zones}
    underservice_map = historical_underservice_scores([z.zone_id for z in zones], historical_records)

    # 3. Apply fairness constraints (scaled by equity_weight)
    if equity_weight > 0:
        # Rural multiplier (scale the multiplier bonus by equity_weight)
        if equity_weight >= 0.3:
            allocations, notes = apply_rural_multiplier(allocations, zone_demo_map)
            all_notes.extend(notes)

        # Vulnerability priority bump
        if equity_weight >= 0.2:
            allocations, notes = apply_vulnerability_priority(allocations, zone_demo_map)
            all_notes.extend(notes)

        # Historical underservice compensation
        if equity_weight >= 0.5:
            allocations, notes = apply_underservice_compensation(allocations, underservice_map)
            all_notes.extend(notes)

    # 4. Compute scores
    eff = _efficiency_score(base_result)

    # Equity blending: at equity_weight=0 we use pure-efficiency equity,
    # at equity_weight=1 we use the fully-adjusted equity.
    eq = _equity_from_allocations(allocations, zones) if zones else 0.0

    zone_alloc_map: dict[str, float] = {}
    for a in allocations:
        zid = a.get("zone_id", "")
        zone_alloc_map[zid] = zone_alloc_map.get(zid, 0.0) + a.get("quantity", 0.0)

    alloc_list_vals = [zone_alloc_map.get(z.zone_id, 0.0) for z in zones]
    pop_list = [z.population for z in zones]
    gini = gini_per_capita(alloc_list_vals, pop_list) if zones else 0.0

    return FairAllocationPlan(
        equity_weight=equity_weight,
        allocations=allocations,
        efficiency_score=round(eff, 4),
        equity_score=round(eq, 4),
        gini=round(gini, 4),
        zone_allocations=zone_alloc_map,
        adjustments_applied=all_notes,
    )


# ── Pareto Frontier ──────────────────────────────────────────────────────────


def compute_pareto_frontier(
    resources: list[AvailableResource],
    needs: list[ResourceNeed],
    zones: list[ZoneDemographics],
    historical_records: list[HistoricalRecord],
    weights: PriorityWeights | None = None,
    max_distance_km: float = 500.0,
    n_points: int = PARETO_POINTS,
    disaster_id: str | None = None,
) -> ParetoFrontier:
    """
    Compute *n_points* allocation plans along the efficiency–equity
    trade-off.  Each point uses a different ``equity_weight`` from 0
    (pure efficiency) to 1 (pure equity).

    Returns a ParetoFrontier containing the plans.
    """
    frontier = ParetoFrontier(disaster_id=disaster_id)

    for i in range(n_points):
        ew = i / max(n_points - 1, 1)
        plan = fair_allocate(
            resources=resources,
            needs=needs,
            zones=zones,
            historical_records=historical_records,
            weights=weights,
            max_distance_km=max_distance_km,
            equity_weight=round(ew, 2),
        )
        plan.plan_index = i
        frontier.plans.append(plan)

    return frontier


# ── Audit report generation ──────────────────────────────────────────────────


def generate_fairness_audit(
    zones: list[ZoneDemographics],
    allocations: list[ZoneAllocation],
    historical_records: list[HistoricalRecord],
    disaster_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate a post-allocation fairness audit report.

    Returns a JSON-serialisable dict suitable for storage and API responses.
    """
    report = compute_fairness_report(zones, allocations, historical_records)

    return {
        "disaster_id": disaster_id,
        "gini_coefficient": report.gini_coefficient,
        "overall_equity_score": report.overall_equity_score,
        "vulnerability_scores": report.vulnerability_scores,
        "underservice_scores": report.underservice_scores,
        "zone_details": report.zone_details,
        "distribution_by_vulnerability_group": report.distribution_by_vulnerability,
        "summary": {
            "total_zones": len(zones),
            "high_vulnerability_zones": sum(
                1 for z in zones if vulnerability_index(z) >= VULNERABILITY_PRIORITY_CUTOFF
            ),
            "underserved_zones": sum(1 for s in report.underservice_scores.values() if s > UNDERSERVICE_THRESHOLD),
            "rural_access_constrained": sum(
                1 for z in zones if z.is_rural and z.ngo_count_within_20km < RURAL_NGO_THRESHOLD
            ),
        },
    }
