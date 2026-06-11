"""
CookAgent 限流中间件

基于 Redis 提供 IP 级和用户级限流能力
支持针对不同类型的接口配置不同的限流策略
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """CookAgent 限流配置类"""

    # 全局ip限流，默认每分钟100次请求
    global_per_minute: int = 100

    # 接口限流
    login_per_minute: int = 5
    conversation_per_minute: int = 30

    # 限流窗口大小，默认60秒
    window_seconds: int = 60

    # 是否启用限流，默认启用
    enabled: bool = True


class RateLimiter:
    """
    CookAgent 限流器

    基于 Redis 的滑动窗口算法实现。
    使用 Redis INCR 和 TTL 实现高效的限流。
    支持 IP 级和用户级限流。
    """

    def __init__(self, redis_client: Optional[Redis] = None, config: Optional[RateLimitConfig] = None):
        self.redis: Optional[Redis] = redis_client
        self.config = config or RateLimitConfig(
            global_per_minute=settings.RATE_LIMIT_GLOBAL_PER_MINUTE,
            login_per_minute=settings.RATE_LIMIT_LOGIN_PER_MINUTE,
            conversation_per_minute=settings.RATE_LIMIT_CONVERSATION_PER_MINUTE,
            enabled=settings.RATE_LIMIT_ENABLED,
        )

    def set_redis(self, redis_client: Redis) -> None:
        """设置 Redis 客户端 (在应用启动后调用)"""
        self.redis = redis_client

    async def _get_rate_limit_key(self, request: Request, key_type: str = "ip") -> str:
        """
        基于请求类型生成限流键

        Args:
            request: FastAPI 请求对象
            key_type: "ip" 表示基于 IP 基于限流，"user" 表示基于用户级限流

        Returns:
            Redis key string
        """
        # 获取客户端请求 IP
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.headers.get("X-Real-IP", "")
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        # 获取当前时间窗口
        window = int(time.time() // self.config.window_seconds)

        if key_type == "user":
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                return f"rate_limit:user:{user_id}:{window}"

        return f"rate_limit:ip:{client_ip}:{window}"

    async def _check_limit(self, key: str, limit: int) -> tuple[bool, int, int]:
        """
        检查请求是否超过限流阈值

        Args:
            key: Redis key
            limit: 请求限制次数

        Returns:
            (is_allowed, current_count, remaining)
        """
        if not self.redis:
            # 如果 Redis 客户端不可用，允许所有请求
            return True, 0, limit

        try:
            # 增加请求计数
            current = await self.redis.incr(key)

            # 设置 TTL
            if current == 1:
                # +1s 是保证在窗口结束后键过期删除，避免过早过期导致的误判
                await self.redis.expire(key, self.config.window_seconds + 1)

            remaining = max(0, limit - current)
            is_allowed = current <= limit

            return is_allowed, current, remaining

        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}, allowing request")
            return True, 0, limit

    def _get_limit_for_path(self, path: str) -> int:
        """根据端点路径获取限流配置."""
        if "/auth/login" in path or "/auth/register" in path:
            return self.config.login_per_minute
        elif "/conversation" in path:
            return self.config.conversation_per_minute
        else:
            return self.config.global_per_minute

    async def check_rate_limit(self, request: Request) -> Optional[JSONResponse]:
        """
        检查请求的限流状态。

        Args:
            request: FastAPI 请求对象

        Returns:
            None 或 JSONResponse 对象
        """
        if not self.config.enabled:
            return None

        path = request.url.path

        # docs 和 openapi 不限流
        if path.startswith("/docs") or path.startswith("/openapi") or path == "/":
            return None

        # 获取当前端点的限流配置
        limit = self._get_limit_for_path(path)

        # 检查 IP 基于限流配置
        ip_key = await self._get_rate_limit_key(request, "ip")
        is_allowed, current, remaining = await self._check_limit(ip_key, limit)

        if not is_allowed:
            logger.warning(
                f"Rate limit exceeded: path={path}, key={ip_key}, "
                f"current={current}, limit={limit}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "请求过于频繁，请稍后再试",
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": self.config.window_seconds,
                },
                headers={
                    "Retry-After": str(self.config.window_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + self.config.window_seconds),
                }
            )

        # 保存限流信息到请求状态，供后续中间件或服务使用
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_limit = limit

        return None


rate_limiter = RateLimiter()
