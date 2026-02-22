"""
Rate-limiting middleware using slowapi.

Applies per-IP limits to auth endpoints and computationally expensive routes.
Falls back to a no-op if slowapi is not installed.
"""

import logging
from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    limiter = Limiter(key_func=get_remote_address)
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
