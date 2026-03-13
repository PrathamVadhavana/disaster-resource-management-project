"""
Centralized dependencies for the Disaster Management API.

Provides reusable auth helpers so every router doesn't need its own
copy of _get_user_id / _require_admin / _require_role.

Auth layer: Supabase Auth (JWT verification via python-jose).
Database  : Supabase PostgREST via db_client.
"""

import logging
import os

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwk, jwt

from app.database import db_admin

logger = logging.getLogger(__name__)

# Global ML service instance
ml_service = None

security = HTTPBearer()

# Cached JWKS public key for ES256 verification
_jwks_key = None


# ── Supabase JWT verification ─────────────────────────────────────────────────


def _get_jwt_secret() -> str:
    """Return Supabase JWT secret from environment."""
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("SUPABASE_JWT_SECRET must be set")
    return secret


def _get_jwks_key():
    """Fetch and cache the ES256 public key from Supabase JWKS endpoint."""
    global _jwks_key
    if _jwks_key is not None:
        return _jwks_key
    supabase_url = os.environ.get("SUPABASE_URL", "")
    if not supabase_url:
        return None
    try:
        resp = httpx.get(f"{supabase_url}/auth/v1/.well-known/jwks.json", timeout=10)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
        if keys:
            _jwks_key = keys[0]
            logger.info("JWKS public key loaded (alg=%s)", _jwks_key.get("alg"))
            return _jwks_key
    except Exception as e:
        logger.warning("Failed to fetch JWKS: %s", e)
    return None


def init_supabase_auth() -> None:
    """Initialise Supabase auth — JWKS key will be fetched on first request."""
    logger.info("Supabase auth ready (JWT secret loaded)")


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


def _verify_supabase_token(token: str) -> dict:
    """Verify a Supabase JWT and return the decoded claims dict.

    Supports both ES256 (JWKS public key) and HS256 (JWT secret) tokens.

    Raises HTTPException 401 on any verification failure.
    """
    try:
        # Try ES256 verification with JWKS public key first
        jwks_data = _get_jwks_key()
        if jwks_data:
            try:
                key = jwk.construct(jwks_data)
                decoded = jwt.decode(
                    token,
                    key,
                    algorithms=["ES256"],
                    audience="authenticated",
                )
                decoded["uid"] = decoded.get("sub", "")
                return decoded
            except (JWTError, ExpiredSignatureError):
                # Fall through to HS256
                pass

        # Fallback: HS256 with JWT secret
        secret = _get_jwt_secret()
        decoded = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        decoded["uid"] = decoded.get("sub", "")
        return decoded
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except JWTError as e:
        logger.warning("JWT verification error: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error("Token verification error: %s", e)
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Extract and verify user from bearer token. Returns uid."""
    decoded = _verify_supabase_token(credentials.credentials)
    return decoded["uid"]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Extract and verify user from bearer token.

    Returns a dict with id, email, role, and metadata.
    The role is read from the Supabase user_metadata or ``app_metadata``
    baked into the JWT.  If missing, a fallback lookup against the ``users``
    table is performed.
    """
    decoded = _verify_supabase_token(credentials.credentials)
    uid = decoded["uid"]
    email = decoded.get("email")
    # Supabase stores custom claims in app_metadata or user_metadata
    app_meta = decoded.get("app_metadata", {})
    user_meta = decoded.get("user_metadata", {})
    role = app_meta.get("role") or user_meta.get("role")
    app_meta.get("additional_roles", [])

    # Source of truth: always prefer DB role so admin-approved role changes
    # apply immediately even if JWT claim is stale.
    try:
        db_resp = (
            await db_admin.table("users")
            .select("role, additional_roles, email")
            .eq("id", uid)
            .maybe_single()
            .async_execute()
        )
        if db_resp.data:
            role = db_resp.data.get("role") or role
            email = email or db_resp.data.get("email")
    except Exception as db_err:
        print(f"DB role lookup error: {db_err}")

    return {
        "id": uid,
        "email": email,
        "role": role,
        "metadata": decoded,
    }


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
        decoded = _verify_supabase_token(credentials.credentials)
        uid = decoded["uid"]
        email = decoded.get("email")
        app_meta = decoded.get("app_metadata", {})
        user_meta = decoded.get("user_metadata", {})
        role = app_meta.get("role") or user_meta.get("role")
        additional_roles = app_meta.get("additional_roles", [])

        # Source of truth: always prefer DB role and additional roles so
        # role updates made by admin are effective immediately.
        try:
            db_resp = (
                await db_admin.table("users")
                .select("role, additional_roles")
                .eq("id", uid)
                .maybe_single()
                .async_execute()
            )
            if db_resp.data:
                role = db_resp.data.get("role") or role
                db_additional = db_resp.data.get("additional_roles") or []
                if isinstance(db_additional, list):
                    additional_roles = db_additional
        except Exception as db_err:
            print(f"DB role lookup error: {db_err}")

        user_roles = [role] + (additional_roles if isinstance(additional_roles, list) else [])

        if not any(r in allowed_roles for r in user_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}. Your roles: {user_roles}",
            )
        return {
            "id": uid,
            "email": email,
            "role": role,
            "roles": user_roles,
            "metadata": decoded,
        }

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
    Reads verification_status from the database (users table) for
    immediate effect after admin verification, rather than relying
    on JWT claims which may take up to 1 hour to refresh.
    """

    async def _check(
        user: dict = Depends(require_role(*allowed_roles)),
    ) -> dict:
        # Admin is always 'verified' implicitly
        if user.get("role") == "admin":
            return user

        # First check JWT claims (fast path)
        status = user.get("metadata", {}).get("verification_status")

        # Fallback: read from the database for immediate effect after admin verification
        if not status or status == "pending":
            try:
                db_resp = (
                    await db_admin.table("users")
                    .select("verification_status")
                    .eq("id", user["id"])
                    .maybe_single()
                    .async_execute()
                )
                if db_resp.data:
                    status = db_resp.data.get("verification_status") or "pending"
            except Exception as e:
                print(f"DB verification check error: {e}")

        if status != "verified":
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Your account (role: {user.get('role')}) is currently '{status or 'pending'}'. Verification from an admin is required.",
            )
        return user

    return _check


require_verified_ngo = require_verified_role("admin", "ngo")
require_verified_donor = require_verified_role("admin", "donor")
require_verified_volunteer = require_verified_role("admin", "volunteer")
