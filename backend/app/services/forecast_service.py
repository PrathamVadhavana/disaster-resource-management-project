"""
Surplus / shortfall forecasting service.

Uses simple time-series analysis (sklearn linear trending + optional Prophet)
on historical resource consumption to predict shortfalls for the next 72 hours.

If Prophet is available it will be preferred for its holiday/seasonality
handling; otherwise a lightweight linear-regression fallback is used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)

# Try importing Prophet — optional heavy dependency
try:
    from prophet import Prophet  # type: ignore

    _HAS_PROPHET = True
except ImportError:
    _HAS_PROPHET = False
    logger.info("Prophet not installed — using sklearn linear regression fallback for forecasting.")


# ── Data classes ──────────────────────────────────────────────────────────


@dataclass
class ConsumptionRecord:
    """One point of resource consumption history."""

    resource_type: str
    timestamp: datetime
    quantity_consumed: float
    quantity_available: float


@dataclass
class ForecastItem:
    """Predicted shortfall for one resource type in one time bucket."""

    resource_type: str
    forecast_hour: int  # hours from now (e.g. 24, 48, 72)
    predicted_demand: float
    predicted_supply: float
    shortfall: float  # negative means surplus
    confidence_lower: float = 0.0
    confidence_upper: float = 0.0


@dataclass
class ForecastResult:
    """Aggregated forecast across all resource types."""

    generated_at: datetime = field(default_factory=datetime.utcnow)
    horizon_hours: int = 72
    items: list[ForecastItem] = field(default_factory=list)
    method: str = "linear"  # or "prophet"


@dataclass
class ForecastBacktestItem:
    """Per-resource backtest metrics."""

    resource_type: str
    samples: int
    mae_shortfall: float
    rmse_shortfall: float
    mape_shortfall: float
    directional_accuracy: float


@dataclass
class ForecastBacktestResult:
    """Aggregate backtest results across resource types."""

    generated_at: datetime = field(default_factory=datetime.utcnow)
    lookback_points: int = 0
    method: str = "linear"
    items: list[ForecastBacktestItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ── Forecasting functions ─────────────────────────────────────────────────


def _forecast_linear(
    df: pd.DataFrame,
    resource_type: str,
    horizon_hours: int = 72,
    step_hours: int = 24,
) -> list[ForecastItem]:
    """Simple linear regression on consumption rate."""
    if df.empty or len(df) < 2:
        return [
            ForecastItem(
                resource_type=resource_type,
                forecast_hour=h,
                predicted_demand=0,
                predicted_supply=0,
                shortfall=0,
            )
            for h in range(step_hours, horizon_hours + 1, step_hours)
        ]

    df = df.sort_values("timestamp").copy()
    df["hours"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds() / 3600

    # Fit demand trend
    X = df[["hours"]].values
    y_demand = df["quantity_consumed"].values
    y_supply = df["quantity_available"].values

    model_demand = LinearRegression().fit(X, y_demand)
    model_supply = LinearRegression().fit(X, y_supply)

    last_hour = df["hours"].max()
    items: list[ForecastItem] = []
    for h in range(step_hours, horizon_hours + 1, step_hours):
        future_hour = last_hour + h
        pred_demand = max(float(model_demand.predict([[future_hour]])[0]), 0)
        pred_supply = max(float(model_supply.predict([[future_hour]])[0]), 0)
        shortfall = pred_demand - pred_supply

        # Rough confidence band: ±20 % of predicted demand
        band = pred_demand * 0.2
        items.append(
            ForecastItem(
                resource_type=resource_type,
                forecast_hour=h,
                predicted_demand=round(pred_demand, 2),
                predicted_supply=round(pred_supply, 2),
                shortfall=round(shortfall, 2),
                confidence_lower=round(shortfall - band, 2),
                confidence_upper=round(shortfall + band, 2),
            )
        )
    return items


def _forecast_prophet(
    df: pd.DataFrame,
    resource_type: str,
    horizon_hours: int = 72,
    step_hours: int = 24,
) -> list[ForecastItem]:
    """Prophet-based forecasting (preferred when available)."""
    if not _HAS_PROPHET or df.empty or len(df) < 2:
        return _forecast_linear(df, resource_type, horizon_hours, step_hours)

    df = df.sort_values("timestamp").copy()
    demand_df = df.rename(columns={"timestamp": "ds", "quantity_consumed": "y"})[["ds", "y"]]

    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=False,
        yearly_seasonality=False,
        changepoint_prior_scale=0.05,
    )
    model.fit(demand_df)

    future = model.make_future_dataframe(periods=horizon_hours, freq="h")
    forecast = model.predict(future)

    # Supply: simple linear for now
    supply_df = df.rename(columns={"timestamp": "ds", "quantity_available": "y"})[["ds", "y"]]
    supply_model = LinearRegression()
    supply_df["hours"] = (supply_df["ds"] - supply_df["ds"].min()).dt.total_seconds() / 3600
    supply_model.fit(supply_df[["hours"]].values, supply_df["y"].values)
    last_hour = supply_df["hours"].max()

    items: list[ForecastItem] = []
    for h in range(step_hours, horizon_hours + 1, step_hours):
        row = forecast.iloc[-horizon_hours + h - 1] if len(forecast) > horizon_hours else forecast.iloc[-1]
        pred_demand = max(float(row["yhat"]), 0)
        pred_supply = max(float(supply_model.predict([[last_hour + h]])[0]), 0)
        shortfall = pred_demand - pred_supply

        items.append(
            ForecastItem(
                resource_type=resource_type,
                forecast_hour=h,
                predicted_demand=round(pred_demand, 2),
                predicted_supply=round(pred_supply, 2),
                shortfall=round(shortfall, 2),
                confidence_lower=round(float(row.get("yhat_lower", shortfall * 0.8)), 2),
                confidence_upper=round(float(row.get("yhat_upper", shortfall * 1.2)), 2),
            )
        )
    return items


# ── Public API ────────────────────────────────────────────────────────────


def generate_forecast(
    records: list[ConsumptionRecord],
    horizon_hours: int = 72,
    step_hours: int = 24,
) -> ForecastResult:
    """
    Produce a shortfall forecast for each resource type present in *records*.

    Parameters
    ----------
    records        : historical consumption / availability rows.
    horizon_hours  : how far ahead to forecast (default 72 h).
    step_hours     : bucket size (default 24 h → gives 24 h, 48 h, 72 h).

    Returns
    -------
    ForecastResult with per-type shortfall predictions.
    """
    if not records:
        return ForecastResult(horizon_hours=horizon_hours, method="none")

    df = pd.DataFrame(
        [
            {
                "resource_type": r.resource_type,
                "timestamp": r.timestamp,
                "quantity_consumed": r.quantity_consumed,
                "quantity_available": r.quantity_available,
            }
            for r in records
        ]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    method = "prophet" if _HAS_PROPHET else "linear"
    forecast_fn = _forecast_prophet if _HAS_PROPHET else _forecast_linear

    all_items: list[ForecastItem] = []
    for rtype, group in df.groupby("resource_type"):
        all_items.extend(forecast_fn(group, str(rtype), horizon_hours, step_hours))

    return ForecastResult(
        horizon_hours=horizon_hours,
        items=all_items,
        method=method,
    )


def backtest_forecast(
    records: list[ConsumptionRecord],
    horizon_hours: int = 24,
    min_train_points: int = 12,
) -> ForecastBacktestResult:
    """
    Backtest forecast quality with rolling-origin one-step evaluation.

    For each resource type, iteratively train on historical prefix and predict
    the next observed point's shortfall. Metrics are computed on shortfall
    error (predicted_demand - predicted_supply).
    """
    if not records:
        return ForecastBacktestResult(method="none", notes=["No records available for backtesting"])

    df = pd.DataFrame(
        [
            {
                "resource_type": r.resource_type,
                "timestamp": r.timestamp,
                "quantity_consumed": r.quantity_consumed,
                "quantity_available": r.quantity_available,
            }
            for r in records
        ]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    method = "prophet" if _HAS_PROPHET else "linear"

    result_items: list[ForecastBacktestItem] = []
    notes: list[str] = []
    lookback_points = len(df)

    for rtype, group in df.groupby("resource_type"):
        g = group.sort_values("timestamp").reset_index(drop=True)
        n = len(g)
        if n < (min_train_points + 3):
            notes.append(f"Skipped {rtype}: insufficient points ({n})")
            continue

        abs_errors: list[float] = []
        sq_errors: list[float] = []
        ape_values: list[float] = []
        direction_matches = 0
        total = 0

        for i in range(min_train_points, n):
            train_rows = g.iloc[:i]
            current_row = g.iloc[i]

            train_records = [
                ConsumptionRecord(
                    resource_type=str(r["resource_type"]),
                    timestamp=pd.Timestamp(r["timestamp"]).to_pydatetime(),
                    quantity_consumed=float(r["quantity_consumed"]),
                    quantity_available=float(r["quantity_available"]),
                )
                for _, r in train_rows.iterrows()
            ]
            fc = generate_forecast(train_records, horizon_hours=horizon_hours, step_hours=horizon_hours)
            step_predictions = [
                it for it in fc.items if it.resource_type == str(rtype) and it.forecast_hour == horizon_hours
            ]
            if not step_predictions:
                continue

            pred_shortfall = float(step_predictions[0].shortfall)
            actual_shortfall = float(current_row["quantity_consumed"]) - float(current_row["quantity_available"])
            err = pred_shortfall - actual_shortfall

            abs_errors.append(abs(err))
            sq_errors.append(err * err)
            if abs(actual_shortfall) > 1e-6:
                ape_values.append(abs(err) / abs(actual_shortfall))

            if (pred_shortfall >= 0 and actual_shortfall >= 0) or (pred_shortfall < 0 and actual_shortfall < 0):
                direction_matches += 1
            total += 1

        if total == 0:
            notes.append(f"Skipped {rtype}: no evaluable rolling windows")
            continue

        result_items.append(
            ForecastBacktestItem(
                resource_type=str(rtype),
                samples=total,
                mae_shortfall=round(sum(abs_errors) / total, 3),
                rmse_shortfall=round(float((sum(sq_errors) / total) ** 0.5), 3),
                mape_shortfall=round((sum(ape_values) / len(ape_values)) * 100, 2) if ape_values else 0.0,
                directional_accuracy=round((direction_matches / total) * 100, 2),
            )
        )

    if not result_items and not notes:
        notes.append("No resource types had enough data for backtest")

    return ForecastBacktestResult(
        lookback_points=lookback_points,
        method=method,
        items=result_items,
        notes=notes,
    )
