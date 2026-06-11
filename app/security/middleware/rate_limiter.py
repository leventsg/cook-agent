"""
Rate limiting middleware for CookHero.

Provides IP-level and user-level rate limiting using Redis.
Supports different limits for different endpoint types.
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
    """Configuration for rate limiting."""

    # Global limits (per IP)
    global_per_minute: int = 100

    # Endpoint-specific limits
    login_per_minute: int = 5
    conversation_per_minute: int = 30

    # Window size in seconds
    window_seconds: int = 60

    # Whether to enable rate limiting
    enabled: bool = True


class RateLimiter:
    """
    Redis-based rate limiter with sliding window algorithm.

    Uses Redis INCR with TTL for efficient rate limiting.
    Supports IP-level and user-level limiting.
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
        """Set Redis client (called after app startup)."""
        self.redis = redis_client

    async def _get_rate_limit_key(self, request: Request, key_type: str = "ip") -> str:
        """
        Generate rate limit key based on type.

        Args:
            request: FastAPI request object
            key_type: "ip" for IP-based, "user" for user-based

        Returns:
            Redis key string
        """
        # Get client IP (handle proxy headers)
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.headers.get("X-Real-IP", "")
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        # Get current minute window
        window = int(time.time() // self.config.window_seconds)

        if key_type == "user":
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                return f"rate_limit:user:{user_id}:{window}"

        return f"rate_limit:ip:{client_ip}:{window}"

    async def _check_limit(self, key: str, limit: int) -> tuple[bool, int, int]:
        """
        Check if rate limit is exceeded.

        Args:
            key: Redis key
            limit: Maximum allowed requests

        Returns:
            Tuple of (is_allowed, current_count, remaining)
        """
        if not self.redis:
            # If Redis not available, allow all requests
            return True, 0, limit

        try:
            # Increment counter
            current = await self.redis.incr(key)

            # Set TTL on first request
            if current == 1:
                await self.redis.expire(key, self.config.window_seconds + 1)

            remaining = max(0, limit - current)
            is_allowed = current <= limit

            return is_allowed, current, remaining

        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}, allowing request")
            return True, 0, limit

    def _get_limit_for_path(self, path: str) -> int:
        """Get rate limit based on endpoint path."""
        if "/auth/login" in path or "/auth/register" in path:
            return self.config.login_per_minute
        elif "/conversation" in path:
            return self.config.conversation_per_minute
        else:
            return self.config.global_per_minute

    async def check_rate_limit(self, request: Request) -> Optional[JSONResponse]:
        """
        Check rate limit for a request.

        Args:
            request: FastAPI request object

        Returns:
            None if allowed, JSONResponse if rate limited
        """
        if not self.config.enabled:
            return None

        path = request.url.path

        # Skip rate limiting for docs and health endpoints
        if path.startswith("/docs") or path.startswith("/openapi") or path == "/":
            return None

        # Get appropriate limit for this endpoint
        limit = self._get_limit_for_path(path)

        # Check IP-based rate limit
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

        # Store rate limit info for response headers
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_limit = limit

        return None


# Global rate limiter instance
rate_limiter = RateLimiter()
