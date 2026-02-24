import os
import json
from dotenv import load_dotenv
load_dotenv()
from app.database import supabase_admin

def test_admin_query():
    print("Testing Admin Requests Query...")
    try:
        # This is exactly what's in admin.py now
        query = (
            supabase_admin.table("resource_requests")
            .select("*, victim:users!victim_id(full_name, email), assigned_user:users!assigned_to(full_name, email, metadata)", count="exact")
        )
        response = query.execute()
        print(f"Status Code: 200 (Success)")
        print(f"Total Count: {response.count}")
        print(f"Data Length: {len(response.data) if response.data else 0}")
        if response.data:
            print(f"Sample Row: {json.dumps(response.data[0], indent=2)}")
        else:
            print("No data returned!")

        # Try without the forced join hint to see if it makes a difference
        print("\nTesting Query without join hints...")
        query2 = (
            supabase_admin.table("resource_requests")
            .select("*, victim:users(full_name), assigned_user:users(full_name)", count="exact")
        )
        response2 = query2.execute()
        print(f"Total Count: {response2.count}")
        
    except Exception as e:
        print(f"Query Failed: {e}")

if __name__ == "__main__":
    test_admin_query()
