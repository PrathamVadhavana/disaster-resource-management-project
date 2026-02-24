import requests
import os
from dotenv import load_dotenv
load_dotenv()

def test_users_api():
    url = "http://localhost:8000/api/admin/users"
    # We need a token. Let's use the service key to simulate auth or bypass it if we can.
    # Actually, let's just use the direct database if we want to check if the route works.
    # But he wants to know why it's slow/loading.
    
    print(f"Calling {url}...")
    # We need a real admin token to test this via HTTP.
    # Let's try to just call the function in a script.
    pass

if __name__ == "__main__":
    import asyncio
    from app.routers.admin import list_users
    
    async def run():
        try:
            print("Calling list_users() function directly...")
            # Mock the dependency
            users = await list_users(admin={"role": "admin"})
            print(f"Success! Got {len(users)} users.")
        except Exception as e:
            print(f"Error: {e}")

    asyncio.run(run())
