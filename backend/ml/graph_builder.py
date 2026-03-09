"""
Bipartite graph construction for GNN-based resource allocation.

Builds a heterogeneous bipartite graph with:
  - **Victim nodes**: resource requests from disaster victims.
  - **NGO nodes**: organisations / resource depots that can fulfil requests.
  - **Edges**: victim ↔ NGO pairs within a configurable radius (default 50 km).

Each node carries a feature vector; each edge carries distance, estimated
travel time, and a resource-type match score.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
from torch_geometric.data import HeteroData

from app.services.distance import haversine

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

# The 8 canonical victim resource types (order matters for one-hot encoding)
RESOURCE_TYPES: List[str] = [
    "Food",
    "Water",
    "Medical",
    "Shelter",
    "Clothing",
    "Financial Aid",
    "Evacuation",
    "Volunteers",
]

_RT_INDEX: Dict[str, int] = {rt.lower(): i for i, rt in enumerate(RESOURCE_TYPES)}
NUM_RESOURCE_TYPES: int = len(RESOURCE_TYPES)

# Approximate average road speed (km/h) used when OSMnx is not available.
_FALLBACK_SPEED_KMH: float = 40.0

# ── Node dataclasses ─────────────────────────────────────────────────────


@dataclass
class VictimNode:
    """Raw data for a single victim/request node."""

    id: str
    lat: float
    lon: float
    priority_score: float  # 0-10 continuous
    medical_needs_encoded: float  # 0 = none, 1 = critical
    hours_since_request: float
    resource_type: str  # one of RESOURCE_TYPES (case-insensitive)


@dataclass
class NgoNode:
    """Raw data for a single NGO / depot node."""

    id: str
    lat: float
    lon: float
    capacity_score: float  # 0-1 normalised capacity
    available_resource_types: List[str]  # subset of RESOURCE_TYPES
    avg_response_time_hours: float
    current_load_ratio: float  # 0 = idle, 1 = fully loaded


# ── Feature helpers ──────────────────────────────────────────────────────


def _resource_type_one_hot(rt: str) -> np.ndarray:
    """Return a one-hot vector of length NUM_RESOURCE_TYPES."""
    vec = np.zeros(NUM_RESOURCE_TYPES, dtype=np.float32)
    idx = _RT_INDEX.get(rt.lower())
    if idx is not None:
        vec[idx] = 1.0
    return vec


def _resource_types_multi_hot(types: List[str]) -> np.ndarray:
    """Return a multi-hot vector for a set of resource types."""
    vec = np.zeros(NUM_RESOURCE_TYPES, dtype=np.float32)
    for rt in types:
        idx = _RT_INDEX.get(rt.lower())
        if idx is not None:
            vec[idx] = 1.0
    return vec


def _victim_features(v: VictimNode) -> np.ndarray:
    """
    Victim feature vector (dim = 5 + NUM_RESOURCE_TYPES = 13).

    [lat, lon, priority_score, medical_needs_encoded,
     hours_since_request, resource_type_one_hot (8)]
    """
    scalar = np.array(
        [v.lat, v.lon, v.priority_score, v.medical_needs_encoded, v.hours_since_request],
        dtype=np.float32,
    )
    return np.concatenate([scalar, _resource_type_one_hot(v.resource_type)])


def _ngo_features(n: NgoNode) -> np.ndarray:
    """
    NGO feature vector (dim = 4 + NUM_RESOURCE_TYPES = 12).

    [lat, lon, capacity_score, available_resource_types_multi_hot (8),
     avg_response_time_hours, current_load_ratio]
    """
    scalar_pre = np.array([n.lat, n.lon, n.capacity_score], dtype=np.float32)
    multi_hot = _resource_types_multi_hot(n.available_resource_types)
    scalar_post = np.array(
        [n.avg_response_time_hours, n.current_load_ratio], dtype=np.float32
    )
    return np.concatenate([scalar_pre, multi_hot, scalar_post])


# ── Edge helpers ─────────────────────────────────────────────────────────


def _estimate_travel_time(distance_km: float) -> float:
    """
    Return estimated travel-time in minutes.

    Tries to use OSMnx for road-network routing. Falls back to a simple
    speed-based estimate when the network is unavailable.
    """
    # OSMnx integration is expensive (downloads road graphs); keep it as a
    # best-effort enhancement — fall back gracefully.
    try:
        import osmnx as ox  # type: ignore

        # Downloading the road network on the fly is too slow for real-time
        # inference.  A production deployment should pre-cache regional graphs.
        # For now, we fall through to the heuristic.
        raise ImportError("OSMnx route caching not implemented yet")
    except (ImportError, Exception):
        pass

    # Heuristic: straight-line distance × detour factor / speed
    detour_factor = 1.3
    return (distance_km * detour_factor / _FALLBACK_SPEED_KMH) * 60.0


def _resource_type_match_score(victim_type: str, ngo_types: List[str]) -> float:
    """
    Return a match score in [0, 1].

    1.0 → exact match, 0.0 → no match at all.
    """
    victim_lower = victim_type.lower()
    ngo_lower = {t.lower() for t in ngo_types}
    if victim_lower in ngo_lower:
        return 1.0
    # Partial: same category family (e.g. Food ↔ Water in survival cluster)
    survival = {"food", "water"}
    health = {"medical", "evacuation"}
    support = {"clothing", "financial aid", "volunteers", "shelter"}
    for cluster in (survival, health, support):
        if victim_lower in cluster and cluster & ngo_lower:
            return 0.5
    return 0.0


# ── Main builder ─────────────────────────────────────────────────────────


def build_graph(
    victims: List[VictimNode],
    ngos: List[NgoNode],
    radius_km: float = 50.0,
) -> HeteroData:
    """
    Construct a PyTorch Geometric ``HeteroData`` bipartite graph.

    Parameters
    ----------
    victims : victim/request nodes.
    ngos : NGO/depot nodes.
    radius_km : maximum great-circle distance to create an edge.

    Returns
    -------
    HeteroData with node features, edge indices, and edge attributes.
    Also stores ``victim_ids`` and ``ngo_ids`` for downstream mapping.
    """
    data = HeteroData()

    # ── Node features ────────────────────────────────────────────────
    if victims:
        v_feats = np.stack([_victim_features(v) for v in victims])
        data["victim"].x = torch.from_numpy(v_feats)
    else:
        data["victim"].x = torch.zeros((0, 5 + NUM_RESOURCE_TYPES), dtype=torch.float32)

    if ngos:
        n_feats = np.stack([_ngo_features(n) for n in ngos])
        data["ngo"].x = torch.from_numpy(n_feats)
    else:
        data["ngo"].x = torch.zeros((0, 4 + NUM_RESOURCE_TYPES), dtype=torch.float32)

    # ── Edges (within radius) ────────────────────────────────────────
    src_indices: List[int] = []  # victim indices
    dst_indices: List[int] = []  # ngo indices
    edge_attrs: List[List[float]] = []

    for vi, v in enumerate(victims):
        for ni, n in enumerate(ngos):
            dist_km = haversine(v.lat, v.lon, n.lat, n.lon)
            if dist_km > radius_km:
                continue
            travel_min = _estimate_travel_time(dist_km)
            match_score = _resource_type_match_score(v.resource_type, n.available_resource_types)
            src_indices.append(vi)
            dst_indices.append(ni)
            edge_attrs.append([dist_km, travel_min, match_score])

    if src_indices:
        edge_index = torch.tensor([src_indices, dst_indices], dtype=torch.long)
        edge_attr = torch.tensor(edge_attrs, dtype=torch.float32)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
        edge_attr = torch.zeros((0, 3), dtype=torch.float32)

    # Victim → NGO direction
    data["victim", "requests", "ngo"].edge_index = edge_index
    data["victim", "requests", "ngo"].edge_attr = edge_attr

    # Reverse edges (NGO → Victim) for message passing in both directions
    data["ngo", "serves", "victim"].edge_index = edge_index.flip(0)
    data["ngo", "serves", "victim"].edge_attr = edge_attr.clone()

    # ── Store IDs for later look-up ──────────────────────────────────
    data["victim"].node_ids = [v.id for v in victims]
    data["ngo"].node_ids = [n.id for n in ngos]

    return data


# ── Convenience: build from DB rows ─────────────────────────────────────


def victim_node_from_dict(d: dict, now: datetime | None = None) -> VictimNode:
    """
    Convert a database row / API dict to a ``VictimNode``.

    Expected keys: id, lat/latitude, lon/longitude, priority_score or priority,
    medical_needs, resource_type, created_at.
    """
    now = now or datetime.now(timezone.utc)
    created_at = d.get("created_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            created_at = now
    elif created_at is None:
        created_at = now

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    hours_since = max((now - created_at).total_seconds() / 3600.0, 0.0)

    # Medical needs: try numeric first, then boolean
    med = d.get("medical_needs_encoded", d.get("medical_needs", 0))
    if isinstance(med, bool):
        med = 1.0 if med else 0.0

    return VictimNode(
        id=str(d.get("id", "")),
        lat=float(d.get("lat", d.get("latitude", 0.0))),
        lon=float(d.get("lon", d.get("longitude", 0.0))),
        priority_score=float(d.get("priority_score", d.get("priority", 5.0))),
        medical_needs_encoded=float(med),
        hours_since_request=hours_since,
        resource_type=str(d.get("resource_type", "Other")),
    )


def ngo_node_from_dict(d: dict) -> NgoNode:
    """
    Convert a database row / API dict to an ``NgoNode``.

    Expected keys: id, lat/latitude, lon/longitude, capacity_score or capacity,
    available_resource_types (list), avg_response_time_hours, current_load_ratio.
    """
    raw_types = d.get("available_resource_types", [])
    if isinstance(raw_types, str):
        raw_types = [t.strip() for t in raw_types.split(",")]

    return NgoNode(
        id=str(d.get("id", "")),
        lat=float(d.get("lat", d.get("latitude", 0.0))),
        lon=float(d.get("lon", d.get("longitude", 0.0))),
        capacity_score=float(d.get("capacity_score", d.get("capacity", 0.5))),
        available_resource_types=raw_types,
        avg_response_time_hours=float(d.get("avg_response_time_hours", 2.0)),
        current_load_ratio=float(d.get("current_load_ratio", 0.0)),
    )
