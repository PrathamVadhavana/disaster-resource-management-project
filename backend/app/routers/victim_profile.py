"""
Victim Profile Router
Profile management endpoints for victim users
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
import traceback

from app.database import supabase, supabase_admin
from app.schemas import VictimProfileUpdate

router = APIRouter()
security = HTTPBearer()


def _get_victim_id(credentials: HTTPAuthorizationCredentials) -> str:
    """Extract and verify victim user from bearer token"""
    try:
        user = supabase.auth.get_user(credentials.credentials)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


def _build_profile_dict(user_data: dict, victim_data: dict) -> dict:
    """Build a clean profile dict from user + victim_details data."""
    return {
        "id": user_data["id"],
        "email": user_data.get("email", ""),
        "full_name": user_data.get("full_name"),
        "phone": user_data.get("phone"),
        "role": str(user_data.get("role", "victim")),
        "current_status": victim_data.get("current_status"),
        "needs": victim_data.get("needs"),
        "medical_needs": victim_data.get("medical_needs"),
        "location_lat": victim_data.get("location_lat"),
        "location_long": victim_data.get("location_long"),
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
        user_resp = (
            supabase_admin.table("users")
            .select("*")
            .eq("id", victim_id)
            .single()
            .execute()
        )

        if not user_resp.data:
            raise HTTPException(status_code=404, detail="User profile not found")

        user_data = user_resp.data

        # Get victim_details if they exist
        victim_data = {}
        try:
            details_resp = (
                supabase_admin.table("victim_details")
                .select("*")
                .eq("id", victim_id)
                .single()
                .execute()
            )
            if details_resp.data:
                victim_data = details_resp.data
        except Exception:
            pass  # victim_details row may not exist yet

        return JSONResponse(content=_build_profile_dict(user_data, victim_data))
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
            supabase_admin.table("users").update(user_fields).eq("id", victim_id).execute()

        # Upsert victim_details
        if victim_fields:
            existing = None
            try:
                existing_resp = (
                    supabase_admin.table("victim_details")
                    .select("id")
                    .eq("id", victim_id)
                    .single()
                    .execute()
                )
                existing = existing_resp.data
            except Exception:
                pass

            if existing:
                supabase_admin.table("victim_details").update(victim_fields).eq("id", victim_id).execute()
            else:
                victim_fields["id"] = victim_id
                supabase_admin.table("victim_details").insert(victim_fields).execute()

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
                supabase_admin.table("victim_details")
                .select("id")
                .eq("id", victim_id)
                .single()
                .execute()
            )
            existing = existing_resp.data
        except Exception:
            pass

        if existing:
            supabase_admin.table("victim_details").update(location_data).eq("id", victim_id).execute()
        else:
            location_data["id"] = victim_id
            supabase_admin.table("victim_details").insert(location_data).execute()

        return {"message": "Location updated successfully", "latitude": latitude, "longitude": longitude}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating location: {str(e)}")
