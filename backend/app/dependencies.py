"""
Centralized dependencies for the Disaster Management API.

Provides reusable auth helpers so every router doesn't need its own
copy of _get_user_id / _require_admin / _require_role.
"""

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List
from app.database import supabase, supabase_admin, async_supabase, async_supabase_admin

# Global ML service instance
ml_service = None

security = HTTPBearer()


def set_ml_service(service):
    """Set the global ML service instance (called at startup)."""
    global ml_service
    ml_service = service


def get_ml_service():
    """Get ML service dependency"""
    if ml_service is None:
        raise HTTPException(status_code=503, detail="ML service not initialized")
    return ml_service


# ── Auth helpers ──────────────────────────────────────────────────────────────


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Extract and verify user from bearer token. Returns user ID."""
    try:
        client = await async_supabase
        resp = await client.auth.get_user(credentials.credentials)
        if not resp or not resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return str(resp.user.id)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Extract and verify user from bearer token. Returns full user dict."""
    try:
        client = await async_supabase
        resp = await client.auth.get_user(credentials.credentials)
        if not resp or not resp.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        user = resp.user
        return {
            "id": str(user.id),
            "email": user.email,
            "role": (user.user_metadata or {}).get("role"),
            "metadata": user.user_metadata or {},
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Auth error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


def require_role(*allowed_roles: str):
    """
    FastAPI dependency factory that checks the user has one of the allowed roles.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        async def admin_only_endpoint(): ...

    """

    async def _check(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> dict:
        try:
            client = await async_supabase
            resp = await client.auth.get_user(credentials.credentials)
            if not resp or not resp.user:
                raise HTTPException(status_code=401, detail="Invalid token")
            user = resp.user
            role = (user.user_metadata or {}).get("role")
            additional_roles = (user.user_metadata or {}).get("additional_roles", [])

            # Fallback: if JWT metadata has no role, look it up from the users table
            if not role:
                try:
                    db_resp = (
                        supabase_admin.table("users")
                        .select("role, additional_roles")
                        .eq("id", str(user.id))
                        .maybe_single()
                        .execute()
                    )
                    if db_resp.data:
                        role = db_resp.data.get("role")
                        db_additional = db_resp.data.get("additional_roles") or []
                        if isinstance(db_additional, list):
                            additional_roles = db_additional
                except Exception as db_err:
                    print(f"DB role lookup fallback error: {db_err}")

            user_roles = [role] + (
                additional_roles if isinstance(additional_roles, list) else []
            )

            if not any(r in allowed_roles for r in user_roles):
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied. Required role: {', '.join(allowed_roles)}. Your roles: {user_roles}",
                )
            return {
                "id": str(user.id),
                "email": user.email,
                "role": role,
                "roles": user_roles,
                "metadata": user.user_metadata or {},
            }
        except HTTPException:
            raise
        except Exception as e:
            print(f"Auth role check error: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")

    return _check


# Convenience shortcuts for common role checks
require_admin = require_role("admin")
require_ngo = require_role("admin", "ngo")
require_donor = require_role("admin", "donor")
require_volunteer = require_role("admin", "volunteer")
require_victim = require_role("admin", "victim")


def require_verified_role(*allowed_roles: str):
    """
    Checks if the user has one of the allowed roles AND is verified.
    """

    async def _check(
        user: dict = Depends(require_role(*allowed_roles)),
    ) -> dict:
        # Check metadata for verification_status
        # In this system, we store it in metadata or the specialized table.
        # Let's assume for now it's in the user's main metadata for quick checks.
        status = user.get("metadata", {}).get("verification_status", "pending")

        # Admin is always 'verified' implicitly for this check
        if user.get("role") == "admin":
            return user

        if status != "verified":
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Your account (role: {user.get('role')}) is currently '{status}'. Verification from an admin is required.",
            )
        return user

    return _check


require_verified_ngo = require_verified_role("admin", "ngo")
require_verified_donor = require_verified_role("admin", "donor")
require_verified_volunteer = require_verified_role("admin", "volunteer")
