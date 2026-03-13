"""
backend/ml/graph_builder.py - Heterogeneous graph construction for GAT assignment.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    from torch_geometric.data import HeteroData

    _HAS_GRAPH_DEPS = True
except ImportError:
    _HAS_GRAPH_DEPS = False
    logger.warning("torch_geometric not available - graph builder disabled")

from dataclasses import dataclass, field


@dataclass
class VictimNode:
    id: str
    lat: float
    lon: float
    priority_score: float = 5.0
    medical_needs_encoded: float = 0.0
    hours_since_request: float = 0.0
    resource_type: str = "unknown"


@dataclass
class NgoNode:
    id: str
    lat: float
    lon: float
    capacity_score: float = 0.5
    available_resource_types: list[str] = field(default_factory=list)
    avg_response_time_hours: float = 12.0
    current_load_ratio: float = 0.0


def victim_node_from_dict(d: dict[str, Any]) -> VictimNode:
    """Utility to create a VictimNode from a database dictionary."""
    return VictimNode(
        id=str(d.get("id", "")),
        lat=float(d.get("lat") or d.get("latitude", 0.0)),
        lon=float(d.get("lon") or d.get("longitude", 0.0)),
        priority_score=float(d.get("priority_score") or d.get("priority", 5.0)),
        medical_needs_encoded=float(
            d.get("medical_needs_encoded") or (1.0 if str(d.get("resource_type", "")).lower() == "medical" else 0.0)
        ),
        hours_since_request=float(d.get("hours_since_request") or d.get("hours_since_submission") or 0.0),
        resource_type=str(d.get("resource_type", "unknown")),
    )


def ngo_node_from_dict(d: dict[str, Any]) -> NgoNode:
    """Utility to create an NgoNode from a database dictionary."""
    return NgoNode(
        id=str(d.get("id", "")),
        lat=float(d.get("lat") or d.get("latitude", 0.0)),
        lon=float(d.get("lon") or d.get("longitude", 0.0)),
        capacity_score=float(d.get("capacity_score") or 0.5),
        available_resource_types=d.get("available_resource_types", []),
        avg_response_time_hours=float(d.get("avg_response_time_hours") or d.get("avg_response_time", 12.0)),
        current_load_ratio=float(d.get("current_load_ratio", 0.0)),
    )


# 8 canonical resource types
RESOURCE_TYPES = ["food", "water", "medical", "shelter", "clothing", "financial_aid", "evacuation", "volunteers"]
RT_INDEX = {rt: i for i, rt in enumerate(RESOURCE_TYPES)}


def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two points."""
    R = 6371
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c


def _one_hot_rt(rt_name):
    vec = np.zeros(8, dtype=np.float32)
    idx = RT_INDEX.get(str(rt_name).lower())
    if idx is not None:
        vec[idx] = 1.0
    return vec


def _multi_hot_rt(rt_list):
    vec = np.zeros(8, dtype=np.float32)
    for rt in rt_list:
        idx = RT_INDEX.get(str(rt).lower())
        if idx is not None:
            vec[idx] = 1.0
    return vec


def _get_val(obj, key, default=None):
    if hasattr(obj, "get"):
        return obj.get(key, default)
    return getattr(obj, key, default)


