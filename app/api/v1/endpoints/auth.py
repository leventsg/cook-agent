"""
认证相关 API 接口：注册与登录
包含以下安全特性：
- 账户锁定机制
- 审计日志记录
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.auth_service import auth_service
from app.security.audit import audit_logger

router = APIRouter()
logger = logging.getLogger(__name__)

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=3, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=3, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@router.post("/auth/register", response_model=TokenResponse)
async def register(request: RegisterRequest, http_request: Request):
    """
    注册新用户
    """
    try:
        user = await auth_service.register_user(request.username, request.password)
    except ValueError as exc:
        audit_logger.login_failure(
            username=request.username,
            request=http_request,
            reason="registration_failed_username_exists",
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.error("Register error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed")
    
    token = auth_service.create_access_token(user)
    audit_logger.login_success(
        username=user.username,
        user_id=str(user.id),
        request=http_request,
    )
    return TokenResponse(access_token=token, username=user.username)

@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, http_request: Request):
    """Authenticate user and return JWT token with security protections."""
    # 检查账户锁定状态
    is_locked, remaining_seconds = await auth_service.is_account_locked(request.username)
    if is_locked:
        audit_logger.login_failure(
            username=request.username,
            request=http_request,
            reason="account_locked",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"账户已被锁定，请在 {remaining_seconds // 60 + 1} 分钟后重试",
            headers={"Retry-After": str(remaining_seconds)},
        )

    user = await auth_service.authenticate_user(request.username, request.password)
    if not user:
        # 记录登录失败尝试
        attempts, is_now_locked = await auth_service.record_failed_attempt(request.username)

        audit_logger.login_failure(
            username=request.username,
            request=http_request,
            reason="invalid_credentials",
        )

        if is_now_locked:
            audit_logger.account_locked(
                username=request.username,
                request=http_request,
                failed_attempts=attempts,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录失败次数过多，账户已锁定 {auth_service.lockout_minutes} 分钟",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    # 清除登录失败尝试记录
    await auth_service.clear_failed_attempts(request.username)

    token = auth_service.create_access_token(user)
    audit_logger.login_success(
        username=user.username,
        user_id=str(user.id),
        request=http_request,
    )
    return TokenResponse(access_token=token, username=user.username)
    