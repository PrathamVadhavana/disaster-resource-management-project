import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

async def test_async_clients():
    from app.database import async_supabase, async_supabase_admin
    
    print("Testing async_supabase...")
    try:
        # async_supabase is a coroutine object because __getattr__ called it
        client = await async_supabase
        print(f"Got client: {client}")
    except Exception as e:
        print(f"async_supabase failed: {e}")

    print("\nTesting sync supabase_admin...")
    from app.database import supabase_admin
    try:
        res = supabase_admin.table("users").select("id").limit(1).execute()
        print(f"Success! Got {len(res.data)} users.")
    except Exception as e:
        print(f"sync shared_admin failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_async_clients())
