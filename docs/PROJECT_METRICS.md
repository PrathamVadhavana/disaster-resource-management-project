# Project Metrics

Generated on 2026-10-24 from local, reproducible measurements. Raw results are
stored in [`reports/PROJECT_METRICS_2026-10-24.json`](../reports/PROJECT_METRICS_2026-10-24.json).

## Resume-safe measurements

| Area | Measured result | Scope |
|---|---:|---|
| NLP throughput | 4,840.74 classifications/second | 8 deterministic request cases, 8,000 total classifications |
| NLP latency | 0.2066 ms/classification | Local in-process benchmark; excludes network and database latency |
| NLP tests | 30/30 passed | `test_nlp_service.py` |
| NLP service coverage | 35% line coverage | 420 statements measured by `pytest-cov` |
| MILP allocation coverage | 100% | 4 needs and 8 resources in the benchmark scenario |
| MILP median solve time | 29.66 ms | 100 repeated local runs |
| MILP p95 solve time | 36.98 ms | 100 repeated local runs |
| Repository API scope | 57 documented endpoints | README API reference |
| Frontend scope | 52 page files | `frontend/src/app` |
| Backend routing scope | 27 router modules | `backend/app/routers` |
| Backend service scope | 39 service modules | `backend/app/services`, recursively |

## Reproduction commands

Run these from PowerShell:

```powershell
Set-Location E:\disaster-management-system\backend
$env:PYTHONPATH = "."
uv run pytest tests\unit\test_nlp_service.py `
  --cov=app.services.nlp_service --cov-report=term-missing
```

The NLP and allocation throughput benchmarks were run as deterministic
in-process scripts using
[`backend/scripts/project_metrics_benchmark.py`](../backend/scripts/project_metrics_benchmark.py).
Regenerate them with:

```powershell
Set-Location E:\disaster-management-system\backend
uv run python scripts\project_metrics_benchmark.py `
  --output reports\project_metrics_latest.json
```

The recorded raw output is in the dated JSON report.

## Validation findings

- The targeted NLP suite passed: **30 passed, 0 failed**.
- The full backend suite collected 33 tests and reported **30 passed and 3
  failed**. The three failures are in `test_dependencies.py`, whose tests
  patch `app.dependencies.db` even though that module does not expose a `db`
  attribute.
- The frontend production build compiled successfully but failed during
  TypeScript checking at
  `frontend/src/components/coordinator/MLDashboard.tsx:419`. The
  `triggerInference(typeOverride?, featuresOverride?)` function is passed
  directly as a button click handler and receives a mouse event.

These failures are recorded rather than hidden; the metrics should not be
presented as a fully green build until they are fixed.

## Interpretation

The allocation result is a **benchmark-scenario result**, not a production
impact claim. In the tested scenario, the MILP optimizer matched the greedy
nearest-resource baseline at 100% coverage and 6.12 km total estimated
delivery distance. The benchmark therefore supports the solver's correctness
and timing, but not a claim that it reduced distance or improved coverage.

The NLP throughput result is also not model accuracy. Accuracy, precision,
recall, and F1 require a labeled ground-truth test set. Production API
latency requires a deployed service, database, and defined concurrency
profile.
