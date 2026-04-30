import asyncio
import os
from dotenv import load_dotenv

load_dotenv("e:/disaster-management-system/backend/.env")

from app.database import db_admin

async def main():
    query = db_admin.table("resource_requests").select(
        "id, latitude, longitude, status, priority, resource_type, description, created_at, disaster_id, linked_disaster_id, head_count, address_text"
    )
    query = query.order("created_at", desc=True).limit(1000)
    query = query.in_("status", ["pending", "in_progress"])
    resp = await query.async_execute()
    
    print(f"Total returned: {len(resp.data)}")
    for r in resp.data[:5]:
        print(f"ID: {r['id'][:8]} | Status: {r['status']} | Type: {r['resource_type']} | Lat: {r['latitude']} | Lon: {r['longitude']}")

if __name__ == "__main__":
    asyncio.run(main())
