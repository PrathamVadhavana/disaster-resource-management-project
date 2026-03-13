"""
Rate-limiting middleware using slowapi.

Applies per-IP limits to auth endpoints and computationally expensive routes.
Falls back to a no-op if slowapi is not installed.

Redis backend: when the REDIS_URL env var is set, rate-limit counters are
shared across all workers via Redis. Otherwise, limits are per-process only.
"""

import logging
import os

from fastapi import FastAPI

logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    # Check for Redis backend
    _redis_url = os.getenv("REDIS_URL", "")
    if _redis_url:
        try:
            from slowapi.util import get_remote_address

            limiter = Limiter(
                key_func=get_remote_address,
                storage_uri=_redis_url,
            )
            logger.info("Rate limiting configured with Redis backend: %s", _redis_url.split("@")[-1])
        except Exception as exc:
            logger.warning("Redis connection failed for rate limiting, falling back to in-memory: %s", exc)
            limiter = Limiter(key_func=get_remote_address)
    else:
        limiter = Limiter(key_func=get_remote_address)
        logger.info("Rate limiting using in-memory storage (set REDIS_URL for shared limits)")

    _HAS_SLOWAPI = True
except ImportError:
    limiter = None
    _HAS_SLOWAPI = False
    logger.info("slowapi not installed – rate limiting disabled")


def setup_rate_limiting(app: FastAPI) -> None:
    """Attach the slowapi limiter to the FastAPI app."""
    if not _HAS_SLOWAPI or limiter is None:
        logger.info("Rate limiting skipped (slowapi not available)")
        return

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("Rate limiting enabled")
