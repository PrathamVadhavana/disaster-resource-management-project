import asyncio
import os
import sys
from sqlalchemy import text
from dotenv import load_dotenv

# Add parent directory to sys.path to allow imports from app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load .env explicitly
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../.env')))

from app.database import engine

async def inspect_constraints():
    if not engine:
        print("Error: SQLAlchemy engine not initialized.")
        return

    with open('inspection_results.txt', 'w') as f:
        async with engine.connect() as conn:
            f.write("--- Inspection of ngo_details ---\n")
            query = text("""
                SELECT tc.constraint_name, cc.check_clause
                FROM information_schema.table_constraints tc
                JOIN information_schema.check_constraints cc 
                  ON tc.constraint_name = cc.constraint_name
                WHERE tc.table_name = 'ngo_details'
                  AND tc.table_schema = 'public';
            """)
            result = await conn.execute(query)
            for row in result:
                f.write(f"Check Constraint: {row[0]} -> {row[1]}\n")
                
            f.write("\n--- Inspection of donor_details ---\n")
            result = await conn.execute(text("""
                SELECT tc.constraint_name, cc.check_clause
                FROM information_schema.table_constraints tc
                JOIN information_schema.check_constraints cc 
                  ON tc.constraint_name = cc.constraint_name
                WHERE tc.table_name = 'donor_details'
                  AND tc.table_schema = 'public';
            """))
            for row in result:
                f.write(f"Check Constraint: {row[0]} -> {row[1]}\n")
    print("Results written to inspection_results.txt")

if __name__ == "__main__":
    asyncio.run(inspect_constraints())
