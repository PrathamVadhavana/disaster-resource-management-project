import asyncio
import sys
import os

# Ensure the app is in the path
sys.path.append(os.getcwd())

from app.database import db_admin

async def main():
    try:
        resp = await db_admin.table('disasters').select('*').execute()
        print(f"Total Disasters: {len(resp.data)}")
        for d in resp.data:
            print(f"ID: {d.get('id')}, Title: {d.get('title')}, Type: {d.get('type')}, Status: {d.get('status')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
