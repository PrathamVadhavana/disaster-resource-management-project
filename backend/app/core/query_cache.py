"""
In-memory TTL cache for database queries.

Reduces database read operations by caching frequently-accessed
collections (users, locations, platform_settings) and query results.
Falls back transparently on cache miss.
"""

import logging
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("query_cache")

# ── Cache storage ─────────────────────────────────────────────────────────────

_cache: Dict[str, Tuple[Any, float]] = {}  # key → (value, expires_at)
_lock = threading.Lock()

# TTL presets (seconds)
TTL_VERY_SHORT = 15       # 15s — volatile data (active request counts)
TTL_SHORT = 60            # 1 min — lists that change moderately
TTL_MEDIUM = 300          # 5 min — users-by-role, locations
TTL_LONG = 900            # 15 min — platform_settings, static lookups
TTL_VERY_LONG = 1800      # 30 min — rarely changing reference data

# Collections that benefit most from caching
CACHEABLE_COLLECTIONS = {
    "users": TTL_MEDIUM,
    "locations": TTL_LONG,
    "platform_settings": TTL_LONG,
    "disasters": TTL_SHORT,
    "resources": TTL_SHORT,
}


def cache_get(key: str) -> Optional[Any]:
    """Return cached value or None if miss/expired."""
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del _cache[key]
            return None
        return value


def cache_set(key: str, value: Any, ttl: int = TTL_SHORT) -> None:
    """Store a value with TTL."""
    with _lock:
        _cache[key] = (value, time.monotonic() + ttl)


def cache_invalidate(key: str) -> None:
    """Remove a specific key."""
    with _lock:
        _cache.pop(key, None)


def cache_invalidate_prefix(prefix: str) -> None:
    """Remove all keys starting with prefix."""
    with _lock:
        keys_to_remove = [k for k in _cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del _cache[k]


def cache_clear() -> None:
    """Clear entire cache."""
    with _lock:
        _cache.clear()


def cache_stats() -> Dict[str, int]:
    """Return cache size and expired count."""
    now = time.monotonic()
    with _lock:
        total = len(_cache)
        expired = sum(1 for _, (_, exp) in _cache.items() if now > exp)
    return {"total_keys": total, "expired": expired, "active": total - expired}


def cleanup_expired() -> int:
    """Remove expired entries. Called periodically."""
    now = time.monotonic()
    removed = 0
    with _lock:
        keys_to_remove = [k for k, (_, exp) in _cache.items() if now > exp]
        for k in keys_to_remove:
            del _cache[k]
            removed += 1
    return removed


# ── Query-result cache helpers ────────────────────────────────────────────────

def make_query_cache_key(table: str, operation: str, filters: list, order: list,
                         limit: Optional[int], range_start: Optional[int],
                         range_end: Optional[int]) -> str:
    """Build a deterministic cache key from query parameters."""
    filter_str = str(sorted((f, o, str(v)) for f, o, v in filters))
    order_str = str(order)
    return f"q:{table}:{operation}:{filter_str}:{order_str}:{limit}:{range_start}:{range_end}"


# ── Users-by-role cache (heavily used by notification_service) ────────────────

_users_by_role_cache: Dict[str, Tuple[List[Dict], float]] = {}


def get_users_by_role_cached(role: str) -> Optional[List[Dict]]:
    """Return cached users list for a role, or None."""
    entry = _users_by_role_cache.get(role)
    if entry is None:
        return None
    data, expires_at = entry
    if time.monotonic() > expires_at:
        _users_by_role_cache.pop(role, None)
        return None
    return data


def set_users_by_role_cached(role: str, users: List[Dict], ttl: int = TTL_MEDIUM) -> None:
    """Cache users list for a role."""
    _users_by_role_cache[role] = (users, time.monotonic() + ttl)


def invalidate_users_cache() -> None:
    """Clear all users-by-role cache entries."""
    _users_by_role_cache.clear()
