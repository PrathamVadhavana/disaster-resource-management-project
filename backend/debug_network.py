import asyncio
import os
import socket
from dotenv import load_dotenv
load_dotenv()

async def debug_dns():
    url = os.getenv("SUPABASE_URL")
    print(f"URL: {url}")
    if url:
        hostname = url.split("//")[-1].split("/")[0]
        print(f"Hostname: {hostname}")
        try:
            addr = socket.getaddrinfo(hostname, 443)
            print(f"DNS Success: {addr}")
        except Exception as e:
            print(f"DNS Link Failed: {e}")

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
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_dns())
    asyncio.run(test_async_accessor())
