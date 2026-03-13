"""
Evaluation script: GAT allocator vs greedy / LP baseline.

Generates 100 synthetic disaster scenarios and compares:
  1. **GAT** — trained Graph Attention Network + Hungarian matching.
  2. **ILP** — PuLP-based Integer Linear Programme (existing baseline).
  3. **Greedy** — distance-first greedy heuristic (nearest-eligible NGO).

Metrics per scenario:
  - **Average response time** (minutes) — travel-time proxy.
  - **Coverage %** — fraction of victim requests assigned.
  - **Total distance** (km) — sum of all assignment distances.
  - **Resource-type match rate** — fraction of assignments with exact type match.

Usage
-----
    python -m ml.evaluate_gat [--scenarios 100] [--checkpoint ml/models/gat_allocator.pt]
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from app.services.distance import haversine
from ml.gat_model import (
    DEFAULT_CHECKPOINT,
    GATAllocator,
    hungarian_assignment,
    load_checkpoint,
)
from ml.graph_builder import (
    NgoNode,
    VictimNode,
    build_graph,
)
from ml.train_gat import generate_scenario, solve_optimal_assignment

logger = logging.getLogger(__name__)

# ── Metrics dataclass ────────────────────────────────────────────────────


@dataclass
class ScenarioMetrics:
    avg_response_time_min: float = 0.0  # mean travel-time in minutes
    coverage_pct: float = 0.0
    total_distance_km: float = 0.0
    type_match_rate: float = 0.0


@dataclass
class AggregateMetrics:
    method: str = ""
    n_scenarios: int = 0
    avg_response_time_min: float = 0.0
    std_response_time_min: float = 0.0
    avg_coverage_pct: float = 0.0
    std_coverage_pct: float = 0.0
    avg_total_distance_km: float = 0.0
    avg_type_match_rate: float = 0.0


# ── Evaluator helpers ────────────────────────────────────────────────────

_FALLBACK_SPEED_KMH = 40.0
_DETOUR_FACTOR = 1.3


def _travel_time_min(dist_km: float) -> float:
    return (dist_km * _DETOUR_FACTOR / _FALLBACK_SPEED_KMH) * 60.0


def _type_matches(victim_type: str, ngo_types: list[str]) -> bool:
    return victim_type.lower() in {t.lower() for t in ngo_types}


def _compute_metrics(
    assignments: list[tuple[int, int]],
    victims: list[VictimNode],
    ngos: list[NgoNode],
) -> ScenarioMetrics:
    if not assignments:
        return ScenarioMetrics()

    distances = []
    travel_times = []
    type_matches = 0

    for vi, ni in assignments:
        d = haversine(victims[vi].lat, victims[vi].lon, ngos[ni].lat, ngos[ni].lon)
        distances.append(d)
        travel_times.append(_travel_time_min(d))
        if _type_matches(victims[vi].resource_type, ngos[ni].available_resource_types):
            type_matches += 1

    return ScenarioMetrics(
        avg_response_time_min=round(statistics.mean(travel_times), 2) if travel_times else 0.0,
        coverage_pct=round(len(assignments) / len(victims) * 100, 2) if victims else 0.0,
        total_distance_km=round(sum(distances), 2),
        type_match_rate=round(type_matches / len(assignments), 4) if assignments else 0.0,
    )


def _aggregate(method: str, all_metrics: list[ScenarioMetrics]) -> AggregateMetrics:
    if not all_metrics:
        return AggregateMetrics(method=method)
    return AggregateMetrics(
        method=method,
        n_scenarios=len(all_metrics),
        avg_response_time_min=round(statistics.mean(m.avg_response_time_min for m in all_metrics), 2),
        std_response_time_min=round(statistics.stdev(m.avg_response_time_min for m in all_metrics), 2)
        if len(all_metrics) > 1
        else 0.0,
        avg_coverage_pct=round(statistics.mean(m.coverage_pct for m in all_metrics), 2),
        std_coverage_pct=round(statistics.stdev(m.coverage_pct for m in all_metrics), 2)
        if len(all_metrics) > 1
        else 0.0,
        avg_total_distance_km=round(statistics.mean(m.total_distance_km for m in all_metrics), 2),
        avg_type_match_rate=round(statistics.mean(m.type_match_rate for m in all_metrics), 4),
    )


# ── Allocation strategies ───────────────────────────────────────────────


def _greedy_assignment(
    victims: list[VictimNode],
    ngos: list[NgoNode],
    radius_km: float = 50.0,
) -> list[tuple[int, int]]:
    """
    Greedy nearest-eligible-first assignment.

    For each victim (sorted by priority descending), assign the nearest
    unassigned NGO that has a matching resource type and is within radius.
    """
    assigned_ngos: set = set()
    assignments: list[tuple[int, int]] = []

    # Sort victims by priority (highest first)
    order = sorted(range(len(victims)), key=lambda i: victims[i].priority_score, reverse=True)

    for vi in order:
        v = victims[vi]
        best_ni = None
        best_dist = float("inf")
        for ni, n in enumerate(ngos):
            if ni in assigned_ngos:
                continue
            d = haversine(v.lat, v.lon, n.lat, n.lon)
            if d > radius_km:
                continue
            if not _type_matches(v.resource_type, n.available_resource_types):
                continue
            if d < best_dist:
                best_dist = d
                best_ni = ni
        # Fallback: if no type match, try nearest unassigned within radius
        if best_ni is None:
            for ni, n in enumerate(ngos):
                if ni in assigned_ngos:
                    continue
                d = haversine(v.lat, v.lon, n.lat, n.lon)
                if d > radius_km:
                    continue
                if d < best_dist:
                    best_dist = d
                    best_ni = ni
        if best_ni is not None:
            assignments.append((vi, best_ni))
            assigned_ngos.add(best_ni)

    return assignments


def _gat_assignment(
    model: GATAllocator,
    victims: list[VictimNode],
    ngos: list[NgoNode],
    radius_km: float = 50.0,
) -> list[tuple[int, int]]:
    """Run the GAT model + Hungarian matching."""
    graph = build_graph(victims, ngos, radius_km=radius_km)
    if graph["victim", "requests", "ngo"].edge_index.size(1) == 0:
        return []
    probs = model.predict_probs(graph)
    raw = hungarian_assignment(graph, probs)
    return [(vi, ni) for vi, ni, _ in raw]


# ── Main evaluation ─────────────────────────────────────────────────────


def evaluate(
    n_scenarios: int = 100,
    radius_km: float = 50.0,
    checkpoint_path: str | None = None,
    seed: int = 123,
) -> dict[str, AggregateMetrics]:
    """
    Run the three-way comparison on ``n_scenarios`` synthetic scenarios.

    Returns a dict keyed by method name → AggregateMetrics.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    # Load GAT model
    ckpt = Path(checkpoint_path or DEFAULT_CHECKPOINT)
    gat: GATAllocator | None = None
    if ckpt.exists():
        gat = load_checkpoint(ckpt)
        logger.info("Loaded GAT from %s", ckpt)
    else:
        logger.warning("GAT checkpoint not found at %s — skipping GAT evaluation", ckpt)

    gat_metrics: list[ScenarioMetrics] = []
    ilp_metrics: list[ScenarioMetrics] = []
    greedy_metrics: list[ScenarioMetrics] = []

    for i in range(n_scenarios):
        victims, ngos = generate_scenario()

        # ── ILP (ground-truth optimal) ───────────────────────────────
        ilp_assign = solve_optimal_assignment(victims, ngos, radius_km=radius_km)
        ilp_metrics.append(_compute_metrics(ilp_assign, victims, ngos))

        # ── Greedy ───────────────────────────────────────────────────
        greedy_assign = _greedy_assignment(victims, ngos, radius_km=radius_km)
        greedy_metrics.append(_compute_metrics(greedy_assign, victims, ngos))

        # ── GAT ──────────────────────────────────────────────────────
        if gat is not None:
            gat_assign = _gat_assignment(gat, victims, ngos, radius_km=radius_km)
            gat_metrics.append(_compute_metrics(gat_assign, victims, ngos))

        if (i + 1) % 20 == 0:
            logger.info("Evaluated %d / %d scenarios", i + 1, n_scenarios)

    results: dict[str, AggregateMetrics] = {
        "ILP (optimal)": _aggregate("ILP (optimal)", ilp_metrics),
        "Greedy": _aggregate("Greedy", greedy_metrics),
    }
    if gat_metrics:
        results["GAT"] = _aggregate("GAT", gat_metrics)

    return results


