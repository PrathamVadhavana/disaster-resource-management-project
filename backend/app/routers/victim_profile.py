"""
Victim Profile Router
Profile management endpoints for victim users
"""

import traceback
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import db_admin
from app.dependencies import _verify_supabase_token
from app.schemas import VictimProfileUpdate

router = APIRouter()
security = HTTPBearer()


async def _compute_victim_ai_insights(victim_id: str, victim_data: dict) -> dict:
    """Compute AI risk score and recommendations for a victim."""
    risk_score = 0.0
    recommendations = []

    try:
        # Factor 1: Medical needs
        medical_needs = victim_data.get("medical_needs")
        if medical_needs:
            risk_score += 0.3
            recommendations.append("Medical needs identified — prioritize medical resource allocation")

        # Factor 2: Current status
        current_status = victim_data.get("current_status", "").lower()
        if current_status in ("critical", "urgent", "emergency"):
            risk_score += 0.4
            recommendations.append("Victim status is critical — immediate attention required")
        elif current_status in ("displaced", "evacuated"):
            risk_score += 0.2
            recommendations.append("Victim is displaced — shelter and essential supplies needed")

        # Factor 3: Number of unmet needs
        needs = victim_data.get("needs") or []
        if len(needs) > 3:
            risk_score += 0.2
            recommendations.append(f"Multiple unmet needs ({len(needs)}) — coordinate comprehensive support")

        # Factor 4: Check for pending/urgent requests
        try:
            req_resp = (
                await db_admin.table("resource_requests")
                .select("priority, status")
                .eq("victim_id", victim_id)
                .in_("status", ["pending", "approved", "under_review"])
                .async_execute()
            )
            pending_requests = req_resp.data or []
            critical_requests = [r for r in pending_requests if r.get("priority") == "critical"]
            if critical_requests:
                risk_score += 0.3
                recommendations.append(f"{len(critical_requests)} critical resource request(s) pending")
            elif len(pending_requests) > 2:
                risk_score += 0.1
                recommendations.append("Multiple pending requests — monitor fulfillment progress")
        except Exception:
            pass

        # Factor 5: Check linked disaster severity
        disaster_id = victim_data.get("disaster_id")
        if disaster_id:
            try:
                disaster_resp = (
                    await db_admin.table("disasters")
                    .select("severity, status")
                    .eq("id", disaster_id)
                    .maybe_single()
                    .async_execute()
                )
                if disaster_resp.data:
                    severity = disaster_resp.data.get("severity", "medium")
                    if severity == "critical":
                        risk_score += 0.3
                        recommendations.append("Located in critical severity disaster zone — high priority")
                    elif severity == "high":
                        risk_score += 0.2
                        recommendations.append("Located in high severity disaster zone")
            except Exception:
                pass

        # Cap risk score at 1.0
        risk_score = min(risk_score, 1.0)

        # Add general recommendations if score is high
        if risk_score >= 0.7 and not recommendations:
            recommendations.append("High risk profile — consider priority resource allocation")

    except Exception as e:
        print(f"⚠️  AI insights computation failed: {e}")

    return {
        "ai_risk_score": round(risk_score, 2),
        "ai_recommendations": recommendations if recommendations else ["No immediate concerns detected"],
    }


