from fastapi import APIRouter, Depends, HTTPException, Query
from app.dependencies import require_admin, require_ngo, require_role
from app.database import db_admin
from app.core.query_cache import (
    cache_get as mem_cache_get,
    cache_set as mem_cache_set,
    TTL_SHORT,
    TTL_MEDIUM,
)
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import traceback
import csv
import io
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/analytics", tags=["Analytics & Reporting"])

@router.get("/summary", response_model=Dict[str, Any])
async def get_platform_summary(user=Depends(require_role("admin", "ngo"))):
    """
    Get a high-level summary of platform activity across all roles.
    Accessible by Admin and NGOs.
    """
    try:
        # Check in-memory cache first (2 min TTL for summary stats)
        _cache_key = "analytics:platform_summary"
        cached = mem_cache_get(_cache_key)
        if cached is not None:
            return cached

        # 1. Total active disasters
        disasters_resp = await db_admin.table("disasters").select("id", count="exact").eq("status", "active").limit(1000).async_execute()
        active_disasters = disasters_resp.count or 0
        
        # 2. Total resource requests (all time vs pending)
        requests_resp = await db_admin.table("resource_requests").select("id, status").limit(5000).async_execute()
        requests = requests_resp.data or []
        total_requests = len(requests)
        pending_requests = len([r for r in requests if r["status"] == "pending"])
        fulfilled_requests = len([r for r in requests if r["status"] in ("completed", "delivered", "satisfied")])

        # 3. Verification stats
        verif_resp = await db_admin.table("request_verifications").select("verification_status").limit(5000).async_execute()
        verifs = verif_resp.data or []
        trusted_count = len([v for v in verifs if v["verification_status"] == "trusted"])
        false_alarms = len([v for v in verifs if v["verification_status"] == "false_alarm"])

        # 4. Donor involvement
        pledges_resp = await db_admin.table("donor_pledges").select("quantity_pledged").limit(5000).async_execute()
        pledges = pledges_resp.data or []
        total_units_pledged = sum([p["quantity_pledged"] for p in pledges])

        # 5. Volunteer mobilization
        mobilization_resp = await db_admin.table("ngo_mobilization").select("id", count="exact").limit(1000).async_execute()
        total_missions = mobilization_resp.count or 0

        return {
            "disasters": {
                "active": active_disasters,
            },
            "requests": {
                "total": total_requests,
                "pending": pending_requests,
                "fulfilled": fulfilled_requests,
                "fulfillment_rate": round(fulfilled_requests / total_requests * 100, 1) if total_requests > 0 else 0
            },
            "verifications": {
                "total": len(verifs),
                "trusted_rate": round(trusted_count / len(verifs) * 100, 1) if verifs else 0,
                "false_alarm_rate": round(false_alarms / len(verifs) * 100, 1) if verifs else 0
            },
            "donations": {
                "units_pledged": total_units_pledged,
                "active_pledges": len(pledges)
            },
            "mobilization": {
                "total_missions": total_missions
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        mem_cache_set(_cache_key, result, TTL_MEDIUM)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/volunteer-performance")
async def get_volunteer_analytics(user=Depends(require_admin)):
    """
    Get volunteer performance metrics. Admin only.
    """
    try:
        # Join verifications with users to see who is active
        # Aggregate in Python for simplicity
        verif_resp = await db_admin.table("request_verifications").select("volunteer_id, verification_status").limit(5000).async_execute()
        verifs = verif_resp.data or []
        
        volunteer_stats = {}
        for v in verifs:
            vid = v["volunteer_id"]
            if vid not in volunteer_stats:
                volunteer_stats[vid] = {"total_verifs": 0, "trusted": 0, "false_alarm": 0, "dubious": 0}
            
            volunteer_stats[vid]["total_verifs"] += 1
            status = v["verification_status"]
            if status in volunteer_stats[vid]:
                volunteer_stats[vid][status] += 1
        
        # Get user names for the top performers
        if not volunteer_stats:
            return []
            
        user_ids = list(volunteer_stats.keys())[:50] # Limit to 50
        users_resp = await db_admin.table("users").select("id, full_name, email").in_("id", user_ids).async_execute()
        user_map = {u["id"]: u for u in (users_resp.data or [])}
        
        result = []
        for vid, stats in volunteer_stats.items():
            u = user_map.get(vid, {"full_name": "Unknown", "email": "N/A"})
            result.append({
                "volunteer_id": vid,
                "name": u["full_name"],
                "email": u["email"],
                **stats,
                "accuracy": round(stats["trusted"] / stats["total_verifs"] * 100, 1) if stats["total_verifs"] > 0 else 0
            })
            
        # Sort by total verifications
        result.sort(key=lambda x: x["total_verifs"], reverse=True)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resource-burn-rate")
async def get_resource_burn_rate(days: int = Query(30, ge=1, le=365), user=Depends(require_role("admin", "ngo"))):
    """
    Calculate how fast resources are being requested vs satisfied.
    """
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Get requests created in the window
        req_resp = await db_admin.table("resource_requests").select("created_at, resource_type, quantity, status").gte("created_at", since).limit(5000).async_execute()
        reqs = req_resp.data or []
        
        # Group by day
        daily_stats = {}
        for r in reqs:
            day = r["created_at"][:10]
            if day not in daily_stats:
                daily_stats[day] = {"date": day, "requested": 0, "fulfilled": 0}
            
            daily_stats[day]["requested"] += r.get("quantity", 1)
            if r["status"] in ("completed", "delivered", "satisfied"):
                daily_stats[day]["fulfilled"] += r.get("quantity", 1)
                
        return sorted(daily_stats.values(), key=lambda x: x["date"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/geospatial-impact")
async def get_geospatial_impact(user=Depends(require_admin)):
    """
    Get density of requests for mapping/heatmap.
    """
    try:
        resp = await db_admin.table("resource_requests").select("id, latitude, longitude, resource_type, priority, status").not_.is_("latitude", "null").limit(2000).async_execute()
        data = resp.data or []
        
        # Optional: bucket by simple grid for performance if data is huge
        # For now, return raw points
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export/interactivity")
async def export_interactivity_data(
    table: str = Query(..., pattern="^(verifications|pledges|missions|pulse)$"),
    admin=Depends(require_admin)
):
    """
    Export the new Phase 6 interactivity tables as CSV.
    """
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        if table == "verifications":
            resp = await db_admin.table("request_verifications").select("*").order("created_at", desc=True).limit(5000).async_execute()
            rows = resp.data or []
            writer.writerow(["ID", "Request ID", "Volunteer ID", "Status", "Notes", "Lat", "Long", "Created At"])
            for r in rows:
                writer.writerow([r.get("id"), r.get("request_id"), r.get("volunteer_id"), r.get("verification_status"), 
                               r.get("field_notes"), r.get("latitude_at_verification"), r.get("longitude_at_verification"), r.get("created_at")])
        
        elif table == "pledges":
            resp = await db_admin.table("donor_pledges").select("*").order("created_at", desc=True).limit(5000).async_execute()
            rows = resp.data or []
            writer.writerow(["ID", "Request ID", "Donor ID", "Quantity", "Status", "Created At"])
            for r in rows:
                writer.writerow([r.get("id"), r.get("sourcing_request_id"), r.get("donor_id"), r.get("quantity_pledged"), 
                               r.get("status"), r.get("created_at")])
                               
        elif table == "missions":
            resp = await db_admin.table("ngo_mobilization").select("*").order("created_at", desc=True).limit(5000).async_execute()
            rows = resp.data or []
            writer.writerow(["ID", "NGO ID", "Title", "Required Vols", "Status", "Created At"])
            for r in rows:
                writer.writerow([r.get("id"), r.get("ngo_id"), r.get("title"), r.get("required_volunteers"), 
                               r.get("status"), r.get("created_at")])
                               
        elif table == "pulse":
            resp = await db_admin.table("operational_pulse").select("*").order("created_at", desc=True).limit(2000).async_execute()
            rows = resp.data or []
            writer.writerow(["ID", "Actor ID", "Action", "Description", "Created At"])
            for r in rows:
                writer.writerow([r.get("id"), r.get("actor_id"), r.get("action_type"), r.get("description"), r.get("created_at")])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={table}_export_{datetime.now().strftime('%Y%m%d')}.csv"},
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
