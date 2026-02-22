"""
Router for live global disaster data from public APIs.
Provides aggregated real-time disaster events from USGS, NASA EONET, GDACS, and ReliefWeb.
"""

from fastapi import APIRouter, Query
from typing import Optional

from app.services.global_disaster_service import get_global_disasters

router = APIRouter()


@router.get("/")
async def list_global_disasters(
    source: Optional[str] = Query(None, description="Filter by source: usgs, eonet, gdacs, reliefweb"),
    type: Optional[str] = Query(None, description="Filter by disaster type: earthquake, flood, cyclone, wildfire, etc."),
    severity: Optional[str] = Query(None, description="Filter by severity: critical, high, medium, low"),
    limit: int = Query(500, ge=1, le=2000, description="Max events to return"),
):
    """Fetch aggregated live global disaster data from multiple free public APIs.

    Data sources:
    - **USGS**: M4.5+ earthquakes worldwide (past 30 days)
    - **NASA EONET**: Active wildfires, storms, volcanoes, floods
    - **GDACS**: Multi-hazard disaster alerts (earthquakes, cyclones, floods, volcanic eruptions)
    - **ReliefWeb**: UN OCHA disaster reports (past 90 days)

    Results are cached for 5 minutes to avoid hammering upstream APIs.
    """
    return await get_global_disasters(
        source=source,
        disaster_type=type,
        severity=severity,
        limit=limit,
    )


@router.get("/sources")
async def list_sources():
    """List available global disaster data sources."""
    return {
        "sources": [
            {
                "id": "usgs",
                "name": "USGS Earthquake Hazards",
                "description": "United States Geological Survey – M4.5+ earthquakes worldwide",
                "url": "https://earthquake.usgs.gov",
                "update_frequency": "Real-time (5 min cache)",
                "data_types": ["earthquake"],
            },
            {
                "id": "eonet",
                "name": "NASA EONET",
                "description": "Earth Observatory Natural Event Tracker – wildfires, storms, volcanoes, floods",
                "url": "https://eonet.gsfc.nasa.gov",
                "update_frequency": "Real-time (5 min cache)",
                "data_types": ["wildfire", "cyclone", "volcanic_eruption", "flood", "landslide"],
            },
            {
                "id": "gdacs",
                "name": "GDACS",
                "description": "Global Disaster Alerting Coordination System – multi-hazard alerts",
                "url": "https://www.gdacs.org",
                "update_frequency": "Real-time (5 min cache)",
                "data_types": ["earthquake", "cyclone", "flood", "volcanic_eruption", "drought", "wildfire"],
            },
            {
                "id": "reliefweb",
                "name": "ReliefWeb",
                "description": "UN OCHA humanitarian information service – global disaster reports",
                "url": "https://reliefweb.int",
                "update_frequency": "Updated frequently (5 min cache)",
                "data_types": ["earthquake", "flood", "cyclone", "epidemic", "drought", "tsunami", "conflict"],
            },
        ]
    }
