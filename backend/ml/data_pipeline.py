"""
ml/data_pipeline.py – Data pipeline for Temporal Fusion Transformer severity forecasting.

1. Parse EM-DAT public CSV disaster catalogue
2. Fetch 72h pre-event weather from Open-Meteo (free, no API key)
3. Build a time-series dataset suitable for pytorch-forecasting
4. Cyclical encoding for temporal features (hour, day-of-week, month)
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "training_data"
PROCESSED_DIR = DATA_DIR / "tft_processed"

# Weather variables we pull from Open-Meteo
WEATHER_VARS = [
    "temperature_2m",
    "wind_speed_10m",
    "precipitation",
    "relative_humidity_2m",
]

# Horizons (hours ahead) we want to predict
FORECAST_HORIZONS = [6, 12, 24, 48]

# Total hours per event series (must be > encoder + decoder = 48 + 48)
# We use 144h (6 days) to give pytorch-forecasting enough room.
LOOKBACK_HOURS = 144

# Severity mapping for numeric labels
SEVERITY_MAP = {"low": 0, "medium": 1, "high": 2, "critical": 3}
SEVERITY_INV = {v: k for k, v in SEVERITY_MAP.items()}


# ─── EM-DAT CSV Parsing ─────────────────────────────────────────────────────


def parse_emdat_csv(csv_path: str | Path) -> pd.DataFrame:
    """Parse the EM-DAT public disaster dataset CSV into a clean DataFrame.

    EM-DAT columns used (names may vary across exports):
        Dis No, Disaster Type, Disaster Subtype, Country, ISO,
        Start Year, Start Month, Start Day, End Year, End Month, End Day,
        Latitude, Longitude, Total Deaths, Total Affected,
        Total Damage ('000 US$), Magnitude, Magnitude Scale

    Returns a DataFrame with standardised columns:
        event_id, disaster_type, country, iso, start_date, end_date,
        latitude, longitude, total_deaths, total_affected,
        total_damage_kusd, magnitude, severity_label, severity_numeric
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"EM-DAT CSV not found at {csv_path}")

    df = pd.read_csv(csv_path, encoding="latin-1", low_memory=False)

    # Normalise column names: strip whitespace, lowercase, replace spaces
    df.columns = [c.strip().lower().replace(" ", "_").replace("'", "") for c in df.columns]

    rename_map = {
        "dis_no": "event_id",
        "disaster_type": "disaster_type",
        "disaster_subtype": "disaster_subtype",
        "country": "country",
        "iso": "iso",
        "start_year": "start_year",
        "start_month": "start_month",
        "start_day": "start_day",
        "end_year": "end_year",
        "end_month": "end_month",
        "end_day": "end_day",
        "latitude": "latitude",
        "longitude": "longitude",
        "total_deaths": "total_deaths",
        "total_affected": "total_affected",
        "total_damage_(000_us$)": "total_damage_kusd",
        "total_damage,_adjusted_(000_us$)": "total_damage_kusd",
        "total_damages_(000_us$)": "total_damage_kusd",
        "total_damages,_adjusted_(000_us$)": "total_damage_kusd",
        "magnitude": "magnitude",
        "magnitude_scale": "magnitude_scale",
    }

    # Keep only columns that exist in the rename map
    existing_cols = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=existing_cols)

    # Build start_date from year/month/day columns
    for col in ("start_year", "start_month", "start_day"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "start_year" in df.columns:
        df["start_month"] = df.get("start_month", pd.Series(1, index=df.index)).fillna(1).astype(int)
        df["start_day"] = df.get("start_day", pd.Series(1, index=df.index)).fillna(1).astype(int)
        df["start_date"] = pd.to_datetime(
            df[["start_year", "start_month", "start_day"]].rename(
                columns={"start_year": "year", "start_month": "month", "start_day": "day"}
            ),
            errors="coerce",
        )
    else:
        df["start_date"] = pd.NaT

    # Filter out rows without valid dates or coordinates
    df = df.dropna(subset=["start_date"])
    for coord in ("latitude", "longitude"):
        if coord in df.columns:
            df[coord] = pd.to_numeric(df.get(coord, 0), errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])

    # Numeric cleanup
    for num_col in ("total_deaths", "total_affected", "total_damage_kusd", "magnitude"):
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)

    # Derive severity label from deaths + affected population
    df["severity_numeric"] = df.apply(_compute_severity_score, axis=1)
    df["severity_label"] = df["severity_numeric"].map(SEVERITY_INV)

    # Keep only events from 2000+ (better weather data coverage)
    if "start_year" in df.columns:
        df = df[df["start_year"] >= 2000]

    logger.info("Parsed %d EM-DAT events with coordinates", len(df))
    return df.reset_index(drop=True)


def _compute_severity_score(row: pd.Series) -> int:
    """Heuristic severity from deaths and affected population."""
    deaths = row.get("total_deaths", 0) or 0
    affected = row.get("total_affected", 0) or 0

    if deaths >= 1000 or affected >= 1_000_000:
        return 3  # critical
    if deaths >= 100 or affected >= 100_000:
        return 2  # high
    if deaths >= 10 or affected >= 10_000:
        return 1  # medium
    return 0  # low


