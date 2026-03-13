"""
In-memory store for ingestion data.

In-memory storage for all ingestion-related collections:
- ingested_events
- weather_observations
- satellite_observations
- alert_notifications
- external_data_sources

Data is kept in memory with a configurable max size per collection.
Oldest entries are evicted when the limit is reached.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

_MAX_EVENTS = 2000
_MAX_WEATHER = 500
_MAX_SATELLITE = 2000
_MAX_ALERTS = 500

_lock = threading.Lock()

# ── Storage ──────────────────────────────────────────────────────────

_ingested_events: OrderedDict[str, dict[str, Any]] = OrderedDict()
_weather_observations: OrderedDict[str, dict[str, Any]] = OrderedDict()
_satellite_observations: OrderedDict[str, dict[str, Any]] = OrderedDict()
_alert_notifications: OrderedDict[str, dict[str, Any]] = OrderedDict()
_external_data_sources: dict[str, dict[str, Any]] = {}

# Dedup sets (external_id values already seen)
_seen_event_ids: set[str] = set()
_seen_satellite_ids: set[str] = set()


# ── Helpers ──────────────────────────────────────────────────────────


def _trim(store: OrderedDict, max_size: int) -> None:
    while len(store) > max_size:
        store.popitem(last=False)


def _match(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, val in filters.items():
        if val is None:
            continue
        if row.get(key) != val:
            return False
    return True


# ── Ingested Events ─────────────────────────────────────────────────


def add_ingested_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with _lock:
        added = []
        for e in events:
            eid = e.get("id", "")
            ext_id = e.get("external_id")
            if ext_id and ext_id in _seen_event_ids:
                continue
            _ingested_events[eid] = e
            if ext_id:
                _seen_event_ids.add(ext_id)
            added.append(e)
        _trim(_ingested_events, _MAX_EVENTS)
    return added


def event_exists(external_id: str) -> bool:
    return external_id in _seen_event_ids


def query_ingested_events(
    *,
    event_type: str | None = None,
    severity: str | None = None,
    processed: bool | None = None,
    since: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with _lock:
        results = list(reversed(_ingested_events.values()))

    # Apply filters
    filtered = []
    for e in results:
        if event_type and e.get("event_type") != event_type:
            continue
        if severity and e.get("severity") != severity:
            continue
        if processed is not None and e.get("processed") != processed:
            continue
        if since and (e.get("ingested_at", "") < since):
            continue
        filtered.append(e)

    return filtered[offset : offset + limit]


def get_ingested_event(event_id: str) -> dict[str, Any] | None:
    return _ingested_events.get(event_id)


# ── Weather Observations ────────────────────────────────────────────


def add_weather_observations(observations: list[dict[str, Any]]) -> None:
    with _lock:
        for o in observations:
            _weather_observations[o.get("id", "")] = o
        _trim(_weather_observations, _MAX_WEATHER)


def query_weather(*, location_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        results = list(reversed(_weather_observations.values()))
    if location_id:
        results = [r for r in results if r.get("location_id") == location_id]
    return results[:limit]


def latest_weather_for_location(location_id: str) -> dict[str, Any] | None:
    rows = query_weather(location_id=location_id, limit=1)
    return rows[0] if rows else None


# ── Satellite Observations ──────────────────────────────────────────


def add_satellite_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with _lock:
        added = []
        for o in observations:
            ext_id = o.get("external_id", "")
            if ext_id and ext_id in _seen_satellite_ids:
                continue
            _satellite_observations[o.get("id", "")] = o
            if ext_id:
                _seen_satellite_ids.add(ext_id)
            added.append(o)
        _trim(_satellite_observations, _MAX_SATELLITE)
    return added


def query_satellites(
    *,
    disaster_id: str | None = None,
    confidence: str | None = None,
    lat_range: tuple[float, float] | None = None,
    lon_range: tuple[float, float] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with _lock:
        results = list(reversed(_satellite_observations.values()))
    filtered = []
    for r in results:
        if disaster_id and r.get("disaster_id") != disaster_id:
            continue
        if confidence and r.get("confidence") != confidence:
            continue
        if lat_range:
            lat = r.get("latitude", 0)
            if lat < lat_range[0] or lat > lat_range[1]:
                continue
        if lon_range:
            lon = r.get("longitude", 0)
            if lon < lon_range[0] or lon > lon_range[1]:
                continue
        filtered.append(r)
        if len(filtered) >= limit:
            break
    return filtered


# ── Alert Notifications ─────────────────────────────────────────────


def add_alert_notification(notif: dict[str, Any]) -> None:
    with _lock:
        _alert_notifications[notif.get("id", "")] = notif
        _trim(_alert_notifications, _MAX_ALERTS)


def query_alerts(*, severity: str | None = None, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        results = list(reversed(_alert_notifications.values()))
    filtered = []
    for r in results:
        if severity and r.get("severity") != severity:
            continue
        if status and r.get("status") != status:
            continue
        filtered.append(r)
        if len(filtered) >= limit:
            break
    return filtered


# ── External Data Sources (metadata) ────────────────────────────────

_DEFAULT_SOURCES = {
    "openweathermap": {
        "id": "src-weather",
        "source_name": "openweathermap",
        "source_type": "api",
        "base_url": "https://api.openweathermap.org/data/2.5",
        "is_active": True,
        "poll_interval_s": 600,
        "last_polled_at": None,
        "last_status": None,
        "last_error": None,
    },
    "gdacs": {
        "id": "src-gdacs",
        "source_name": "gdacs",
        "source_type": "rss_feed",
        "base_url": "https://www.gdacs.org/xml/rss.xml",
        "is_active": True,
        "poll_interval_s": 900,
        "last_polled_at": None,
        "last_status": None,
        "last_error": None,
    },
    "usgs_earthquakes": {
        "id": "src-usgs",
        "source_name": "usgs_earthquakes",
        "source_type": "geojson_feed",
        "base_url": "https://earthquake.usgs.gov/earthquakes/feed",
        "is_active": True,
        "poll_interval_s": 300,
        "last_polled_at": None,
        "last_status": None,
        "last_error": None,
    },
    "nasa_firms": {
        "id": "src-firms",
        "source_name": "nasa_firms",
        "source_type": "csv_api",
        "base_url": "https://firms.modaps.eosdis.nasa.gov/api/area/csv",
        "is_active": True,
        "poll_interval_s": 1800,
        "last_polled_at": None,
        "last_status": None,
        "last_error": None,
    },
    "social_media": {
        "id": "src-social",
        "source_name": "social_media",
        "source_type": "api",
        "base_url": "https://api.twitter.com/2",
        "is_active": True,
        "poll_interval_s": 300,
        "last_polled_at": None,
        "last_status": None,
        "last_error": None,
    },
}


def _ensure_sources() -> None:
    if not _external_data_sources:
        _external_data_sources.update({k: dict(v) for k, v in _DEFAULT_SOURCES.items()})


def get_source_id(source_name: str) -> str:
    _ensure_sources()
    src = _external_data_sources.get(source_name)
    if src:
        return src["id"]
    new_id = f"src-{source_name}"
    _external_data_sources[source_name] = {
        "id": new_id,
        "source_name": source_name,
        "source_type": "unknown",
        "base_url": "",
        "is_active": True,
        "poll_interval_s": 600,
        "last_polled_at": None,
        "last_status": None,
        "last_error": None,
    }
    return new_id


def update_source_status(source_name: str, status: str, error: str | None = None) -> None:
    _ensure_sources()
    src = _external_data_sources.get(source_name)
    if src:
        src["last_polled_at"] = datetime.now(UTC).isoformat()
        src["last_status"] = status
        src["last_error"] = error[:500] if error else None


def get_all_sources() -> list[dict[str, Any]]:
    _ensure_sources()
    return list(_external_data_sources.values())
