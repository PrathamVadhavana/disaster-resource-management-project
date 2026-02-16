import os
from supabase import create_client, Client
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator

# Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")  # Public Anon Key
supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY") # Secret Service Role Key

if not supabase_url or not supabase_key or not supabase_service_key:
    raise ValueError("Missing Supabase credentials in environment variables")

# Client for public operations (respects RLS)
supabase: Client = create_client(supabase_url, supabase_key)

# Client for admin operations (bypasses RLS)
supabase_admin: Client = create_client(supabase_url, supabase_service_key)

# SQLAlchemy setup for direct database access if needed (optional)
engine = None
async_session_maker = None
Base = None

try:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"postgresql+asyncpg://postgres:{os.getenv('SUPABASE_DB_PASSWORD')}@{supabase_url.split('//')[1]}/postgres"
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
    print(f"⚠️  SQLAlchemy setup skipped: {e}")
    print("ℹ️  Using Supabase client for all database operations")


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
        print("ℹ️  SQLAlchemy not available, skipping DB init")
        return
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️  Database initialization failed: {e}")
        print("ℹ️  Continuing without database - some features may not work")
