import logging
import os
from sqlalchemy.ext.asyncio import create_async_engine

from app.db_client import DatabaseClient

logger = logging.getLogger(__name__)

# ── Database client ──────────────────────────────────────────────────────────
#
# Single DatabaseClient instance that talks to Supabase (PostgREST).

_db_client = DatabaseClient()

db = _db_client
db_admin = _db_client

# ── SQLAlchemy Engine (for raw SQL execution in scripts) ───────────────────────

engine = None
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    # Handle direct postgres URLs vs asyncpg (if needed)
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif _db_url.startswith("postgresql://"):
        _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    engine = create_async_engine(_db_url, echo=False)


async def init_db():
    """Verify Supabase connectivity.

    Creates the Supabase client on first call and runs a lightweight
    query to confirm the connection is functional.
    """
    try:
        from app.db_client import _get_sb

        _get_sb()
        logger.info("Supabase database client ready")
    except Exception as e:
        logger.warning("Supabase initialisation deferred: %s", e)
        logger.info("Supabase will initialise on first database call")