def build_graph(victim_dicts, ngo_dicts, radius_km=50.0):
    """
    Build a HeteroData object from database records or Node objects.

    Victim features (13 dims): [lat, lon, priority, medical, hours, one_hot(8)]
    NGO features (13 dims): [lat, lon, capacity, multi_hot(8), avg_resp, load_ratio]
    Edge features (3 dims): [dist_km, travel_min, match_score]
    """
    if not _HAS_GRAPH_DEPS:
        return None

    data = HeteroData()
    now = datetime.now(UTC)

    # Build Victim nodes
    v_features = []
    for v in victim_dicts:
        lat = float(_get_val(v, "lat", 0.0) or _get_val(v, "latitude", 0.0))
        lon = float(_get_val(v, "lon", 0.0) or _get_val(v, "longitude", 0.0))
        priority = float(_get_val(v, "priority_score", 5.0))
        medical = float(_get_val(v, "medical_needs_encoded", 0.0))

        hours = _get_val(v, "hours_since_request", 0.0)
        if hours == 0.0:
            created_at = _get_val(v, "created_at")
            if isinstance(created_at, str):
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    hours = (now - dt).total_seconds() / 3600.0
                except Exception:
                    hours = 0.0

        rt_vec = _one_hot_rt(_get_val(v, "resource_type", ""))
        feat = [lat, lon, priority, medical, hours] + rt_vec.tolist()
        v_features.append(feat)

    if not v_features:
        data["victim"].x = torch.zeros((0, 13), dtype=torch.float32)
    else:
        data["victim"].x = torch.tensor(v_features, dtype=torch.float32)

    # Build NGO nodes
    n_features = []
    for n in ngo_dicts:
        lat = float(_get_val(n, "lat", 0.0) or _get_val(n, "latitude", 0.0))
        lon = float(_get_val(n, "lon", 0.0) or _get_val(n, "longitude", 0.0))
        capacity = float(_get_val(n, "capacity_score", 0.5))

        rt_list = _get_val(n, "available_resource_types", [])
        if isinstance(rt_list, str):
            rt_list = [t.strip() for t in rt_list.split(",")]

        rt_vec = _multi_hot_rt(rt_list)
        avg_resp = float(_get_val(n, "avg_response_time_hours", 12.0))
        load = float(_get_val(n, "current_load_ratio", 0.0))

        feat = [lat, lon, capacity] + rt_vec.tolist() + [avg_resp, load]
        n_features.append(feat)

    if not n_features:
        data["ngo"].x = torch.zeros((0, 13), dtype=torch.float32)
    else:
        data["ngo"].x = torch.tensor(n_features, dtype=torch.float32)

    # Build Edges (Victim <-> NGO)
    v_indices = []
    n_indices = []
    e_features = []

    for vi, v in enumerate(victim_dicts):
        v_rt = str(_get_val(v, "resource_type", "")).lower()
        v_lat = float(_get_val(v, "lat", 0.0) or _get_val(v, "latitude", 0.0))
        v_lon = float(_get_val(v, "lon", 0.0) or _get_val(v, "longitude", 0.0))

        for ni, n in enumerate(ngo_dicts):
            n_lat = float(_get_val(n, "lat", 0.0) or _get_val(n, "latitude", 0.0))
            n_lon = float(_get_val(n, "lon", 0.0) or _get_val(n, "longitude", 0.0))

            dist = haversine(v_lat, v_lon, n_lat, n_lon)
            if dist > radius_km:
                continue

            # Simple travel time: 1.5 min per km
            travel_time = dist * 1.5

            # Match score
            n_rts = _get_val(n, "available_resource_types", [])
            if isinstance(n_rts, str):
                n_rts = [t.strip().lower() for t in n_rts.split(",")]
            else:
                n_rts = [str(t).lower() for t in n_rts]

            match_score = 1.0 if v_rt in n_rts else 0.0

            v_indices.append(vi)
            n_indices.append(ni)
            e_features.append([dist, travel_time, match_score])

    if not v_indices:
        data["victim", "requests", "ngo"].edge_index = torch.zeros((2, 0), dtype=torch.long)
        data["victim", "requests", "ngo"].edge_attr = torch.zeros((0, 3), dtype=torch.float32)
        data["ngo", "serves", "victim"].edge_index = torch.zeros((2, 0), dtype=torch.long)
        data["ngo", "serves", "victim"].edge_attr = torch.zeros((0, 3), dtype=torch.float32)
    else:
        v_idx = torch.tensor(v_indices, dtype=torch.long)
        n_idx = torch.tensor(n_indices, dtype=torch.long)

        data["victim", "requests", "ngo"].edge_index = torch.stack([v_idx, n_idx], dim=0)
        data["victim", "requests", "ngo"].edge_attr = torch.tensor(e_features, dtype=torch.float32)

        # Add reverse edges
        data["ngo", "serves", "victim"].edge_index = torch.stack([n_idx, v_idx], dim=0)
        data["ngo", "serves", "victim"].edge_attr = torch.tensor(e_features, dtype=torch.float32)

    return data
