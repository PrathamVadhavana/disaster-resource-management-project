import os
from supabase import create_client, Client
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator

# Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    raise ValueError("Missing Supabase credentials in environment variables")

supabase: Client = create_client(supabase_url, supabase_key)

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
