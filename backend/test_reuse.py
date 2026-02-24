import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

async def test_reuse():
    from app.database import async_supabase
    
    print("Awaiting 1...")
    c1 = await async_supabase
    print(f"C1: {c1}")
    
    print("Awaiting 2...")
    c2 = await async_supabase
    print(f"C2: {c2}")
    
    assert c1 is c2
    print("SUCCESS: Proxy reused singleton correctly!")

if __name__ == "__main__":
    asyncio.run(test_reuse())
