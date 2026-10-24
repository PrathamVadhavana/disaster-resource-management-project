"""Run deterministic local benchmarks used by the project metrics report.

Usage:
    uv run python scripts/project_metrics_benchmark.py
    uv run python scripts/project_metrics_benchmark.py --output reports/project_metrics_latest.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.allocation_engine import AvailableResource, ResourceNeed, solve_allocation
from app.services.nlp_service import classify_request


def build_allocation_fixture() -> tuple[list[AvailableResource], list[ResourceNeed]]:
    resources = [
        AvailableResource("0", "Water", 100, 5, 19.07, 72.87, "warehouse-0"),
        AvailableResource("1", "Food", 80, 5, 19.10, 72.90, "warehouse-1"),
        AvailableResource("2", "Medical", 40, 5, 19.12, 72.85, "warehouse-2"),
        AvailableResource("3", "Shelter", 50, 5, 19.02, 72.91, "warehouse-3"),
        AvailableResource("4", "Water", 120, 5, 19.20, 73.00, "warehouse-4"),
        AvailableResource("5", "Food", 90, 5, 18.95, 72.80, "warehouse-5"),
        AvailableResource("6", "Medical", 60, 5, 19.00, 72.95, "warehouse-6"),
        AvailableResource("7", "Shelter", 75, 5, 19.15, 72.78, "warehouse-7"),
    ]
    needs = [
        ResourceNeed("Water", 50, 10, 19.08, 72.88, "zone-1"),
        ResourceNeed("Food", 60, 8, 19.09, 72.89, "zone-1"),
        ResourceNeed("Medical", 30, 10, 19.11, 72.86, "zone-2"),
        ResourceNeed("Shelter", 40, 7, 19.03, 72.90, "zone-3"),
    ]
    return resources, needs


def benchmark_nlp() -> dict[str, float | int]:
    cases = [
        "We need clean water and food for a family of 5",
        "Person trapped under collapsed building, unconscious, not breathing",
        "Need medicine and a doctor for severe bleeding",
        "Our house collapsed and we need tents and blankets",
        "Please send rescue helicopter, we are stranded",
        "There are 15 people with no water for 3 days",
        "We need food, water, and medical supplies urgently",
        "Pregnant woman needs evacuation and medical help",
    ]
    iterations = 1000
    for _ in range(10):
        for text in cases:
            classify_request(text, user_priority="medium")

    started = time.perf_counter()
    for _ in range(iterations):
        for text in cases:
            classify_request(text, user_priority="medium")
    elapsed = time.perf_counter() - started
    total = iterations * len(cases)
    return {
        "input_cases": len(cases),
        "iterations_per_case": iterations,
        "total_classifications": total,
        "elapsed_seconds": round(elapsed, 6),
        "classifications_per_second": round(total / elapsed, 2),
        "milliseconds_per_classification": round(elapsed / total * 1000, 4),
    }


def benchmark_allocation() -> dict[str, float | int | str]:
    resources, needs = build_allocation_fixture()
    for _ in range(3):
        solve_allocation(resources, needs)

    timings = []
    result = None
    for _ in range(100):
        started = time.perf_counter()
        result = solve_allocation(resources, needs)
        timings.append((time.perf_counter() - started) * 1000)

    assert result is not None
    return {
        "resources": len(resources),
        "needs": len(needs),
        "iterations": len(timings),
        "solver_status": result.solver_status,
        "coverage_percent": result.coverage_pct,
        "allocated_count": len(result.allocations),
        "unmet_count": len(result.unmet_needs),
        "estimated_delivery_km": result.estimated_delivery_km,
        "optimization_score": result.optimization_score,
        "median_solve_time_ms": round(statistics.median(timings), 4),
        "p95_solve_time_ms": round(sorted(timings)[94], 4),
        "min_solve_time_ms": round(min(timings), 4),
        "max_solve_time_ms": round(max(timings), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local project metrics benchmarks")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_type": "deterministic_local_benchmarks",
        "nlp": benchmark_nlp(),
        "allocation": benchmark_allocation(),
    }
    encoded = json.dumps(report, indent=2)
    print(encoded)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
