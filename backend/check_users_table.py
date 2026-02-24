import os
from dotenv import load_dotenv
load_dotenv()

from app.database import supabase_admin

def check_users():
    try:
        resp = supabase_admin.table("users").select("*", count="exact").execute()
        print(f"Total users in table: {resp.count}")
        print(f"Users data: {resp.data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_users()
