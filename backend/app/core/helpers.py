"""
Shared helper utilities for routers.
"""

from datetime import datetime
from typing import Any, Dict


def serialize_datetime_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert any datetime values in a dict to ISO-format strings."""
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def serialize_disaster(disaster: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a disaster row: serialize datetimes & flatten joined location."""
    for field in ("created_at", "updated_at", "start_date", "end_date"):
        val = disaster.get(field)
        if isinstance(val, datetime):
            disaster[field] = val.isoformat()

    loc = disaster.pop("locations", None)
    if loc:
        disaster["latitude"] = loc.get("latitude")
        disaster["longitude"] = loc.get("longitude")
        disaster["location_name"] = loc.get("name") or loc.get("city") or ""
        disaster["location_city"] = loc.get("city") or ""
        disaster["location_country"] = loc.get("country") or ""

    return disaster
