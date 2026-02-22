"""
Generate realistic synthetic training data modeled after EM-DAT, NOAA, and FEMA datasets.

Run this script to create CSV files in backend/training_data/ that mimic the
statistical distributions found in real disaster datasets. If you have actual
EM-DAT / NOAA / FEMA CSVs, place them in training_data/ and the training
pipeline will prefer them over synthetic data.

Usage:
    python -m scripts.generate_training_data
"""

import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

SEED = 42
np.random.seed(SEED)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "training_data"
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 1. EM-DAT-style disaster events  (severity labels)
# ---------------------------------------------------------------------------

DISASTER_TYPES = [
    "earthquake", "flood", "hurricane", "tornado",
    "wildfire", "tsunami", "drought", "landslide", "volcano",
]

SEVERITY_MAP = {"low": 0, "medium": 1, "high": 2, "critical": 3}

COUNTRY_GDP_PER_CAPITA = {
    "USA": 63000, "India": 2100, "Japan": 40000, "Philippines": 3500,
    "Brazil": 8700, "Indonesia": 4300, "China": 12500, "Mexico": 10000,
    "Bangladesh": 2500, "Haiti": 1400, "Nepal": 1200, "Australia": 55000,
    "Chile": 15000, "Turkey": 9600, "Pakistan": 1500, "Nigeria": 2100,
}

COUNTRIES = list(COUNTRY_GDP_PER_CAPITA.keys())


def _weather_for_disaster(dtype: str, n: int) -> dict:
    """Return weather feature arrays with realistic correlations."""
    if dtype == "hurricane":
        temp = np.random.normal(29, 3, n)
        wind = np.random.normal(130, 40, n).clip(60, 280)
        humidity = np.random.normal(85, 8, n).clip(40, 100)
        pressure = np.random.normal(960, 20, n).clip(880, 1020)
    elif dtype == "tornado":
        temp = np.random.normal(26, 5, n)
        wind = np.random.normal(100, 50, n).clip(30, 300)
        humidity = np.random.normal(70, 12, n).clip(30, 100)
        pressure = np.random.normal(980, 15, n).clip(920, 1020)
    elif dtype == "flood":
        temp = np.random.normal(22, 6, n)
        wind = np.random.normal(25, 15, n).clip(0, 80)
        humidity = np.random.normal(90, 5, n).clip(60, 100)
        pressure = np.random.normal(1000, 10, n).clip(960, 1030)
    elif dtype == "wildfire":
        temp = np.random.normal(38, 5, n)
        wind = np.random.normal(35, 15, n).clip(5, 100)
        humidity = np.random.normal(20, 10, n).clip(5, 50)
        pressure = np.random.normal(1015, 8, n).clip(990, 1040)
    elif dtype == "earthquake":
        temp = np.random.normal(20, 10, n)
        wind = np.random.normal(15, 10, n).clip(0, 50)
        humidity = np.random.normal(55, 20, n).clip(10, 100)
        pressure = np.random.normal(1013, 8, n).clip(980, 1040)
    elif dtype == "tsunami":
        temp = np.random.normal(25, 6, n)
        wind = np.random.normal(20, 12, n).clip(0, 60)
        humidity = np.random.normal(75, 10, n).clip(40, 100)
        pressure = np.random.normal(1010, 10, n).clip(970, 1040)
    elif dtype == "drought":
        temp = np.random.normal(40, 5, n)
        wind = np.random.normal(12, 8, n).clip(0, 40)
        humidity = np.random.normal(15, 8, n).clip(2, 40)
        pressure = np.random.normal(1020, 6, n).clip(1000, 1040)
    elif dtype == "landslide":
        temp = np.random.normal(18, 6, n)
        wind = np.random.normal(20, 10, n).clip(0, 60)
        humidity = np.random.normal(80, 10, n).clip(50, 100)
        pressure = np.random.normal(1005, 10, n).clip(970, 1030)
    elif dtype == "volcano":
        temp = np.random.normal(22, 8, n)
        wind = np.random.normal(18, 12, n).clip(0, 60)
        humidity = np.random.normal(60, 15, n).clip(20, 100)
        pressure = np.random.normal(1010, 10, n).clip(975, 1035)
    else:
        temp = np.random.normal(25, 8, n)
        wind = np.random.normal(20, 15, n).clip(0, 80)
        humidity = np.random.normal(55, 20, n).clip(10, 100)
        pressure = np.random.normal(1013, 10, n).clip(970, 1040)

    return {
        "temperature": temp,
        "wind_speed": wind,
        "humidity": humidity,
        "pressure": pressure,
    }


