"""
DisasterGPT — Training Data Collector
======================================
Scrapes ReliefWeb API for situation reports and formats them
as instruction-tuning pairs for fine-tuning a disaster-domain LLM.

Usage:
    python -m scripts.collect_training_data             # default 5000 reports
    python -m scripts.collect_training_data --limit 500 # smaller dataset
    python -m scripts.collect_training_data --output training_data/disaster_instructions.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os
import random

import httpx
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── ReliefWeb API config ────────────────────────────────────────────────────────
RELIEFWEB_BASE = "https://api.reliefweb.int/v1/reports"
PAGE_SIZE = 100  # max allowed by ReliefWeb per request
REQUEST_DELAY = 0.5  # seconds between pages — be respectful
# ReliefWeb requires a registered appname — get one at:
# https://apidoc.reliefweb.int/parameters#appname
RELIEFWEB_APPNAME = os.environ.get("RELIEFWEB_APPNAME", "")

# Disaster-type keywords for instruction generation
DISASTER_TYPES = [
    "flood", "earthquake", "cyclone", "hurricane", "typhoon", "tsunami",
    "drought", "landslide", "wildfire", "volcanic eruption", "storm",
    "conflict", "epidemic", "famine", "displacement", "cholera",
    "tornado", "heatwave", "cold wave", "avalanche",
]

SEVERITY_LABELS = ["low", "moderate", "high", "critical"]


# ── HTML → plain text ───────────────────────────────────────────────────────────
def html_to_text(html: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")
    # collapse blank lines & leading/trailing whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Instruction generation ──────────────────────────────────────────────────────
def _detect_disaster_type(text: str) -> str:
    """Heuristic: pick the first matching disaster keyword from the text."""
    lower = text.lower()
    for dt in DISASTER_TYPES:
        if dt in lower:
            return dt
    return "disaster"


def _detect_severity(text: str) -> str:
    """Heuristic severity from keywords in the report body."""
    lower = text.lower()
    critical_kw = ["catastrophic", "critical", "unprecedented", "mass casualty",
                   "state of emergency", "declared emergency", "death toll"]
    high_kw = ["severe", "major", "significant damage", "thousands displaced",
               "urgent", "emergency"]
    moderate_kw = ["moderate", "localized", "some damage", "hundreds affected"]

    for kw in critical_kw:
        if kw in lower:
            return "critical"
    for kw in high_kw:
        if kw in lower:
            return "high"
    for kw in moderate_kw:
        if kw in lower:
            return "moderate"
    return "low"


def _extract_country(report: dict[str, Any]) -> str:
    """Extract primary country from ReliefWeb report metadata."""
    countries = report.get("fields", {}).get("country", [])
    if countries:
        return countries[0].get("name", "Unknown")
    primary = report.get("fields", {}).get("primary_country", {})
    return primary.get("name", "Unknown")


def _build_instruction(report: dict[str, Any], body_text: str) -> dict[str, str]:
    """Build a single instruction-tuning pair from a report."""
    title = report.get("fields", {}).get("title", "Untitled report")
    country = _extract_country(report)
    disaster_type = _detect_disaster_type(title + " " + body_text[:2000])
    severity = _detect_severity(body_text[:3000])
    date_str = report.get("fields", {}).get("date", {}).get("created", "")
    date_part = ""
    if date_str:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_part = f", date: {dt.strftime('%Y-%m-%d')}"
        except Exception:
            pass

    # Truncate output to ~4096 tokens (~16 000 chars) for training efficiency
    truncated_body = body_text[:16_000]

    instruction = (
        f"Generate a situation report and response plan for "
        f"{disaster_type}, severity: {severity}, location: {country}{date_part}"
    )

    return {
        "instruction": instruction,
        "input": "",
        "output": truncated_body,
        "metadata": {
            "source": "reliefweb",
            "report_id": str(report.get("id", "")),
            "title": title,
            "country": country,
            "disaster_type": disaster_type,
            "severity": severity,
        },
    }


# ── ReliefWeb scraper ───────────────────────────────────────────────────────────
def fetch_reports(limit: int = 5000, appname: str = "") -> list[dict[str, Any]]:
    """
    Fetch situation reports from ReliefWeb API.
    Uses pagination with offset; respects rate limits.
    Requires a registered appname (env RELIEFWEB_APPNAME or --appname).
    """
    resolved_appname = appname or RELIEFWEB_APPNAME
    if not resolved_appname:
        logger.warning(
            "No ReliefWeb appname set. The API now requires a registered appname.\n"
            "Register at: https://apidoc.reliefweb.int/parameters#appname\n"
            "Then set RELIEFWEB_APPNAME env var or use --appname flag.\n"
            "Falling back to synthetic training data generation."
        )
        return []

    all_reports: list[dict[str, Any]] = []
    offset = 0

    # appname goes as a query parameter (not in the JSON body)
    api_url = f"{RELIEFWEB_BASE}?appname={resolved_appname}"

    payload_base = {
        "filter": {
            "field": "format.name",
            "value": "Situation Report",
        },
        "fields": {
            "include": [
                "title", "body", "date.created", "country.name",
                "primary_country.name", "source.name", "disaster_type.name",
            ]
        },
        "sort": ["date.created:desc"],
        "limit": PAGE_SIZE,
    }

    with httpx.Client(timeout=30) as client:
        while offset < limit:
            payload = {**payload_base, "offset": offset}
            logger.info("Fetching reports %d – %d ...", offset, offset + PAGE_SIZE)

            try:
                resp = client.post(api_url, json=payload)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error("HTTP %s at offset %d: %s", exc.response.status_code, offset, exc)
                if exc.response.status_code == 429:
                    logger.warning("Rate-limited — sleeping 10 s")
                    time.sleep(10)
                    continue
                if exc.response.status_code in (400, 403):
                    logger.error(
                        "API rejected request (likely invalid appname). "
                        "Register at https://apidoc.reliefweb.int/parameters#appname"
                    )
                    break
                break
            except httpx.RequestError as exc:
                logger.error("Request error at offset %d: %s", offset, exc)
                time.sleep(5)
                continue

            data = resp.json()
            items = data.get("data", [])
            if not items:
                logger.info("No more reports at offset %d — done.", offset)
                break

            all_reports.extend(items)
            offset += PAGE_SIZE
            time.sleep(REQUEST_DELAY)

    logger.info("Fetched %d raw reports.", len(all_reports))
    return all_reports


def process_reports(reports: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert raw ReliefWeb reports to instruction-tuning pairs."""
    pairs: list[dict[str, str]] = []
    skipped = 0

    for report in reports:
        body_html = report.get("fields", {}).get("body", "")
        if not body_html:
            skipped += 1
            continue

        body_text = html_to_text(body_html)
        # Skip very short reports (< 200 chars) — unlikely to be useful
        if len(body_text) < 200:
            skipped += 1
            continue

        pair = _build_instruction(report, body_text)
        pairs.append(pair)

    logger.info(
        "Processed %d instruction pairs (%d skipped).",
        len(pairs), skipped,
    )
    return pairs


