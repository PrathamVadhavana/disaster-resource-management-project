import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

async def test_async_accessor():
    from app.database import async_supabase
    print("Awaiting async_supabase...")
    try:
        client = await async_supabase
        print(f"Got client: {client}")
        # Test a query
        res = await client.table("users").select("id").limit(1).execute()
        print(f"Query success: {res.data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_async_accessor())
