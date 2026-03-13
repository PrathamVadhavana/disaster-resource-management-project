"""
Fairness metrics for disaster resource allocation.

Provides geographic equity (Gini coefficient), vulnerability indexing,
and historical underservice scoring across grid zones.

Uses concepts from Fairlearn for equitable allocation auditing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class ZoneDemographics:
    """Demographic breakdown for a geographic zone."""

    zone_id: str
    zone_name: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    population: int = 0
    elderly_ratio: float = 0.0  # fraction of pop ≥ 65
    children_ratio: float = 0.0  # fraction of pop ≤ 14
    medical_needs_ratio: float = 0.0  # fraction with chronic / urgent medical needs
    ngo_count_within_20km: int = 0
    is_rural: bool = False


@dataclass
class ZoneAllocation:
    """Resource allocation record for a single zone."""

    zone_id: str
    allocated_quantity: float = 0.0
    needed_quantity: float = 0.0
    resource_types: dict[str, float] = field(default_factory=dict)


@dataclass
class HistoricalRecord:
    """Simplified record of past disaster resource allocation for a zone."""

    disaster_id: str
    zone_id: str
    resources_received: float = 0.0
    median_resources: float = 0.0  # median across all zones for that disaster


@dataclass
class FairnessReport:
    """Complete fairness audit report."""

    gini_coefficient: float = 0.0
    vulnerability_scores: dict[str, float] = field(default_factory=dict)
    underservice_scores: dict[str, int] = field(default_factory=dict)
    zone_details: list[dict[str, Any]] = field(default_factory=list)
    distribution_by_vulnerability: dict[str, dict[str, Any]] = field(default_factory=dict)
    overall_equity_score: float = 0.0  # 0–1, higher = more equitable


# ── Gini Coefficient ─────────────────────────────────────────────────────────


def gini_coefficient(allocations: list[float]) -> float:
    """
    Compute the Gini coefficient of resource allocations across zones.

    Parameters
    ----------
    allocations : per-zone allocation quantities (non-negative).

    Returns
    -------
    Gini coefficient in [0, 1].  0 = perfect equality, 1 = maximal inequality.
    """
    if not allocations or all(a == 0 for a in allocations):
        return 0.0

    arr = np.array(allocations, dtype=np.float64)
    arr = np.sort(arr)
    n = len(arr)
    total = arr.sum()
    if total == 0:
        return 0.0

    # Standard Gini formula: G = (2 * Σ i*y_i) / (n * Σ y_i) – (n+1)/n
    index = np.arange(1, n + 1)
    return float((2.0 * np.dot(index, arr)) / (n * total) - (n + 1.0) / n)


def gini_per_capita(allocations: list[float], populations: list[int]) -> float:
    """Gini on *per-capita* allocation — fairer comparison across zones."""
    if not allocations or not populations:
        return 0.0
    per_cap = [a / max(p, 1) for a, p in zip(allocations, populations)]
    return gini_coefficient(per_cap)


# ── Vulnerability Index ───────────────────────────────────────────────────────


def vulnerability_index(zone: ZoneDemographics) -> float:
    """
    Compute a vulnerability score for a zone.

    weighted score = 0.4 * elderly_ratio
                   + 0.3 * children_ratio
                   + 0.3 * medical_needs_ratio

    Returns
    -------
    Score in [0, 1].  Higher = more vulnerable.
    """
    return 0.4 * _clamp(zone.elderly_ratio) + 0.3 * _clamp(zone.children_ratio) + 0.3 * _clamp(zone.medical_needs_ratio)


def vulnerability_scores(
    zones: list[ZoneDemographics],
) -> dict[str, float]:
    """Return ``{zone_id: vulnerability_index}`` for every zone."""
    return {z.zone_id: round(vulnerability_index(z), 4) for z in zones}


# ── Historical Under-service Score ────────────────────────────────────────────


def historical_underservice(zone_id: str, records: list[HistoricalRecord], n_disasters: int = 3) -> int:
    """
    Count how many of the *last n_disasters* the zone received fewer
    resources than the median across all zones.

    Returns
    -------
    Integer count in [0, n_disasters].
    """
    zone_records = [r for r in records if r.zone_id == zone_id]
    # Take the most recent n_disasters
    zone_records = zone_records[-n_disasters:]
    return sum(1 for r in zone_records if r.resources_received < r.median_resources)


def historical_underservice_scores(
    zone_ids: list[str],
    records: list[HistoricalRecord],
    n_disasters: int = 3,
) -> dict[str, int]:
    """Return ``{zone_id: underservice_count}`` for every zone."""
    return {zid: historical_underservice(zid, records, n_disasters) for zid in zone_ids}


# ── Composite Equity Score ────────────────────────────────────────────────────


def equity_score(
    gini: float,
    vulnerability_map: dict[str, float],
    allocations_map: dict[str, float],
) -> float:
    """
    Return a composite equity score in [0, 1] (higher = more equitable).

    Components:
      • (1 – gini)           — allocation evenness
      • vulnerability-weighted adequacy — do high-vulnerability zones get enough?

    The two components are averaged with equal weight.
    """
    evenness = 1.0 - _clamp(gini)

    # Vulnerability-weighted adequacy: correlation between vulnerability
    # and allocation share.  If high-vuln zones get proportional share → 1.
    if not vulnerability_map or not allocations_map:
        return round(evenness, 4)

    zone_ids = list(set(vulnerability_map.keys()) & set(allocations_map.keys()))
    if not zone_ids:
        return round(evenness, 4)

    vuln = np.array([vulnerability_map[z] for z in zone_ids])
    alloc = np.array([allocations_map.get(z, 0.0) for z in zone_ids])
    total_alloc = alloc.sum()
    if total_alloc == 0 or vuln.sum() == 0:
        return round(evenness, 4)

    # Normalise to proportions
    vuln_share = vuln / vuln.sum()
    alloc_share = alloc / total_alloc

    # Adequacy: 1 – mean absolute deviation between shares (max possible = 1)
    adequacy = 1.0 - float(np.mean(np.abs(vuln_share - alloc_share)))

    return round(0.5 * evenness + 0.5 * adequacy, 4)


# ── Full audit ────────────────────────────────────────────────────────────────


def compute_fairness_report(
    zones: list[ZoneDemographics],
    allocations: list[ZoneAllocation],
    historical_records: list[HistoricalRecord],
) -> FairnessReport:
    """
    Compute a comprehensive fairness report over zones.

    Parameters
    ----------
    zones : zone demographic profiles.
    allocations : current resource allocations per zone.
    historical_records : past disaster allocation history.

    Returns
    -------
    FairnessReport with all metrics populated.
    """
    alloc_map = {a.zone_id: a.allocated_quantity for a in allocations}
    need_map = {a.zone_id: a.needed_quantity for a in allocations}
    alloc_list = [alloc_map.get(z.zone_id, 0.0) for z in zones]
    pop_list = [z.population for z in zones]

    gini = gini_per_capita(alloc_list, pop_list)
    vuln_map = vulnerability_scores(zones)
    underservice = historical_underservice_scores([z.zone_id for z in zones], historical_records)

    # Per-zone detail rows
    zone_details: list[dict[str, Any]] = []
    for z in zones:
        zid = z.zone_id
        detail: dict[str, Any] = {
            "zone_id": zid,
            "zone_name": z.zone_name,
            "population": z.population,
            "vulnerability_index": vuln_map.get(zid, 0.0),
            "underservice_score": underservice.get(zid, 0),
            "allocated": alloc_map.get(zid, 0.0),
            "needed": need_map.get(zid, 0.0),
            "fulfillment_pct": round(
                alloc_map.get(zid, 0.0) / max(need_map.get(zid, 1.0), 1.0) * 100,
                2,
            ),
            "is_rural": z.is_rural,
            "ngo_count_within_20km": z.ngo_count_within_20km,
        }
        zone_details.append(detail)

    # Distribution by vulnerability group
    low_vuln = [d for d in zone_details if d["vulnerability_index"] < 0.3]
    mid_vuln = [d for d in zone_details if 0.3 <= d["vulnerability_index"] < 0.7]
    high_vuln = [d for d in zone_details if d["vulnerability_index"] >= 0.7]

    def _group_summary(group: list[dict[str, Any]]) -> dict[str, Any]:
        if not group:
            return {
                "zone_count": 0,
                "total_allocated": 0,
                "total_needed": 0,
                "avg_fulfillment_pct": 0,
            }
        return {
            "zone_count": len(group),
            "total_allocated": sum(d["allocated"] for d in group),
            "total_needed": sum(d["needed"] for d in group),
            "avg_fulfillment_pct": round(sum(d["fulfillment_pct"] for d in group) / len(group), 2),
        }

    dist_by_vuln = {
        "low": _group_summary(low_vuln),
        "medium": _group_summary(mid_vuln),
        "high": _group_summary(high_vuln),
    }

    eq = equity_score(gini, vuln_map, alloc_map)

    return FairnessReport(
        gini_coefficient=round(gini, 4),
        vulnerability_scores=vuln_map,
        underservice_scores=underservice,
        zone_details=zone_details,
        distribution_by_vulnerability=dist_by_vuln,
        overall_equity_score=eq,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))
