import logging

from app.db_client import DatabaseClient

logger = logging.getLogger(__name__)

# ── Database client ──────────────────────────────────────────────────────────
#
# Single DatabaseClient instance that talks to Supabase (PostgREST).

_db_client = DatabaseClient()

db = _db_client
db_admin = _db_client


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
