import logging
import os
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database import db_admin
from app.db_client import get_supabase_client
from app.dependencies import _verify_supabase_token, get_current_user
from app.schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserLogin,
    UserRegister,
    EmailVerificationResponse,
)

try:
    from app.middleware.rate_limit import limiter
except ImportError:
    limiter = None

logger = logging.getLogger(__name__)

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
        user_created = False
        try:
            auth_resp = sb.auth.admin.create_user(
                {
                    "email": user.email,
                    "password": user.password if user.password else None,
                    "email_confirm": False,
                    "user_metadata": {"full_name": user.full_name, "role": user.role},
                    "app_metadata": {"role": user.role},
                }
            )
            sb_user = auth_resp.user
            user_created = True
        except Exception as auth_err:
            err_msg = str(auth_err)
            if "already" in err_msg.lower() or "duplicate" in err_msg.lower():
                # User already exists (e.g. created by OAuth flow)
                # Try to get their ID from the JWT bearer token
                existing_user = True
                auth_header = request.headers.get("Authorization", "")
                bearer_token = (
                    auth_header.replace("Bearer ", "")
                    if auth_header.startswith("Bearer ")
                    else ""
                )
                if bearer_token:
                    try:
                        decoded = _verify_supabase_token(bearer_token)
                        uid_from_token = decoded["uid"]
                        sb_user = sb.auth.admin.get_user_by_id(uid_from_token)
                        # Update app_metadata with the role
                        sb.auth.admin.update_user_by_id(
                            uid_from_token,
                            {
                                "app_metadata": {"role": user.role},
                                "user_metadata": {
                                    "full_name": user.full_name
                                    or (sb_user.user_metadata or {}).get(
                                        "full_name", ""
                                    ),
                                    "role": user.role,
                                },
                            },
                        )
                    except Exception:
                        raise HTTPException(
                            status_code=400, detail="Email already registered"
                        )
                else:
                    raise HTTPException(
                        status_code=400, detail="Email already registered"
                    )
            else:
                raise HTTPException(
                    status_code=500, detail=f"Auth creation failed: {err_msg}"
                )

        # 2. Send verification email for newly created users
        # Always try to send verification email (Supabase handles duplicates gracefully)
        try:
            allowed_origins = _parse_allowed_origins()
            default_origin = (
                allowed_origins[0] if allowed_origins else "http://localhost:3000"
            )
            request_origin = (request.headers.get("origin") or "").strip().rstrip("/")
            if request_origin and request_origin in allowed_origins:
                default_origin = request_origin

            redirect_url = f"{default_origin}/auth/callback"

            sb.auth.resend(
                {
                    "type": "signup",
                    "email": user.email,
                    "redirect_to": redirect_url,
                }
            )
            logger.info(
                "Verification email sent for email (hash: %s)", hash(user.email)
            )
        except Exception as e:
            logger.warning(f"Failed to send verification email: {e}")

        uid = sb_user.id

        # 2. Create/upsert user profile in the users table
        profile_data = {
            "id": uid,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "verification_status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
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
                sign_in_resp = sb.auth.sign_in_with_password(
                    {
                        "email": user.email,
                        "password": user.password,
                    }
                )
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
        resp = sb.auth.sign_in_with_password(
            {
                "email": credentials.email,
                "password": credentials.password,
            }
        )

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
        _verify_supabase_token(credentials.credentials)
        # Supabase handles session invalidation on the client side
        # The token will simply expire
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Get current user profile, merged with role-specific details."""
    try:
        # Get user profile from DB
        response = (
            await db_admin.table("users")
            .select("*")
            .eq("id", user["id"])
            .single()
            .async_execute()
        )

        profile = response.data or {}
        role = profile.get("role", "")

        # Merge role-specific details into the profile
        detail_table_map = {
            "ngo": "ngo_details",
            "donor": "donor_details",
            "volunteer": "volunteer_details",
            "victim": "victim_details",
        }
        detail_table = detail_table_map.get(role)
        if detail_table:
            try:
                detail_resp = (
                    await db_admin.table(detail_table)
                    .select("*")
                    .eq("id", user["id"])
                    .maybe_single()
                    .async_execute()
                )
                if detail_resp.data:
                    detail_data = detail_resp.data
                    # Don't overwrite id/created_at/updated_at from details
                    detail_data.pop("id", None)
                    detail_data.pop("created_at", None)
                    detail_data.pop("updated_at", None)
                    profile.update(detail_data)
            except Exception as e:
                logger.warning(f"Failed to load {detail_table}: {e}")

        return profile

    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.put("/me")
async def update_me(request: Request, user: dict = Depends(get_current_user)):
    """Update current user profile fields.

    Splits incoming data between the `users` table and role-specific
    detail tables (e.g. `ngo_details`) so that all fields persist
    correctly.
    """
    try:
        body = await request.json()
        # Prevent updating sensitive fields
        body.pop("id", None)
        body.pop("email", None)
        body.pop("role", None)
        body.pop("additional_roles", None)
        body.pop("verification_status", None)
        body.pop("verification_notes", None)
        body.pop("metadata", None)

        uid = user["id"]

        # Determine if there are role-specific fields to save
        ngo_fields = {
            "organization_name", "registration_number", "operating_sectors",
            "website", "phone_number", "address", "latitude", "longitude",
        }

        # Get current user role
        role = user.get("role", "")

        # Split NGO-specific fields out of the users update
        ngo_data = {}
        if role == "ngo":
            for f in list(body.keys()):
                if f in ngo_fields:
                    ngo_data[f] = body.pop(f)

        # Update users table (only if there are remaining fields)
        result_data = {}
        if body:
            body["updated_at"] = datetime.now(UTC).isoformat()
            response = (
                await db_admin.table("users")
                .update(body)
                .eq("id", uid)
                .async_execute()
            )
            result_data = response.data[0] if response.data else {}

        # Upsert role-specific details
        if role == "ngo" and ngo_data:
            ngo_data["id"] = uid
            ngo_data["updated_at"] = datetime.now(UTC).isoformat()
            try:
                await db_admin.table("ngo_details").upsert(ngo_data).async_execute()
            except Exception as e:
                logger.warning(f"Failed to update ngo_details: {e}")

        # Return merged profile
        return await me(user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/me/upsert")
async def upsert_me(request: Request, user: dict = Depends(get_current_user)):
    """Upsert user profile — used during onboarding."""
    try:
        body = await request.json()
        # Prevent upsert from mutating auth-sensitive fields.
        # Role IS allowed here (onboarding sets the chosen role) but 'admin'
        # can never be self-assigned.
        if body.get("role") == "admin":
            body.pop("role", None)
        body.pop("additional_roles", None)
        body.pop("verification_status", None)
        body.pop("verification_notes", None)
        body.pop("metadata", None)
        # Always force id from the authenticated JWT — do not trust client-supplied id.
        body["id"] = user["id"]

        response = await db_admin.table("users").upsert(body).async_execute()
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
    allowed_tables = {
        "donor_details",
        "victim_details",
        "volunteer_details",
        "ngo_details",
    }
    if detail_table not in allowed_tables:
        raise HTTPException(
            status_code=400, detail=f"Invalid detail table: {detail_table}"
        )

    try:
        body = await request.json()
        body["id"] = user["id"]

        response = await db_admin.table(detail_table).upsert(body).async_execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


from pydantic import BaseModel as _BaseModel


class _RoleSwitchBody(_BaseModel):
    new_role: str


@router.post("/me/switch-role")
async def switch_role(body: _RoleSwitchBody, user: dict = Depends(get_current_user)):
    """Self-service role switching.

    Rules:
    - Any non-admin user can initiate a role switch.
    - Switching to ``victim`` happens immediately.
    - Switching to any other role requires admin approval and creates a pending request.
    """
    allowed_roles = {"donor", "victim", "volunteer", "ngo"}
    current_role = user.get("role", "")

    if current_role == "admin":
        raise HTTPException(
            status_code=403,
            detail="Admins must use admin endpoints for role changes",
        )

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

    metadata_resp = (
        await db_admin.table("users")
        .select("metadata")
        .eq("id", uid)
        .maybe_single()
        .async_execute()
    )
    existing_meta = (metadata_resp.data or {}).get("metadata") or {}

    if body.new_role == "victim":
        history = existing_meta.get("role_history", [])
        history.append(
            {
                "changed_by": uid,
                "timestamp": datetime.now(UTC).isoformat(),
                "old_role": current_role,
                "new_role": body.new_role,
                "reason": "Self-service role switch to victim",
            }
        )
        existing_meta["role_history"] = history

        await (
            db_admin.table("users")
            .update(
                {
                    "role": body.new_role,
                    "metadata": existing_meta,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            .eq("id", uid)
            .async_execute()
        )

        try:
            sb = get_supabase_client()
            sb.auth.admin.update_user_by_id(
                uid, {"app_metadata": {"role": body.new_role}}
            )
        except Exception as e:
            print(f"Warning: Failed to sync Supabase auth metadata: {e}")

        return {
            "message": f"Role switched to {body.new_role}",
            "role": body.new_role,
            "status": "switched",
        }

    pending_requests = existing_meta.get("pending_role_switch_requests", [])
    existing_pending = next(
        (
            req
            for req in pending_requests
            if req.get("status") == "pending"
            and req.get("requested_role") == body.new_role
        ),
        None,
    )
    if existing_pending:
        return {
            "message": f"Role switch to {body.new_role} is already pending admin approval",
            "requested_role": body.new_role,
            "status": "pending_approval",
        }

    pending_requests.append(
        {
            "request_id": f"{uid}:{body.new_role}:{int(datetime.now(UTC).timestamp())}",
            "requested_by": uid,
            "requested_at": datetime.now(UTC).isoformat(),
            "current_role": current_role,
            "requested_role": body.new_role,
            "status": "pending",
        }
    )
    existing_meta["pending_role_switch_requests"] = pending_requests
    existing_meta["latest_role_switch_request"] = {
        "requested_role": body.new_role,
        "status": "pending",
        "requested_at": datetime.now(UTC).isoformat(),
    }

    await (
        db_admin.table("users")
        .update(
            {
                "metadata": existing_meta,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        .eq("id", uid)
        .async_execute()
    )

    return {
        "message": f"Role switch request to {body.new_role} submitted. Waiting for admin approval.",
        "requested_role": body.new_role,
        "status": "pending_approval",
    }


# ============================================================
# Password Reset Endpoints
# ============================================================

# Simple in-memory rate limiter for forgot-password (per-IP)
_forgot_password_attempts: dict[str, list[float]] = {}
_FORGOT_PASSWORD_MAX_ATTEMPTS = 5
_FORGOT_PASSWORD_WINDOW_SECONDS = 300  # 5 minutes

_PASSWORD_REGEX = re.compile(r"^(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9]).{8,}$")


def _parse_allowed_origins() -> list[str]:
    origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
    return [
        origin.strip().rstrip("/")
        for origin in origins_raw.split(",")
        if origin.strip()
    ]


def _is_allowed_reset_redirect(url: str, allowed_origins: list[str]) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        if origin not in allowed_origins:
            return False
        return parsed.path.rstrip("/") == "/reset-password"
    except Exception:
        return False


def _check_forgot_password_rate_limit(client_ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    import time

    now = time.time()
    attempts = _forgot_password_attempts.get(client_ip, [])
    attempts = [t for t in attempts if now - t < _FORGOT_PASSWORD_WINDOW_SECONDS]
    if len(attempts) >= _FORGOT_PASSWORD_MAX_ATTEMPTS:
        _forgot_password_attempts[client_ip] = attempts
        return False

    attempts.append(now)
    _forgot_password_attempts[client_ip] = attempts
    return True


@router.post("/forgot-password")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """Request a password reset link.

    Always returns success message to avoid leaking account existence.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _check_forgot_password_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many password reset requests. Please try again later.",
        )

    # Validate email format
    email = (body.email or "").strip().lower()
    if not email or "@" not in email:
        # Still return success to avoid leaking info
        return {
            "message": "If an account exists with this email, a password reset link has been sent."
        }

    # Determine the redirect URL for the reset link
    allowed_origins = _parse_allowed_origins()
    default_origin = allowed_origins[0] if allowed_origins else "http://localhost:3000"

    request_origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if request_origin and request_origin in allowed_origins:
        default_origin = request_origin

    redirect_url = f"{default_origin}/reset-password"
    requested_redirect = (body.redirect_to or "").strip()
    if requested_redirect and _is_allowed_reset_redirect(
        requested_redirect, allowed_origins
    ):
        redirect_url = requested_redirect

    try:
        sb = get_supabase_client()
        sb.auth.reset_password_for_email(
            email,
            options={"redirect_to": redirect_url},
        )
        logger.info("Password reset email sent for email (hash: %s)", hash(email))
    except Exception as e:
        # Log but never expose whether the email exists
        logger.warning("Forgot password send result: %s", str(e))

    # Always return success — never reveal whether the email exists
    return {
        "message": "If an account exists with this email, a password reset link has been sent."
    }


