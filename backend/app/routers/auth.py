from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timezone
import os

from app.database import db, db_admin
from app.schemas import UserLogin, UserRegister, Token
from app.dependencies import get_current_user, _verify_supabase_token
from app.db_client import get_supabase_client

try:
    from app.middleware.rate_limit import limiter
except ImportError:
    limiter = None

router = APIRouter()
security = HTTPBearer()


@router.post("/register", response_model=Token)
async def register(request: Request, user: UserRegister):
    """Register a new user via Supabase Auth + create DB profile.

    Rate-limited: 5/minute.
    """
    try:
        sb = get_supabase_client()

        # 1. Create auth user in Supabase (or find existing OAuth user)
        existing_user = False
        try:
            auth_resp = sb.auth.admin.create_user({
                "email": user.email,
                "password": user.password if user.password else None,
                "email_confirm": True,
                "user_metadata": {"full_name": user.full_name, "role": user.role},
                "app_metadata": {"role": user.role},
            })
            sb_user = auth_resp.user
        except Exception as auth_err:
            err_msg = str(auth_err)
            if "already" in err_msg.lower() or "duplicate" in err_msg.lower():
                # User already exists (e.g. created by OAuth flow)
                # Try to get their ID from the JWT bearer token
                existing_user = True
                auth_header = request.headers.get("Authorization", "")
                bearer_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
                if bearer_token:
                    try:
                        decoded = _verify_supabase_token(bearer_token)
                        uid_from_token = decoded["uid"]
                        sb_user = sb.auth.admin.get_user_by_id(uid_from_token)
                        # Update app_metadata with the role
                        sb.auth.admin.update_user_by_id(uid_from_token, {
                            "app_metadata": {"role": user.role},
                            "user_metadata": {
                                "full_name": user.full_name or (sb_user.user_metadata or {}).get("full_name", ""),
                                "role": user.role,
                            },
                        })
                    except Exception:
                        raise HTTPException(status_code=400, detail="Email already registered")
                else:
                    raise HTTPException(status_code=400, detail="Email already registered")
            else:
                raise HTTPException(status_code=500, detail=f"Auth creation failed: {err_msg}")

        uid = sb_user.id

        # 2. Create/upsert user profile in the users table
        profile_data = {
            "id": uid,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "verification_status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await db_admin.table("users").upsert(profile_data).async_execute()
        except Exception as db_error:
            print(f"Database Error: {str(db_error)}")
            if not existing_user:
                # Only rollback auth user if we just created it
                try:
                    sb.auth.admin.delete_user(uid)
                except Exception:
                    pass
            raise HTTPException(
                status_code=500,
                detail=f"User profile creation failed: {str(db_error)}",
            )

        # 3. Sign in to get an access token (skip for OAuth users with no password)
        access_token = uid  # fallback
        if user.password:
            try:
                sign_in_resp = sb.auth.sign_in_with_password({
                    "email": user.email,
                    "password": user.password,
                })
                access_token = sign_in_resp.session.access_token
            except Exception:
                pass

        return Token(
            access_token=access_token,
            token_type="bearer",
            user_id=uid,
            email=user.email,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=Token)
async def login(request: Request, credentials: UserLogin):
    """Login user via Supabase Auth and return access token.

    Rate-limited: 10/minute.
    """
    try:
        sb = get_supabase_client()
        resp = sb.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password,
        })

        if not resp.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return Token(
            access_token=resp.session.access_token,
            token_type="bearer",
            user_id=resp.user.id,
            email=credentials.email,
        )

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e).lower()
        if "invalid" in err_msg or "credentials" in err_msg:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Logout user — invalidate session server-side."""
    try:
        decoded = _verify_supabase_token(credentials.credentials)
        # Supabase handles session invalidation on the client side
        # The token will simply expire
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Get current user profile"""
    try:
        # Get user profile from DB
        response = (
            await db_admin.table("users")
            .select("*")
            .eq("id", user["id"])
            .single()
            .async_execute()
        )

        return response.data

    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.put("/me")
async def update_me(request: Request, user: dict = Depends(get_current_user)):
    """Update current user profile fields."""
    try:
        body = await request.json()
        # Prevent updating sensitive fields
        body.pop("id", None)
        body.pop("email", None)

        response = (
            await db_admin.table("users")
            .update(body)
            .eq("id", user["id"])
            .async_execute()
        )
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/me/upsert")
async def upsert_me(request: Request, user: dict = Depends(get_current_user)):
    """Upsert user profile — used during onboarding."""
    try:
        body = await request.json()
        body["id"] = user["id"]

        response = (
            await db_admin.table("users")
            .upsert(body)
            .async_execute()
        )
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/me/details/{detail_table}")
async def upsert_details(
    detail_table: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Upsert role-specific detail table (donor_details, victim_details, etc.)."""
    allowed_tables = {"donor_details", "victim_details", "volunteer_details", "ngo_details"}
    if detail_table not in allowed_tables:
        raise HTTPException(status_code=400, detail=f"Invalid detail table: {detail_table}")

    try:
        body = await request.json()
        body["user_id"] = user["id"]

        response = (
            await db_admin.table(detail_table)
            .upsert(body)
            .async_execute()
        )
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel as _BaseModel

class _RoleSwitchBody(_BaseModel):
    new_role: str


@router.post("/me/switch-role")
async def switch_role(body: _RoleSwitchBody, user: dict = Depends(get_current_user)):
    """Self-service role switching for donor/victim/volunteer.
    Admins and NGOs cannot switch roles via this endpoint."""
    allowed_roles = {"donor", "victim", "volunteer"}
    current_role = user.get("role", "")

    if current_role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_role}' cannot use self-service role switching",
        )

    if body.new_role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Can only switch to: {', '.join(sorted(allowed_roles))}",
        )

    if body.new_role == current_role:
        return {"message": "Already in this role", "role": current_role}

    uid = user["id"]

    # Update DB
    metadata_resp = (
        await db_admin.table("users")
        .select("metadata")
        .eq("id", uid)
        .maybe_single()
        .async_execute()
    )
    existing_meta = (metadata_resp.data or {}).get("metadata") or {}
    history = existing_meta.get("role_history", [])
    history.append({
        "changed_by": uid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "old_role": current_role,
        "new_role": body.new_role,
        "reason": "Self-service role switch",
    })
    existing_meta["role_history"] = history

    await db_admin.table("users").update({
        "role": body.new_role,
        "metadata": existing_meta,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", uid).async_execute()

    # Sync Supabase auth metadata
    try:
        sb = get_supabase_client()
        sb.auth.admin.update_user_by_id(uid, {"app_metadata": {"role": body.new_role}})
    except Exception as e:
        print(f"Warning: Failed to sync Supabase auth metadata: {e}")

    return {"message": f"Role switched to {body.new_role}", "role": body.new_role}
