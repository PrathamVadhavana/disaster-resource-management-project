import os
from dotenv import load_dotenv
load_dotenv()
from app.database import supabase_admin

def test_no_join():
    print("Testing select('*') without joins...")
    try:
        res = supabase_admin.table("resource_requests").select("*", count="exact").execute()
        print(f"Success! Count: {res.count}")
        print(f"Rows: {len(res.data)}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_no_join()
