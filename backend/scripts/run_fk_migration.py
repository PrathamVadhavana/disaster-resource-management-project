"""Run the FK migration directly against PostgreSQL."""
import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import asyncpg

sql_file = Path(__file__).resolve().parent.parent.parent / "database" / "migrations" / "008_fk_migration.sql"
sql = sql_file.read_text(encoding="utf-8")

print(f"Running FK migration ({sql_file.name})...")
print(f"SQL length: {len(sql)} chars\n")


async def run_migration():
    db_url = os.environ.get("DATABASE_URL", "")
    # Convert SQLAlchemy URL to plain PostgreSQL URL for asyncpg
    conn_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        conn = await asyncpg.connect(conn_url)
        await conn.execute(sql)
        await conn.close()
        print("✅ Migration completed successfully!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        print("\nPlease run the SQL manually in your database client:")
        print(f"  {sql_file}")


if __name__ == "__main__":
    asyncio.run(run_migration())
