"""
用户信息相关接口：获取当前用户信息和更新用户信息
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.services.auth_service import auth_service
from app.services.user_service import user_service

router = APIRouter()
logger = logging.getLogger(__name__)


class UserProfile(BaseModel):
    username: str
    occupation: Optional[str] = None
    bio: Optional[str] = None
    profile: Optional[str] = None
    user_instruction: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    occupation: Optional[str] = None
    bio: Optional[str] = None
    profile: Optional[str] = None
    user_instruction: Optional[str] = None


def _get_identity_from_auth(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    identity = auth_service.decode_token(token)
    if not identity or not identity.get("username"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return identity


@router.get("/user/profile", response_model=UserProfile)
async def get_profile(identity: dict = Depends(_get_identity_from_auth)):
    user = await user_service.get_user_by_username(identity["username"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserProfile(
        username=user.username,
        occupation=user.occupation,
        bio=user.bio,
        profile=user.profile,
        user_instruction=user.user_instruction
    )


@router.put("/user/profile", response_model=UserProfile)
async def update_profile(req: UpdateProfileRequest, identity: dict = Depends(_get_identity_from_auth)):
    try:
        user = await user_service.update_profile(identity["username"], req.dict(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return UserProfile(
        username=user.username,
        occupation=user.occupation,
        bio=user.bio,
        profile=user.profile,
        user_instruction=user.user_instruction
    )
