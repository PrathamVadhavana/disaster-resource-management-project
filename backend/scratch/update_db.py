import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not found")
        return
        
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        print("Adding trend and risk_score columns...")
        await conn.execute(text("ALTER TABLE public.hotspot_clusters ADD COLUMN IF NOT EXISTS trend text DEFAULT 'stable';"))
        await conn.execute(text("ALTER TABLE public.hotspot_clusters ADD COLUMN IF NOT EXISTS risk_score double precision DEFAULT 0.0;"))
        print("Done")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
