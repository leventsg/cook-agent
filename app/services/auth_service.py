"""
CookAgent 认证服务

提供用户注册、密码哈希处理以及 JWT Token 生成功能
包含以下安全特性：
- 多次登录失败后的账户锁定机制
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import bcrypt
from jose import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from redis.asyncio import Redis

from app.config import settings
from app.database.models import UserModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)

class AuthService:
    """提供用户认证与注册功能的服务，包含安全防护机制"""

    def __init__(self, secret_key: str | None = None):
        self.secret_key = secret_key or settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.max_failed_attempts = settings.LOGIN_MAX_FAILED_ATTEMPTS
        self.lockout_minutes = settings.LOGIN_LOCKOUT_MINUTES
        self._redis: Optional[Redis] = None

    def set_redis(self, redis_client: Redis) -> None:
        """设置 Redis 客户端，用于登录尝试跟踪。"""
        self._redis = redis_client

    # ------------------------------------------------------------------
    # 登录尝试跟踪（账户锁定机制）
    # ------------------------------------------------------------------
    async def _get_failed_attempts_key(self, username: str) -> str:
        """生成用于跟踪登录失败尝试的 Redis 键."""
        return f"auth:failed_attempts:{username}"

    async def _get_lockout_key(self, username: str) -> str:
        """生成用于账户锁定的 Redis 键."""
        return f"auth:lockout:{username}"

    async def is_account_locked(self, username: str) -> Tuple[bool, int]:
        """
        检查账户是否因登录失败而被锁定。

        Returns:
            (is_locked, remaining_seconds)
        """
        if not self._redis:
            return False, 0

        lockout_key = await self._get_lockout_key(username)
        ttl = await self._redis.ttl(lockout_key)

        if ttl > 0:
            return True, ttl

        return False, 0

    async def record_failed_attempt(self, username: str) -> Tuple[int, bool]:
        """
        记录登录失败尝试。

        Returns:
            (current_attempts, is_now_locked)
        """
        if not self._redis:
            return 0, False

        failed_key = await self._get_failed_attempts_key(username)
        lockout_key = await self._get_lockout_key(username)

        # 增加失败尝试次数
        attempts = await self._redis.incr(failed_key)

        # 设置过期时间（重置后）
        await self._redis.expire(failed_key, self.lockout_minutes * 60)

        # 检查是否达到锁定阈值
        if attempts >= self.max_failed_attempts:
            # 锁定账户
            await self._redis.setex(
                lockout_key,
                self.lockout_minutes * 60,
                "locked"
            )
            logger.warning(f"Account locked: {username} after {attempts} failed attempts")
            return attempts, True

        return attempts, False

    async def clear_failed_attempts(self, username: str) -> None:
        """
        清除登录失败尝试记录。
        """
        if not self._redis:
            return

        failed_key = await self._get_failed_attempts_key(username)
        lockout_key = await self._get_lockout_key(username)

        await self._redis.delete(failed_key, lockout_key)

    # ------------------------------------------------------------------
    # 用户检索辅助函数
    # ------------------------------------------------------------------
    async def get_user_by_username(self, username: str) -> Optional[UserModel]:
        async with get_session_context() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # 注册与认证
    # ------------------------------------------------------------------
    async def register_user(self, username: str, password: str) -> UserModel:
        existing = await self.get_user_by_username(username)
        if existing:
            raise ValueError("Username already exists")

        password_hash = self._hash_password(password)
        user = UserModel(username=username, password_hash=password_hash)

        async with get_session_context() as session:
            session.add(user)
            try:
                await session.flush()
            except IntegrityError as exc:
                logger.warning("Integrity error on user register: %s", exc)
                raise ValueError("Username already exists")

        logger.info("Created user %s", username)
        return user

    async def authenticate_user(self, username: str, password: str) -> Optional[UserModel]:
        user = await self.get_user_by_username(username)
        if not user:
            return None
        if not self._verify_password(password, user.password_hash):
            return None
        return user

    # ------------------------------------------------------------------
    # Token 管理
    # ------------------------------------------------------------------
    def create_access_token(self, user: UserModel) -> str:
        expire = datetime.now() + timedelta(minutes=self.expire_minutes)
        payload = {"sub": user.username, "uid": str(user.id), "exp": expire}
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return {"username": payload.get("sub"), "user_id": payload.get("uid")}
        except Exception as exc:  # broad catch to avoid import of ExpiredSignatureError etc
            logger.warning("Failed to decode token: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 密码辅助函数
    # ------------------------------------------------------------------
    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def _verify_password(self, password: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except ValueError:
            return False


auth_service = AuthService()