def _severity_label(row) -> str:
    """Rule-based severity derived from weather + disaster type with noise."""
    score = 0.0
    # Wind contribution
    score += min(row["wind_speed"] / 280, 1.0) * 35
    # Temperature extremes
    score += (abs(row["temperature"] - 25) / 25) * 15
    # Humidity extremes (both high & low can be bad)
    score += (abs(row["humidity"] - 50) / 50) * 10
    # Pressure drop
    score += max(0, (1013 - row["pressure"]) / 130) * 25
    # Disaster type multiplier
    dtype_mult = {
        "hurricane": 1.3, "tornado": 1.2, "tsunami": 1.25,
        "earthquake": 1.15, "wildfire": 1.1, "volcano": 1.2,
        "flood": 1.0, "landslide": 1.0, "drought": 0.85,
    }
    score *= dtype_mult.get(row["disaster_type"], 1.0)
    # Add noise
    score += np.random.normal(0, 4)
    score = np.clip(score, 0, 100)

    if score >= 62:
        return "critical"
    elif score >= 40:
        return "high"
    elif score >= 22:
        return "medium"
    else:
        return "low"


def generate_emdat_data(n_events: int = 5000) -> pd.DataFrame:
    """Generate EM-DAT-style disaster severity dataset."""
    rows = []
    for dtype in DISASTER_TYPES:
        # Weighted count — some disaster types more common
        weight = {"flood": 2.0, "earthquake": 1.5, "hurricane": 1.2}.get(dtype, 1.0)
        n = int(n_events * weight / sum(
            {"flood": 2.0, "earthquake": 1.5, "hurricane": 1.2}.get(d, 1.0)
            for d in DISASTER_TYPES
        ))
        weather = _weather_for_disaster(dtype, n)
        countries = np.random.choice(COUNTRIES, n)
        lats = np.random.uniform(-60, 70, n)
        lons = np.random.uniform(-180, 180, n)
        years = np.random.randint(1990, 2026, n)
        months = np.random.randint(1, 13, n)

        for i in range(n):
            rows.append({
                "disaster_type": dtype,
                "temperature": round(weather["temperature"][i], 1),
                "wind_speed": round(weather["wind_speed"][i], 1),
                "humidity": round(weather["humidity"][i], 1),
                "pressure": round(weather["pressure"][i], 1),
                "country": countries[i],
                "latitude": round(lats[i], 4),
                "longitude": round(lons[i], 4),
                "year": years[i],
                "month": months[i],
            })

    df = pd.DataFrame(rows)
    df["severity"] = df.apply(_severity_label, axis=1)
    return df


# ---------------------------------------------------------------------------
# 2. Spread dataset  (wildfire / flood area expansion)
# ---------------------------------------------------------------------------

TERRAIN_TYPES = ["flat", "hilly", "mountainous", "forested", "urban", "coastal"]


