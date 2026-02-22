import logging
import os
from supabase import create_client, Client
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

# ── Supabase clients (lazy-initialised) ──────────────────────────────────────
_supabase: Client | None = None
_supabase_admin: Client | None = None


def _get_supabase_credentials():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key or not service_key:
        raise RuntimeError(
            "Missing Supabase credentials – set SUPABASE_URL, SUPABASE_KEY, "
            "and SUPABASE_SERVICE_KEY environment variables."
        )
    return url, key, service_key


def _init_supabase() -> None:
    global _supabase, _supabase_admin
    url, key, service_key = _get_supabase_credentials()
    _supabase = create_client(url, key)
    _supabase_admin = create_client(url, service_key)


class _LazySupabase:
    """Descriptor that initialises the Supabase clients on first access."""

    def __init__(self, admin: bool = False):
        self._admin = admin

    def __get__(self, obj, objtype=None) -> Client:
        if _supabase is None:
            _init_supabase()
        return _supabase_admin if self._admin else _supabase  # type: ignore[return-value]


class _SupabaseAccessor:
    supabase = _LazySupabase(admin=False)
    supabase_admin = _LazySupabase(admin=True)


_accessor = _SupabaseAccessor()


# Public module-level names kept for backward-compat imports
# Usage:  ``from app.database import supabase``
def __getattr__(name: str):
    if name == "supabase":
        return _accessor.supabase
    if name == "supabase_admin":
        return _accessor.supabase_admin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# SQLAlchemy setup for direct database access if needed (optional)
engine = None
async_session_maker = None
Base = None

try:
    supabase_url = os.getenv("SUPABASE_URL", "")
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"postgresql+asyncpg://postgres:{os.getenv('SUPABASE_DB_PASSWORD')}@{supabase_url.split('//')[1] if '//' in supabase_url else 'localhost'}/postgres"
    )

    # Ensure async driver prefix
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    Base = declarative_base()
except Exception as e:
    logger.warning("SQLAlchemy setup skipped: %s", e)
    logger.info("Using Supabase client for all database operations")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions"""
    if not async_session_maker:
        raise RuntimeError("SQLAlchemy is not configured")
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    if not engine:
        logger.info("SQLAlchemy not available, skipping DB init")
        return
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database initialization failed: %s", e)
        logger.info("Continuing without database - some features may not work")
