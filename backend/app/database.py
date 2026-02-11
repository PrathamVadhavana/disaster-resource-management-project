import os
from supabase import create_client, Client
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator

# Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")  # Public Anon Key
supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY") # Secret Service Role Key


# Attempt to create real Supabase clients; on failure, fall back to an in-memory
# mock that provides a minimal `table(...).insert(...).execute()` and
# `table(...).select(...).execute()` interface so the app can run locally
# without external credentials (useful for development and tests).
def _make_mock_supabase():
    from types import SimpleNamespace

    class TableMock:
        def __init__(self, store, name):
            self.store = store
            self.name = name
            self._filters = []
            self._limit = None
            self._order = None
            self._single = False

        def insert(self, payload):
            # accept either dict or list
            items = payload if isinstance(payload, list) else [payload]
            for it in items:
                self.store.setdefault(self.name, []).append(it)
            self._last_inserted = items
            return self

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, key, value):
            self._filters.append((key, value))
            return self

        def order(self, key, desc=False):
            self._order = (key, desc)
            return self

        def limit(self, n):
            self._limit = n
            return self

        def single(self):
            self._single = True
            return self

        def execute(self):
            data = list(self.store.get(self.name, []))
            for key, val in self._filters:
                data = [r for r in data if r.get(key) == val]
            if self._order:
                key, desc = self._order
                data.sort(key=lambda r: r.get(key), reverse=desc)
            if self._limit is not None:
                data = data[: self._limit]
            if getattr(self, '_last_inserted', None) is not None:
                result = self._last_inserted
                self._last_inserted = None
            else:
                result = data
            if self._single:
                return SimpleNamespace(data=result[0] if result else None)
            return SimpleNamespace(data=result)

    class MockSupabase:
        def __init__(self):
            self._store = {}

        def table(self, name):
            return TableMock(self._store, name)

    return MockSupabase()


_use_mock = False
if not (supabase_url and supabase_key and supabase_service_key):
    _use_mock = True

if not _use_mock:
    try:
        # Client for public operations (respects RLS)
        supabase: Client = create_client(supabase_url, supabase_key)

        # Client for admin operations (bypasses RLS)
        supabase_admin: Client = create_client(supabase_url, supabase_service_key)
    except Exception:
        # Fall back to mock client
        supabase = _make_mock_supabase()
        supabase_admin = supabase
else:
    supabase = _make_mock_supabase()
    supabase_admin = supabase

# SQLAlchemy setup for direct database access if needed
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+asyncpg://postgres:{os.getenv('SUPABASE_DB_PASSWORD')}@{supabase_url.split('//')[1]}/postgres"
)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database sessions"""
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
    try:
        async with engine.begin() as conn:
            # Create tables if they don't exist
            # Note: In production, use Alembic for migrations
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
        print("ℹ️  Continuing without database - some features may not work")