# ─── Open-Meteo Weather Fetcher ─────────────────────────────────────────────


async def fetch_weather_openmeteo(
    latitude: float,
    longitude: float,
    start_date: datetime,
    hours: int = LOOKBACK_HOURS,
    retries: int = 3,
) -> pd.DataFrame | None:
    """Fetch hourly weather from the Open-Meteo Historical Weather API.

    Returns a DataFrame with columns: datetime, temperature_2m,
    wind_speed_10m, precipitation, relative_humidity_2m
    or None on failure.
    """
    end_dt = start_date
    start_dt = start_date - timedelta(hours=hours)

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": round(latitude, 4),
        "longitude": round(longitude, 4),
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "hourly": ",".join(WEATHER_VARS),
        "timezone": "UTC",
    }

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            if not times:
                logger.warning("No hourly data returned for (%.2f, %.2f)", latitude, longitude)
                return None

            weather_df = pd.DataFrame(
                {
                    "datetime": pd.to_datetime(times),
                    "temperature_2m": hourly.get("temperature_2m", [None] * len(times)),
                    "wind_speed_10m": hourly.get("wind_speed_10m", [None] * len(times)),
                    "precipitation": hourly.get("precipitation", [None] * len(times)),
                    "relative_humidity_2m": hourly.get("relative_humidity_2m", [None] * len(times)),
                }
            )

            # Trim to exactly the lookback window
            weather_df = weather_df.tail(hours).reset_index(drop=True)

            # Forward-fill any gaps
            weather_df = weather_df.ffill().bfill()
            return weather_df

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2**attempt
                logger.warning("Rate limited by Open-Meteo, retrying in %ds…", wait)
                await asyncio.sleep(wait)
            else:
                logger.error("Open-Meteo HTTP error: %s", e)
                return None
        except Exception as e:
            logger.error("Open-Meteo fetch failed (attempt %d): %s", attempt + 1, e)
            if attempt < retries - 1:
                await asyncio.sleep(1)

    return None


# ─── Cyclical Feature Encoding ──────────────────────────────────────────────


def add_cyclical_time_features(df: pd.DataFrame, dt_col: str = "datetime") -> pd.DataFrame:
    """Add sin/cos encodings for hour-of-day, day-of-week, month-of-year."""
    df = df.copy()
    dt = pd.to_datetime(df[dt_col])

    # Hour of day (0–23)
    hour = dt.dt.hour
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)

    # Day of week (0=Monday … 6=Sunday)
    dow = dt.dt.dayofweek
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)

    # Month of year (1–12)
    month = dt.dt.month
    df["month_sin"] = np.sin(2 * np.pi * month / 12)
    df["month_cos"] = np.cos(2 * np.pi * month / 12)

    return df


# ─── Full Dataset Builder ───────────────────────────────────────────────────


