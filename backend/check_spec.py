import os
from dotenv import load_dotenv
load_dotenv()
from app.database import supabase_admin

def get_constraints():
    # Attempting to use the Supabase REST API to see the OpenAPI spec which contains relationships
    import requests
    url = os.getenv("SUPABASE_URL") + "/rest/v1/"
    headers = {
        "apikey": os.getenv("SUPABASE_SERVICE_KEY"),
        "Authorization": "Bearer " + os.getenv("SUPABASE_SERVICE_KEY")
    }
    
    try:
        print(f"Fetching OpenAPI spec from {url}...")
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            spec = resp.json()
            # Look for resource_requests
            definitions = spec.get("definitions", {})
            req_def = definitions.get("resource_requests", {})
            print("Resource Requests Definition found.")
            
            # Relationships are often described in the paths or info
            # PostgREST 12+ has a better way, but let's just look at what we have.
            
            # Let's try to find potential foreign keys in the description if any
            print(f"Description: {req_def.get('description', 'No description')}")
            
        else:
            print(f"Failed to fetch spec: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_constraints()
