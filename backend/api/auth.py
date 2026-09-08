"""Auth API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import LoginRequest, LoginResponse, SessionUser, UserProfile
from core.auth import AuthContext, authenticate_password, create_access_token, get_current_user
from db.repositories.machines import get_user_profile

router = APIRouter()

@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate a local password and return a short-lived bearer token."""

    user = await authenticate_password(request.user_id, request.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    return LoginResponse(
        access_token=create_access_token(user),
        user=SessionUser(user_id=user.user_id, company_id=user.company_id, visibility=user.visibility),
    )

@router.get("/auth/me", response_model=SessionUser)
async def current_session(user: AuthContext = Depends(get_current_user)) -> SessionUser:
    """Return the user resolved from the submitted bearer token."""

    return SessionUser(
        user_id=user.user_id,
        company_id=user.company_id,
        visibility=user.visibility,
    )

@router.get("/profile", response_model=UserProfile)
async def profile(user: AuthContext = Depends(get_current_user)) -> UserProfile:
    """Return the signed-in user's own account and company information."""

    details = await get_user_profile(user)
    return UserProfile(**details)