# ── Augmentation: alternative instruction phrasings ─────────────────────────────
INSTRUCTION_TEMPLATES = [
    "Generate a situation report and response plan for {dtype}, severity: {sev}, location: {loc}",
    "What actions should be taken for a {sev} {dtype} in {loc}?",
    "As a disaster coordinator, draft an operational briefing for the {dtype} affecting {loc}. Severity level: {sev}.",
    "Summarise the humanitarian situation and recommend resource allocation for {dtype} in {loc} (severity: {sev}).",
    "Create an emergency response plan for a {sev}-severity {dtype} event in {loc}.",
]


def augment_instructions(pairs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Create additional instruction variants per report for diversity."""
    augmented: list[dict[str, str]] = []
    for pair in pairs:
        augmented.append(pair)  # keep original
        meta = pair.get("metadata", {})
        dtype = meta.get("disaster_type", "disaster")
        sev = meta.get("severity", "moderate")
        loc = meta.get("country", "Unknown")

        # Add 1-2 alternative phrasings (not all — keeps dataset balanced)
        for tmpl in INSTRUCTION_TEMPLATES[1:3]:
            augmented.append({
                "instruction": tmpl.format(dtype=dtype, sev=sev, loc=loc),
                "input": "",
                "output": pair["output"],
                "metadata": meta,
            })

    logger.info("Augmented dataset: %d → %d pairs.", len(pairs), len(augmented))
    return augmented


# ── Persistence ─────────────────────────────────────────────────────────────────
def save_jsonl(pairs: list[dict], output_path: str | Path) -> Path:
    """Save instruction pairs as JSONL (one JSON object per line)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        for pair in pairs:
            # Drop metadata for the training file — keep only instruction/input/output
            row = {
                "instruction": pair["instruction"],
                "input": pair.get("input", ""),
                "output": pair["output"],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    size_mb = path.stat().st_size / (1024 * 1024)
    logger.info("Saved %d pairs → %s (%.1f MB)", len(pairs), path, size_mb)
    return path


def save_metadata(pairs: list[dict], output_path: str | Path) -> Path:
    """Save full pairs with metadata for provenance tracking."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "total_pairs": len(pairs),
                "source": "reliefweb",
                "records": pairs,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info("Saved metadata → %s", path)
    return path


# ── Synthetic data generation ───────────────────────────────────────────────────
# Used when ReliefWeb API is unavailable (no registered appname)

_SYNTH_LOCATIONS = [
    ("Bangladesh", "Dhaka"), ("India", "Mumbai"), ("Nepal", "Kathmandu"),
    ("Philippines", "Manila"), ("Indonesia", "Jakarta"), ("Pakistan", "Karachi"),
    ("Haiti", "Port-au-Prince"), ("Mozambique", "Maputo"), ("Japan", "Tokyo"),
    ("Turkey", "Istanbul"), ("Syria", "Aleppo"), ("Somalia", "Mogadishu"),
    ("Yemen", "Sanaa"), ("Ethiopia", "Addis Ababa"), ("South Sudan", "Juba"),
    ("Myanmar", "Yangon"), ("Afghanistan", "Kabul"), ("Nigeria", "Lagos"),
    ("Kenya", "Nairobi"), ("Colombia", "Bogota"),
]

_SYNTH_TEMPLATES = [
    {
        "type": "flood",
        "body": (
            "SITUATION OVERVIEW\n\n"
            "Heavy monsoon rains have caused severe flooding in {city}, {country}, "
            "displacing approximately {displaced:,} people across {districts} districts. "
            "Water levels have risen to {water_level}m above normal, submerging residential areas "
            "and critical infrastructure. {casualties} fatalities have been confirmed so far.\n\n"
            "HUMANITARIAN NEEDS\n\n"
            "- Emergency shelter for {displaced:,} displaced persons\n"
            "- Clean drinking water — municipal supply contaminated\n"
            "- Medical supplies: waterborne disease prevention kits\n"
            "- Food supplies for an estimated {food_need:,} affected individuals\n"
            "- Search and rescue operations in {sar_areas} submerged neighborhoods\n\n"
            "RESPONSE ACTIONS\n\n"
            "National disaster management authority has declared a state of emergency. "
            "Military helicopters deployed for evacuation. International aid agencies "
            "mobilising emergency response teams. Temporary shelters established at "
            "{shelters} locations including schools and community centers.\n\n"
            "RESOURCE REQUIREMENTS\n\n"
            "- Water purification units: {water_units}\n"
            "- Emergency tents: {tents:,}\n"
            "- Medical teams: {med_teams}\n"
            "- Rescue boats: {boats}\n"
            "- Food ration packs: {food_packs:,}"
        ),
    },
    {
        "type": "earthquake",
        "body": (
            "SITUATION OVERVIEW\n\n"
            "A magnitude {magnitude} earthquake struck {city}, {country} at {time} local time, "
            "with the epicentre located {depth}km underground. The quake caused widespread "
            "structural damage across the metropolitan area. {casualties} deaths confirmed, "
            "{injured:,} injured, and an estimated {displaced:,} people displaced from their homes.\n\n"
            "DAMAGE ASSESSMENT\n\n"
            "- {buildings_collapsed:,} buildings collapsed or severely damaged\n"
            "- Critical infrastructure: {infra_damage}\n"
            "- Hospitals operating at reduced capacity\n"
            "- Power outages affecting {power_out:,} households\n"
            "- Road access disrupted in {road_blocked} areas\n\n"
            "HUMANITARIAN NEEDS\n\n"
            "Immediate priorities include urban search and rescue, emergency medical care, "
            "temporary shelter, and restoration of water supply. Aftershocks continuing, "
            "complicating rescue efforts.\n\n"
            "COORDINATION\n\n"
            "UN OCHA has activated the cluster system. UNDAC team deployed. "
            "International search and rescue teams from {sar_countries} countries arriving. "
            "Government has requested international assistance."
        ),
    },
    {
        "type": "cyclone",
        "body": (
            "SITUATION OVERVIEW\n\n"
            "Tropical Cyclone {name} made landfall near {city}, {country} as a Category {category} "
            "storm with sustained winds of {wind_speed}km/h. Storm surge of {surge}m reported "
            "along the coastline. {casualties} fatalities confirmed, with {missing} persons still missing.\n\n"
            "IMPACT\n\n"
            "- {displaced:,} people evacuated from coastal communities\n"
            "- Extensive damage to crops affecting {crop_area:,} hectares\n"
            "- Fishing fleet: {boats_damaged} vessels damaged or destroyed\n"
            "- Communication networks disrupted across {comm_areas} provinces\n\n"
            "RESPONSE PRIORITIES\n\n"
            "1. Search and rescue in affected coastal communities\n"
            "2. Emergency shelter and food distribution\n"
            "3. Restoration of clean water supply\n"
            "4. Medical response — injury treatment and disease prevention\n"
            "5. Debris clearance for road access\n\n"
            "RESOURCE MOBILIZATION\n\n"
            "Red Cross/Red Crescent has deployed {rc_teams} emergency response units. "
            "WFP pre-positioned stocks being distributed. Government allocated "
            "emergency fund of ${fund}M for immediate relief operations."
        ),
    },
    {
        "type": "drought",
        "body": (
            "SITUATION OVERVIEW\n\n"
            "Prolonged drought conditions in {country} have entered their {month}th consecutive month, "
            "with rainfall at {rain_pct}% of seasonal average. An estimated {affected:,} people "
            "are facing acute food insecurity across {regions} regions.\n\n"
            "FOOD SECURITY\n\n"
            "- IPC Phase 3 (Crisis): {crisis:,} people\n"
            "- IPC Phase 4 (Emergency): {emergency:,} people\n"
            "- Livestock losses: {livestock:,} animals\n"
            "- Crop production: {crop_loss}% below average\n\n"
            "WATER SITUATION\n\n"
            "{water_sources}% of water sources dried up or critically low. "
            "Water trucking operations serving {water_served:,} people daily but "
            "demand far exceeds current capacity.\n\n"
            "HUMANITARIAN RESPONSE\n\n"
            "FAO and WFP scaling up emergency food assistance. Supplementary feeding "
            "programmes targeting {children:,} malnourished children under 5. "
            "Cash transfer programmes reaching {cash:,} households."
        ),
    },
    {
        "type": "epidemic",
        "body": (
            "SITUATION OVERVIEW\n\n"
            "A {disease} outbreak has been declared in {country}, with {cases:,} confirmed cases "
            "and {deaths} deaths reported across {provinces} provinces as of today. "
            "Case fatality rate stands at {cfr}%. The outbreak originated in {city} and has "
            "spread to neighbouring areas.\n\n"
            "HEALTH RESPONSE\n\n"
            "- {treatment_centers} treatment centers established\n"
            "- {health_workers:,} health workers deployed\n"
            "- Contact tracing: {contacts:,} contacts identified and monitored\n"
            "- Vaccination campaign targeting {vax_target:,} people\n\n"
            "CHALLENGES\n\n"
            "Limited laboratory capacity, inadequate medical supplies, "
            "community resistance to health measures, and cross-border movement "
            "complicating containment efforts.\n\n"
            "RESOURCE NEEDS\n\n"
            "WHO has classified this as a Grade {grade} emergency. "
            "Urgent need for medical supplies, PPE, diagnostic kits, and "
            "additional health personnel. Estimated funding gap: ${gap}M."
        ),
    },
]


def _rand(low: int, high: int) -> int:
    return random.randint(low, high)


def generate_synthetic_reports(count: int = 500) -> list[dict[str, Any]]:
    """Generate synthetic disaster reports for training when API is unavailable."""
    logger.info("Generating %d synthetic training reports ...", count)
    reports: list[dict[str, Any]] = []
    cyclone_names = ["Amphan", "Idai", "Haiyan", "Nargis", "Pam", "Winston", "Maria", "Irma", "Dorian", "Fani"]
    diseases = ["cholera", "measles", "Ebola", "dengue fever", "malaria", "typhoid"]

    for i in range(count):
        tmpl = random.choice(_SYNTH_TEMPLATES)
        country, city = random.choice(_SYNTH_LOCATIONS)
        sev = random.choice(SEVERITY_LABELS)

        params: dict[str, Any] = {
            "city": city, "country": country,
            "displaced": _rand(1000, 500000),
            "casualties": _rand(0, 2000),
            "districts": _rand(3, 25),
        }

        if tmpl["type"] == "flood":
            params.update({
                "water_level": round(random.uniform(1.5, 8.0), 1),
                "food_need": _rand(5000, 200000),
                "sar_areas": _rand(5, 30),
                "shelters": _rand(10, 100),
                "water_units": _rand(20, 200),
                "tents": _rand(500, 20000),
                "med_teams": _rand(5, 50),
                "boats": _rand(20, 200),
                "food_packs": _rand(10000, 500000),
            })
        elif tmpl["type"] == "earthquake":
            params.update({
                "magnitude": round(random.uniform(5.5, 8.5), 1),
                "time": f"{_rand(0,23):02d}:{_rand(0,59):02d}",
                "depth": _rand(5, 80),
                "injured": _rand(500, 50000),
                "buildings_collapsed": _rand(100, 30000),
                "infra_damage": random.choice(["major hospital partially collapsed", "bridges damaged", "water main ruptured", "airport runway cracked"]),
                "power_out": _rand(10000, 500000),
                "road_blocked": _rand(5, 40),
                "sar_countries": _rand(3, 15),
            })
        elif tmpl["type"] == "cyclone":
            params.update({
                "name": random.choice(cyclone_names),
                "category": _rand(2, 5),
                "wind_speed": _rand(120, 300),
                "surge": round(random.uniform(2.0, 8.0), 1),
                "missing": _rand(10, 500),
                "crop_area": _rand(5000, 200000),
                "boats_damaged": _rand(50, 2000),
                "comm_areas": _rand(3, 15),
                "rc_teams": _rand(5, 30),
                "fund": _rand(10, 500),
            })
        elif tmpl["type"] == "drought":
            params.update({
                "month": _rand(4, 18),
                "rain_pct": _rand(10, 45),
                "affected": _rand(100000, 5000000),
                "regions": _rand(3, 12),
                "crisis": _rand(50000, 2000000),
                "emergency": _rand(10000, 500000),
                "livestock": _rand(10000, 500000),
                "crop_loss": _rand(30, 80),
                "water_sources": _rand(40, 85),
                "water_served": _rand(10000, 200000),
                "children": _rand(5000, 200000),
                "cash": _rand(5000, 100000),
            })
        elif tmpl["type"] == "epidemic":
            params.update({
                "disease": random.choice(diseases),
                "cases": _rand(500, 50000),
                "deaths": _rand(10, 2000),
                "provinces": _rand(3, 20),
                "cfr": round(random.uniform(0.5, 25.0), 1),
                "treatment_centers": _rand(5, 50),
                "health_workers": _rand(100, 5000),
                "contacts": _rand(1000, 50000),
                "vax_target": _rand(50000, 2000000),
                "grade": _rand(1, 3),
                "gap": _rand(5, 200),
            })

        try:
            body = tmpl["body"].format(**params)
        except KeyError:
            body = tmpl["body"]  # fallback: unformatted

        report = {
            "id": f"synth-{i:05d}",
            "fields": {
                "title": f"{country}: {tmpl['type'].title()} Situation Report #{_rand(1,50)}",
                "body": body,
                "date": {"created": datetime.now(timezone.utc).isoformat()},
                "country": [{"name": country}],
                "primary_country": {"name": country},
            },
        }
        reports.append(report)

    logger.info("Generated %d synthetic reports.", len(reports))
    return reports


# ── CLI ─────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Collect ReliefWeb situation reports for DisasterGPT training"
    )
    parser.add_argument(
        "--limit", type=int, default=5000,
        help="Maximum number of reports to fetch (default: 5000)",
    )
    parser.add_argument(
        "--output", type=str,
        default="training_data/disaster_instructions.jsonl",
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--augment", action="store_true", default=True,
        help="Augment with alternative instruction phrasings",
    )
    parser.add_argument(
        "--no-augment", dest="augment", action="store_false",
        help="Disable instruction augmentation",
    )
    parser.add_argument(
        "--appname", type=str, default="",
        help="ReliefWeb registered appname (or set RELIEFWEB_APPNAME env var)",
    )
    parser.add_argument(
        "--synthetic", action="store_true", default=False,
        help="Force synthetic data generation (skip API)",
    )
    args = parser.parse_args()

    logger.info("=== DisasterGPT Training Data Collector ===")
    logger.info("Target: %d reports", args.limit)

    # 1. Fetch from API or generate synthetic
    if args.synthetic:
        reports = generate_synthetic_reports(count=args.limit)
    else:
        reports = fetch_reports(limit=args.limit, appname=args.appname)
        if not reports:
            logger.info("Falling back to synthetic data generation.")
            reports = generate_synthetic_reports(count=min(args.limit, 1000))

    if not reports:
        logger.error("No reports available — exiting.")
        return

    # 2. Process
    pairs = process_reports(reports)
    if not pairs:
        logger.error("No valid instruction pairs generated — exiting.")
        return

    # 3. Augment
    if args.augment:
        pairs = augment_instructions(pairs)

    # 4. Save training file
    save_jsonl(pairs, args.output)

    # 5. Save metadata (for reproducibility)
    meta_path = Path(args.output).with_suffix(".meta.json")
    save_metadata(pairs, meta_path)

    logger.info("=== Done! Ready for fine-tuning. ===")


if __name__ == "__main__":
    main()
