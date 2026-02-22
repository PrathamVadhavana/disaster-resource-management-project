"""
Redis caching layer for expensive queries.

Provides async get/set/invalidate with JSON serialization.
Falls back gracefully when Redis is unavailable (returns None on get).
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

_redis_client = None
_redis_available = False

CACHE_TTL_SHORT = 60          # 1 minute  – volatile data (disasters list)
CACHE_TTL_MEDIUM = 300        # 5 minutes – predictions, forecasts
CACHE_TTL_LONG = 900          # 15 minutes – static-ish data


class _DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


async def _get_redis():
    """Lazy-init Redis connection."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        # Quick connectivity check
        await _redis_client.ping()
        _redis_available = True
        logger.info("Redis cache connected: %s", redis_url)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) – caching disabled", exc)
        _redis_client = None
        _redis_available = False
    return _redis_client


async def cache_get(key: str) -> Optional[Any]:
    """Return cached value or *None* if miss / Redis down."""
    client = await _get_redis()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug("cache_get(%s) error: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SHORT) -> None:
    """Store a JSON-serializable value with a TTL (seconds)."""
    client = await _get_redis()
    if client is None:
        return
    try:
        raw = json.dumps(value, cls=_DateTimeEncoder)
        await client.set(key, raw, ex=ttl)
    except Exception as exc:
        logger.debug("cache_set(%s) error: %s", key, exc)


async def cache_invalidate(*keys: str) -> None:
    """Delete one or more cache keys."""
    client = await _get_redis()
    if client is None:
        return
    try:
        await client.delete(*keys)
    except Exception as exc:
        logger.debug("cache_invalidate error: %s", exc)


async def cache_invalidate_pattern(pattern: str) -> None:
    """Delete all keys matching a glob pattern (e.g. 'disasters:*')."""
    client = await _get_redis()
    if client is None:
        return
    try:
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor, match=pattern, count=100)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
    except Exception as exc:
        logger.debug("cache_invalidate_pattern(%s) error: %s", pattern, exc)
