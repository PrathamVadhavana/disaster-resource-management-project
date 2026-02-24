import os
import json
from dotenv import load_dotenv
load_dotenv()
from app.database import supabase_admin

def check_real_constraints():
    print("Checking relationships via manual testing...")
    tests = [
        "*, victim:users!victim_id(full_name)",
        "*, victim:public_users!victim_id(full_name)",
        "*, users!victim_id(full_name)",
        "*, users!resource_requests_victim_id_fkey(full_name)",
        "*, victim:users!resource_requests_victim_id_fkey(full_name)"
    ]
    
    for t in tests:
        try:
            print(f"\nTesting select: {t}")
            res = supabase_admin.table("resource_requests").select(t).limit(1).execute()
            print(f"  SUCCESS! Data: {res.data}")
        except Exception as e:
            # Print the full structure of the error if it's a dict
            if hasattr(e, 'message'):
                print(f"  FAILED: {e.message}")
            else:
                print(f"  FAILED: {e}")

if __name__ == "__main__":
    check_real_constraints()
