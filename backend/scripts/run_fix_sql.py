import asyncio
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text

# Add parent directory to sys.path to allow imports from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env explicitly
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env")))

from app.database import engine


async def run_sql_file(filename: str):
    if not engine:
        print("Error: SQLAlchemy engine not initialized.")
        return

    # Adjust path if needed
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    sql_path = os.path.join(base_dir, "database", filename)

    if not os.path.exists(sql_path):
        print(f"Error: SQL file not found at {sql_path}")
        return

    with open(sql_path, encoding="utf-8") as f:
        sql = f.read()

    print(f"Executing SQL from {filename}...")
    try:
        async with engine.begin() as conn:
            # We use a single execute() for the whole script
            # SQLAlchemy text() can handle multiple statements if supported by the driver (asyncpg does)
            await conn.execute(text(sql))
        print("SQL executed successfully.")
    except Exception as e:
        print(f"Error executing SQL: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(run_sql_file(sys.argv[1]))
    else:
        print("Usage: python run_fix_sql.py <filename.sql>")
