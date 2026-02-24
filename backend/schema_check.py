import asyncio
import json
from app.database import supabase_admin

async def main():
    try:
        resp = supabase_admin.table('volunteer_certifications').select('id').limit(1).execute()
        print("Volunteer certifications exists")
    except Exception as e:
        print("Certs error:", e)

    try:
        resp2 = supabase_admin.table('messages').select('id').limit(1).execute()
        print("Messages exists")
    except Exception as e:
        print("Messages error:", e)

    try:
        resp3 = supabase_admin.table('donations').select('*').limit(1).execute()
        print("Donations columns:", resp3.data[0].keys() if resp3.data else "No rows")
    except Exception as e:
        print("Donations error:", e)

asyncio.run(main())
