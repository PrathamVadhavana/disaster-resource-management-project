"""
Haversine-based distance utilities for resource allocation.

Computes great-circle distances between (lat, lng) pairs so the
optimizer can penalise far-away depots.
"""

from __future__ import annotations

import math
from typing import List, Tuple

# Mean Earth radius in km (WGS-84)
_EARTH_RADIUS_KM = 6_371.0


def haversine(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """Return the great-circle distance in **km** between two points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def build_distance_matrix(
    depots: List[Tuple[float, float]],
    zones: List[Tuple[float, float]],
) -> List[List[float]]:
    """
    Build a *depots × zones* distance matrix (values in km).

    Parameters
    ----------
    depots : list of (lat, lng) tuples — resource depot locations.
    zones  : list of (lat, lng) tuples — disaster zone locations.

    Returns
    -------
    2-D list where ``matrix[i][j]`` is the distance from depot *i* to zone *j*.
    """
    return [
        [haversine(d[0], d[1], z[0], z[1]) for z in zones]
        for d in depots
    ]