def _get_victim_id(credentials: HTTPAuthorizationCredentials) -> str:
    """Extract and verify victim user from Supabase bearer token"""
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        return decoded["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


async def _build_profile_dict(user_data: dict, victim_data: dict) -> dict:
    """Build a clean profile dict from user + victim_details data, including disaster linking and AI insights."""
    victim_id = user_data["id"]
    
    # Get disaster linking info
    disaster_id = victim_data.get("disaster_id")
    disaster_name = None
    disaster_type = None
    disaster_severity = None
    disaster_status = None
    
    if disaster_id:
        try:
            disaster_resp = (
                await db_admin.table("disasters")
                .select("title, type, severity, status")
                .eq("id", disaster_id)
                .maybe_single()
                .async_execute()
            )
            if disaster_resp.data:
                disaster_name = disaster_resp.data.get("title")
                disaster_type = disaster_resp.data.get("type")
                disaster_severity = disaster_resp.data.get("severity")
                disaster_status = disaster_resp.data.get("status")
        except Exception:
            pass
    
    # Auto-link to nearest disaster if no disaster linked yet
    if not disaster_id and victim_data.get("location_lat") and victim_data.get("location_long"):
        try:
            from app.services.disaster_linking_service import find_matching_disaster
            match = await find_matching_disaster(
                victim_data["location_lat"],
                victim_data["location_long"],
                datetime.now(UTC).isoformat(),
            )
            if match:
                disaster_id = match["disaster_id"]
                disaster_name = match.get("disaster_title")
                disaster_type = match.get("disaster_type")
                disaster_severity = match.get("disaster_severity")
                # Store the link
                try:
                    existing = None
                    try:
                        existing_resp = (
                            await db_admin.table("victim_details").select("id").eq("id", victim_id).single().async_execute()
                        )
                        existing = existing_resp.data
                    except Exception:
                        pass
                    if existing:
                        await db_admin.table("victim_details").update({"disaster_id": disaster_id}).eq("id", victim_id).async_execute()
                    else:
                        await db_admin.table("victim_details").insert({"id": victim_id, "disaster_id": disaster_id}).async_execute()
                except Exception:
                    pass
        except Exception:
            pass
    
    # Compute AI insights
    ai_insights = await _compute_victim_ai_insights(victim_id, {**victim_data, "disaster_id": disaster_id})
    
    return {
        "id": victim_id,
        "email": user_data.get("email", ""),
        "full_name": user_data.get("full_name"),
        "phone": user_data.get("phone"),
        "role": str(user_data.get("role", "victim")),
        "current_status": victim_data.get("current_status"),
        "needs": victim_data.get("needs"),
        "medical_needs": victim_data.get("medical_needs"),
        "location_lat": victim_data.get("location_lat"),
        "location_long": victim_data.get("location_long"),
        # Disaster linking
        "disaster_id": disaster_id,
        "disaster_name": disaster_name,
        "disaster_type": disaster_type,
        "disaster_severity": disaster_severity,
        "disaster_status": disaster_status,
        # AI insights
        "ai_risk_score": ai_insights["ai_risk_score"],
        "ai_recommendations": ai_insights["ai_recommendations"],
        "created_at": str(user_data.get("created_at", "")),
        "updated_at": str(user_data.get("updated_at", "")),
    }


@router.get("/profile")
async def get_victim_profile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get the authenticated victim's combined profile (users + victim_details)"""
    victim_id = _get_victim_id(credentials)

    try:
        user_resp = await db_admin.table("users").select("*").eq("id", victim_id).single().async_execute()

        if not user_resp.data:
            raise HTTPException(status_code=404, detail="User profile not found")

        user_data = user_resp.data

        # Get victim_details if they exist
        victim_data = {}
        try:
            details_resp = (
                await db_admin.table("victim_details").select("*").eq("id", victim_id).single().async_execute()
            )
            if details_resp.data:
                victim_data = details_resp.data
        except Exception:
            pass  # victim_details row may not exist yet

        profile = await _build_profile_dict(user_data, victim_data)
        return JSONResponse(content=profile)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PROFILE GET ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching profile: {str(e)}")


@router.put("/profile")
async def update_victim_profile(
    update_data: VictimProfileUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Update the victim's profile information"""
    victim_id = _get_victim_id(credentials)

    try:
        user_fields = {}
        victim_fields = {}

        update_dict = update_data.model_dump(exclude_unset=True)

        user_field_keys = {"full_name", "phone"}
        victim_field_keys = {"current_status", "needs", "medical_needs", "location_lat", "location_long"}

        for key, value in update_dict.items():
            if key in user_field_keys and value is not None:
                user_fields[key] = value
            elif key in victim_field_keys and value is not None:
                victim_fields[key] = value

        # Update users table
        if user_fields:
            await db_admin.table("users").update(user_fields).eq("id", victim_id).async_execute()

        # Upsert victim_details
        if victim_fields:
            existing = None
            try:
                existing_resp = (
                    await db_admin.table("victim_details").select("id").eq("id", victim_id).single().async_execute()
                )
                existing = existing_resp.data
            except Exception:
                pass

            if existing:
                await db_admin.table("victim_details").update(victim_fields).eq("id", victim_id).async_execute()
            else:
                victim_fields["id"] = victim_id
                await db_admin.table("victim_details").insert(victim_fields).async_execute()

        # Return updated profile
        return await get_victim_profile(credentials)
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PROFILE UPDATE ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating profile: {str(e)}")


@router.put("/profile/location")
async def update_victim_location(
    latitude: float,
    longitude: float,
    address: str = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Update the victim's location"""
    victim_id = _get_victim_id(credentials)

    try:
        location_data = {
            "location_lat": latitude,
            "location_long": longitude,
        }

        existing = None
        try:
            existing_resp = (
                await db_admin.table("victim_details").select("id").eq("id", victim_id).single().async_execute()
            )
            existing = existing_resp.data
        except Exception:
            pass

        if existing:
            await db_admin.table("victim_details").update(location_data).eq("id", victim_id).async_execute()
        else:
            location_data["id"] = victim_id
            await db_admin.table("victim_details").insert(location_data).async_execute()

        return {"message": "Location updated successfully", "latitude": latitude, "longitude": longitude}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating location: {str(e)}")