def print_results(results: dict[str, AggregateMetrics]) -> None:
    """Pretty-print the comparison table."""
    header = f"{'Method':<18} {'Avg RT (min)':>14} {'Coverage %':>12} {'Avg Dist (km)':>15} {'Type Match':>12}"
    sep = "─" * len(header)
    print()
    print(sep)
    print(header)
    print(sep)
    for name, m in results.items():
        print(
            f"{name:<18} "
            f"{m.avg_response_time_min:>10.2f} ± {m.std_response_time_min:<4.1f}"
            f"{m.avg_coverage_pct:>9.1f}%  "
            f"{m.avg_total_distance_km:>13.1f} "
            f"{m.avg_type_match_rate:>11.1%}"
        )
    print(sep)
    print()


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )
    parser = argparse.ArgumentParser(description="Evaluate GAT vs Greedy vs ILP")
    parser.add_argument("--scenarios", type=int, default=100)
    parser.add_argument("--radius", type=float, default=50.0)
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--output-json", type=str, default=None, help="Save results as JSON")
    args = parser.parse_args()

    results = evaluate(
        n_scenarios=args.scenarios,
        radius_km=args.radius,
        checkpoint_path=args.checkpoint,
        seed=args.seed,
    )

    print_results(results)

    if args.output_json:
        out = {}
        for name, m in results.items():
            out[name] = {
                "n_scenarios": m.n_scenarios,
                "avg_response_time_min": m.avg_response_time_min,
                "std_response_time_min": m.std_response_time_min,
                "avg_coverage_pct": m.avg_coverage_pct,
                "std_coverage_pct": m.std_coverage_pct,
                "avg_total_distance_km": m.avg_total_distance_km,
                "avg_type_match_rate": m.avg_type_match_rate,
            }
        Path(args.output_json).write_text(json.dumps(out, indent=2))
        logger.info("Results saved → %s", args.output_json)


if __name__ == "__main__":
    main()
