"""
End-to-end diagnosis script for Spread Map marker pipeline.
Tests every link in the chain.
"""
import asyncio
import json
import sys
import io

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv("e:/disaster-management-system/backend/.env")

from app.database import db_admin

async def main():
    print("=" * 70)
    print("STEP 1: Raw DB query - pending/in_progress requests with coords")
    print("=" * 70)
    
    query = db_admin.table("resource_requests").select(
        "id, latitude, longitude, status, priority, resource_type, description, created_at, disaster_id, linked_disaster_id, head_count, address_text"
    )
    query = query.in_("status", ["pending", "in_progress"])
    query = query.order("created_at", desc=True).limit(1000)
    resp = await query.async_execute()
    
    all_rows = resp.data or []
    print(f"Total pending/in_progress requests: {len(all_rows)}")
    
    with_coords = [r for r in all_rows if r.get("latitude") is not None and r.get("longitude") is not None]
    without_coords = [r for r in all_rows if r.get("latitude") is None or r.get("longitude") is None]
    
    print(f"  With valid lat/lon:    {len(with_coords)}")
    print(f"  Without lat/lon:       {len(without_coords)}")
    
    for r in with_coords[:10]:
        did = r.get('disaster_id')
        lid = r.get('linked_disaster_id')
        print(f"  OK {r['id'][:8]} | {r['status']:12s} | {r['resource_type']:15s} | {r['priority']:8s} | ({r['latitude']:.4f}, {r['longitude']:.4f}) | D:{did[:8] if did else 'None':8s} | LD:{lid[:8] if lid else 'None':8s}")
    
    print()
    print("=" * 70)
    print("STEP 2: Simulating backend victim_markers generation")
    print("=" * 70)
    
    hotspots = []
    victim_markers = []
    for r in all_rows:
        r_lat = r.get("latitude")
        r_lon = r.get("longitude")
        if r_lat is None or r_lon is None:
            continue
        try:
            lat_f, lon_f = float(r_lat), float(r_lon)
            marker = {
                "id": r.get("id"),
                "latitude": lat_f,
                "longitude": lon_f,
                "priority": r.get("priority", "medium"),
                "resource_type": r.get("resource_type", "other"),
                "status": r.get("status", "pending"),
                "description": (r.get("description") or "")[:100],
                "head_count": int(r.get("head_count") or 1),
                "disaster_id": r.get("disaster_id"),
            }
            hotspots.append((lat_f, lon_f))
            victim_markers.append(marker)
        except (ValueError, TypeError) as e:
            print(f"  ERROR processing {r['id'][:8]}: {e}")
    
    print(f"Generated victim_markers: {len(victim_markers)}")
    for m in victim_markers[:5]:
        print(f"  PIN {m['id'][:8]} | {m['resource_type']:15s} | ({m['latitude']:.4f}, {m['longitude']:.4f}) | head_count={m['head_count']}")
    
    print()
    print("=" * 70)
    print("STEP 3: Check resource_requests columns")
    print("=" * 70)
    
    sample = await db_admin.table("resource_requests").select("*").limit(1).async_execute()
    if sample.data:
        cols = list(sample.data[0].keys())
        print(f"Columns ({len(cols)}):")
        for c in sorted(cols):
            print(f"  - {c}: {type(sample.data[0][c]).__name__} = {repr(sample.data[0][c])[:60]}")
        print(f"\n  'head_count' in columns: {'head_count' in cols}")
        print(f"  'people_count' in columns: {'people_count' in cols}")
        print(f"  'disaster_id' in columns: {'disaster_id' in cols}")
        print(f"  'linked_disaster_id' in columns: {'linked_disaster_id' in cols}")
    
    print()
    print("=" * 70)
    print("DIAGNOSIS SUMMARY")
    print("=" * 70)
    
    if len(victim_markers) > 0:
        print(f"[OK] Backend WILL generate {len(victim_markers)} victim_markers with data")
    else:
        print("[FAIL] Backend will generate 0 victim_markers!")
        
    # Check if head_count column exists
    if sample.data and 'head_count' not in sample.data[0]:
        print("[FAIL] 'head_count' column does NOT exist in resource_requests!")
        print("       The backend tries to read it but gets None, defaulting to 1.")
        print("       This is not fatal but indicates the column may need to be added.")

if __name__ == "__main__":
    asyncio.run(main())
