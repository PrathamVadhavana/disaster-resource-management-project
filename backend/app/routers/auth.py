from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.database import supabase
from app.schemas import UserLogin, UserRegister, Token

router = APIRouter()
security = HTTPBearer()


@router.post("/register", response_model=Token)
async def register(user: UserRegister):
    """Register a new user"""
    try:
        # 1. Create auth user
        auth_response = supabase.auth.sign_up({
            "email": user.email,
            "password": user.password,
            "options": {
                "data": {
                    "full_name": user.full_name,
                    "role": user.role
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Registration failed")
        
        # 2. Create user profile using ADMIN client (bypasses RLS)
        profile_data = {
            "id": auth_response.user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role
        }
        
        try:
            # Using table("profiles") instead of "users" and supabase_admin
            from app.database import supabase_admin
            supabase_admin.table("profiles").insert(profile_data).execute()
        except Exception as db_error:
            # If profile creation fails, we should ideally rollback user creation 
            # or have a retry mechanism. For now, we log and return error.
            print(f"Database Error: {str(db_error)}")
            raise HTTPException(
                status_code=500, 
                detail=f"User created but profile creation failed: {str(db_error)}"
            )
        
        return Token(
            access_token=auth_response.session.access_token,
            token_type="bearer",
            user_id=auth_response.user.id,
            email=user.email
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """Login user and return access token"""
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        
        if not auth_response.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return Token(
            access_token=auth_response.session.access_token,
            token_type="bearer",
            user_id=auth_response.user.id,
            email=credentials.email
        )
        
    except Exception as e:
        if "Invalid" in str(e) or "credentials" in str(e):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Logout user"""
    try:
        supabase.auth.sign_out()
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me")
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get current user profile"""
    try:
        # Verify token and get user
        user = supabase.auth.get_user(credentials.credentials)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get user profile
        response = supabase.table("users").select("*").eq("id", user.user.id).single().execute()
        
        return response.data
        
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication failed")