def generate_spread_data(n: int = 3000) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        dtype = np.random.choice(["wildfire", "flood"])
        current_area = np.random.exponential(50) + 1  # km²
        wind_speed = max(0, np.random.normal(25, 15))
        wind_direction = np.random.uniform(0, 360)
        terrain = np.random.choice(TERRAIN_TYPES)
        elevation = np.random.uniform(0, 3000)
        vegetation_density = np.random.uniform(0, 1)
        days_active = np.random.randint(1, 30)

        # Terrain multiplier for spread
        terrain_mult = {
            "flat": 1.2, "hilly": 0.9, "mountainous": 0.7,
            "forested": 1.5, "urban": 0.6, "coastal": 1.0,
        }[terrain]

        # Realistic spread formula with noise
        base_spread = current_area * (1 + (wind_speed * 0.02 * terrain_mult))
        if dtype == "wildfire":
            base_spread *= (1 + vegetation_density * 0.5)
            base_spread *= max(0.5, 1 - elevation / 5000)
        else:  # flood
            base_spread *= (1 + 0.3 * (1 - elevation / 3000))

        noise = np.random.normal(1.0, 0.15)
        predicted_area = max(current_area, base_spread * noise)

        rows.append({
            "disaster_type": dtype,
            "current_area_km2": round(current_area, 2),
            "wind_speed": round(wind_speed, 1),
            "wind_direction": round(wind_direction, 1),
            "terrain_type": terrain,
            "elevation_m": round(elevation, 1),
            "vegetation_density": round(vegetation_density, 3),
            "days_active": days_active,
            "predicted_area_km2": round(predicted_area, 2),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Impact dataset  (casualties + economic damage)
# ---------------------------------------------------------------------------

def generate_impact_data(n: int = 4000) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        dtype = np.random.choice(DISASTER_TYPES)
        severity_score = np.random.uniform(0, 1)
        affected_pop = int(np.random.exponential(50000) + 100)
        country = np.random.choice(COUNTRIES)
        gdp_pc = COUNTRY_GDP_PER_CAPITA[country]
        infra_density = np.random.uniform(0.1, 1.0)  # 0=rural, 1=dense urban

        # Casualty model
        base_casualties = affected_pop * severity_score * 0.005
        base_casualties *= (1.5 - infra_density * 0.8)  # better infra = fewer deaths
        base_casualties *= max(0.3, 1 - gdp_pc / 80000)  # higher GDP = fewer deaths
        casualties = max(0, int(base_casualties * np.random.lognormal(0, 0.6)))

        # Economic damage (millions USD)
        base_damage = affected_pop * gdp_pc * severity_score * 0.001 / 1_000_000
        base_damage *= (0.5 + infra_density)  # dense areas lose more
        economic_damage = max(0, base_damage * np.random.lognormal(0, 0.5))

        rows.append({
            "disaster_type": dtype,
            "severity_score": round(severity_score, 3),
            "affected_population": affected_pop,
            "country": country,
            "gdp_per_capita": gdp_pc,
            "infrastructure_density": round(infra_density, 3),
            "casualties": casualties,
            "economic_damage_million_usd": round(economic_damage, 2),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Generating synthetic training data …")

    print("  → EM-DAT severity dataset (8 000 events)")
    severity_df = generate_emdat_data(8000)
    severity_path = OUTPUT_DIR / "emdat_severity.csv"
    severity_df.to_csv(severity_path, index=False)
    print(f"    Saved {len(severity_df)} rows → {severity_path}")
    print(f"    Severity distribution:\n{severity_df['severity'].value_counts().to_string()}\n")

    print("  → Spread dataset (5 000 events)")
    spread_df = generate_spread_data(5000)
    spread_path = OUTPUT_DIR / "spread_area.csv"
    spread_df.to_csv(spread_path, index=False)
    print(f"    Saved {len(spread_df)} rows → {spread_path}")

    print("  → Impact dataset (6 000 events)")
    impact_df = generate_impact_data(6000)
    impact_path = OUTPUT_DIR / "impact_casualties.csv"
    impact_df.to_csv(impact_path, index=False)
    print(f"    Saved {len(impact_df)} rows → {impact_path}")

    print("\n✅ All datasets generated in", OUTPUT_DIR)


if __name__ == "__main__":
    main()