@router.post("/reset-password")
async def reset_password(request: Request, body: ResetPasswordRequest):
    """Reset user password using a valid Supabase recovery session token.

    The access_token is obtained after the user clicks the recovery link
    in their email and Supabase creates a temporary session.
    """
    # Validate new password strength
    new_password = body.new_password
    if not new_password or len(new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long.",
        )

    if not _PASSWORD_REGEX.match(new_password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one uppercase letter, one number, and one special character.",
        )

    try:
        # Verify the recovery token is valid
        decoded = _verify_supabase_token(body.access_token)
        user_id = decoded.get("uid") or decoded.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid reset token.")

        # Update the password via Supabase Admin API
        sb = get_supabase_client()
        sb.auth.admin.update_user_by_id(user_id, {"password": new_password})

        logger.info("Password reset successful for user %s", user_id)

        return {"message": "Password has been reset successfully."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Password reset failed: %s", str(e))
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired reset token. Please request a new password reset link.",
        )


@router.post("/verify-email", response_model=EmailVerificationResponse)
async def verify_email(user: dict = Depends(get_current_user)):
    """Verify user's email verification status.

    Checks Supabase to see if the user's email is confirmed and updates
    the verification_status in the database accordingly.
    """
    try:
        sb = get_supabase_client()
        uid = user["id"]

        # Get the user's current info from Supabase
        try:
            supabase_user = sb.auth.admin.get_user_by_id(uid)
            email_confirmed = supabase_user.user.email_confirmed_at is not None
        except Exception as e:
            logger.warning(f"Failed to get user from Supabase: {e}")
            email_confirmed = False

        # Determine verification status
        new_status = "verified" if email_confirmed else "pending"

        # Update the user's verification_status in the database
        try:
            await db_admin.table("users").update(
                {
                    "verification_status": new_status,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", uid).async_execute()
        except Exception as e:
            logger.warning(f"Failed to update verification status in DB: {e}")
            # Still return the result even if DB update failed

        if email_confirmed:
            return EmailVerificationResponse(
                verified=True,
                message="Email has been verified successfully",
                verification_status=new_status,
            )
        else:
            return EmailVerificationResponse(
                verified=False,
                message="Email has not been verified yet. Please check your inbox for the verification link.",
                verification_status=new_status,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email verification check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ResendVerificationRequest(_BaseModel):
    email: str


@router.post("/resend-verification")
async def resend_verification(request: Request, body: ResendVerificationRequest):
    """Resend the verification email to the user.

    Allows users to request a new verification email if they didn't receive the original.
    """
    try:
        sb = get_supabase_client()

        # Get the origin for redirect
        allowed_origins = _parse_allowed_origins()
        default_origin = (
            allowed_origins[0] if allowed_origins else "http://localhost:3000"
        )
        request_origin = (request.headers.get("origin") or "").strip().rstrip("/")
        if request_origin and request_origin in allowed_origins:
            default_origin = request_origin

        redirect_url = f"{default_origin}/auth/callback"

        # Resend the verification email
        sb.auth.resend(
            {
                "type": "signup",
                "email": body.email,
                "redirect_to": redirect_url,
            }
        )

        logger.info("Verification email resent for email (hash: %s)", hash(body.email))
        return {
            "message": "Verification email has been resent. Please check your inbox."
        }

    except Exception as e:
        logger.warning("Resend verification failed: %s", str(e))
        # Always return success to avoid leaking whether email exists
        return {
            "message": "Verification email has been resent. Please check your inbox."
        }