async def build_tft_dataset(
    emdat_csv: str | Path | None = None,
    max_events: int = 500,
    output_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Build the complete time-series dataset for TFT training.

    For each EM-DAT event:
      1. Fetch 144h pre-event weather from Open-Meteo
      2. Add cyclical time encodings
      3. Append severity labels (replicated for each timestep)
      4. Assign time_idx (0..143) and group_id (event index)

    Saves the result to output_dir / tft_dataset.parquet.
    Returns the assembled DataFrame.
    """
    output_dir = Path(output_dir or PROCESSED_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    if emdat_csv is not None:
        events_df = parse_emdat_csv(emdat_csv)
    else:
        events_df = _generate_synthetic_events(max_events)

    # Limit event count
    if len(events_df) > max_events:
        events_df = events_df.sample(n=max_events, random_state=42).reset_index(drop=True)

    all_rows: list[pd.DataFrame] = []
    logger.info("Fetching weather for %d events…", len(events_df))

    for idx, event in events_df.iterrows():
        weather = await fetch_weather_openmeteo(
            latitude=event["latitude"],
            longitude=event["longitude"],
            start_date=event["start_date"],
        )

        if weather is None or len(weather) < 12:
            logger.debug("Skipping event %s – insufficient weather data", event.get("event_id", idx))
            continue

        # Add cyclical time features
        weather = add_cyclical_time_features(weather)

        # Event metadata (static covariates)
        weather["group_id"] = int(idx)
        weather["time_idx"] = range(len(weather))
        weather["severity_numeric"] = event["severity_numeric"]
        weather["severity_label"] = event["severity_label"]
        weather["disaster_type"] = event.get("disaster_type", "other")
        weather["latitude"] = event["latitude"]
        weather["longitude"] = event["longitude"]

        all_rows.append(weather)

        # Rate-limit to avoid hammering Open-Meteo
        if idx > 0 and idx % 20 == 0:
            logger.info("  processed %d / %d events", idx, len(events_df))
            await asyncio.sleep(1.0)

    if not all_rows:
        logger.warning("No valid events with weather data. Generating synthetic dataset.")
        return _generate_synthetic_dataset(output_dir)

    dataset = pd.concat(all_rows, ignore_index=True)

    # Ensure numeric types
    for col in WEATHER_VARS:
        dataset[col] = pd.to_numeric(dataset[col], errors="coerce").fillna(0)

    out_path = output_dir / "tft_dataset.parquet"
    dataset.to_parquet(out_path, index=False)
    logger.info("TFT dataset saved: %s  (%d rows, %d events)", out_path, len(dataset), dataset["group_id"].nunique())

    return dataset


# ─── Synthetic Fallback (for training without EM-DAT download) ──────────────


def _generate_synthetic_events(n_events: int = 200) -> pd.DataFrame:
    """Generate synthetic disaster events for pipeline testing."""
    rng = np.random.RandomState(42)

    types = ["earthquake", "flood", "hurricane", "tornado", "wildfire", "tsunami", "drought", "landslide", "volcano"]

    rows = []
    for i in range(n_events):
        lat = rng.uniform(-60, 70)
        lon = rng.uniform(-180, 180)
        year = rng.randint(2005, 2024)
        month = rng.randint(1, 13)
        day = rng.randint(1, 29)
        try:
            start = datetime(year, month, day, tzinfo=UTC)
        except ValueError:
            start = datetime(year, month, 1, tzinfo=UTC)

        deaths = int(rng.exponential(50))
        affected = int(rng.exponential(50_000))
        sev = _compute_severity_score(pd.Series({"total_deaths": deaths, "total_affected": affected}))

        rows.append(
            {
                "event_id": f"SYNTH-{i:04d}",
                "disaster_type": rng.choice(types),
                "country": "Synthetic",
                "iso": "SYN",
                "start_date": start,
                "latitude": lat,
                "longitude": lon,
                "total_deaths": deaths,
                "total_affected": affected,
                "total_damage_kusd": rng.exponential(10_000),
                "magnitude": rng.uniform(1, 9),
                "severity_numeric": sev,
                "severity_label": SEVERITY_INV[sev],
            }
        )

    return pd.DataFrame(rows)


def _generate_synthetic_dataset(output_dir: Path, n_events: int = 200) -> pd.DataFrame:
    """Generate a fully synthetic TFT dataset (no API calls)."""
    rng = np.random.RandomState(42)

    types = ["earthquake", "flood", "hurricane", "tornado", "wildfire"]
    all_rows = []

    for group_id in range(n_events):
        severity = rng.randint(0, 4)
        disaster_type = rng.choice(types)
        lat = rng.uniform(-60, 70)
        lon = rng.uniform(-180, 180)

        # Base weather profile depends on severity
        base_temp = 15 + severity * 5 + rng.normal(0, 3)
        base_wind = 5 + severity * 8 + rng.normal(0, 2)
        base_precip = severity * 3 + rng.exponential(2)
        base_humidity = 40 + severity * 10 + rng.normal(0, 5)

        start_dt = datetime(2020, 1, 1, tzinfo=UTC) + timedelta(hours=rng.randint(0, 365 * 24))

        for t in range(LOOKBACK_HOURS):
            dt = start_dt + timedelta(hours=t)
            # Weather evolves with some trend toward severity
            progress = t / LOOKBACK_HOURS
            temp = base_temp + progress * severity * 2 + rng.normal(0, 1.5)
            wind = max(0, base_wind + progress * severity * 3 + rng.normal(0, 2))
            precip = max(0, base_precip * (1 + progress) + rng.exponential(0.5))
            humidity = np.clip(base_humidity + rng.normal(0, 3), 0, 100)

            hour = dt.hour
            dow = dt.weekday()
            month = dt.month

            all_rows.append(
                {
                    "datetime": dt,
                    "temperature_2m": round(temp, 1),
                    "wind_speed_10m": round(wind, 1),
                    "precipitation": round(precip, 2),
                    "relative_humidity_2m": round(humidity, 1),
                    "hour_sin": round(math.sin(2 * math.pi * hour / 24), 4),
                    "hour_cos": round(math.cos(2 * math.pi * hour / 24), 4),
                    "dow_sin": round(math.sin(2 * math.pi * dow / 7), 4),
                    "dow_cos": round(math.cos(2 * math.pi * dow / 7), 4),
                    "month_sin": round(math.sin(2 * math.pi * month / 12), 4),
                    "month_cos": round(math.cos(2 * math.pi * month / 12), 4),
                    "group_id": group_id,
                    "time_idx": t,
                    "severity_numeric": severity,
                    "severity_label": SEVERITY_INV[severity],
                    "disaster_type": disaster_type,
                    "latitude": round(lat, 4),
                    "longitude": round(lon, 4),
                }
            )

    dataset = pd.DataFrame(all_rows)
    out_path = output_dir / "tft_dataset.parquet"
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(out_path, index=False)
    logger.info("Synthetic TFT dataset saved: %s  (%d rows, %d events)", out_path, len(dataset), n_events)
    return dataset
