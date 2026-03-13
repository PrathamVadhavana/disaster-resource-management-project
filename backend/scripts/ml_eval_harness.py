"""
Unified ML evaluation harness for production models.

What it does:
- Generates evaluation reports for severity/spread/impact from outcome_tracking
- Computes confidence-band calibration summaries from predictions + outcomes
- Writes JSON report to backend/reports/ml_eval_<timestamp>.json

Usage:
    cd backend
    uv run python scripts/ml_eval_harness.py --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.ml_eval_service import run_ml_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run unified ML evaluation harness")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    args = parser.parse_args()

    report = asyncio.run(run_ml_evaluation(days=max(1, args.days)))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
