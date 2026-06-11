"""
CookAgent 审计日志模块
"""
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from fastapi import Request

class AuditEventType(Enum):
    """审计事件类型枚举"""

    # 用户认证
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    TOKEN_CREATED = "auth.token.created"
    TOKEN_REFRESH = "auth.token.refresh"
    TOKEN_INVALID = "auth.token.invalid"

    # 帐号安全
    ACCOUNT_LOCKED = "account.locked"
    ACCOUNT_UNLOCKED = "account.unlocked"
    PASSWORD_CHANGED = "account.password.changed"
    PROFILE_UPDATED = "account.profile.updated"

    # 限流
    RATE_LIMIT_EXCEEDED = "security.rate_limit.exceeded"

    # 输入验证
    PROMPT_INJECTION_BLOCKED = "security.prompt_injection.blocked"
    PROMPT_INJECTION_WARNING = "security.prompt_injection.warning"
    INPUT_VALIDATION_FAILED = "security.input.validation_failed"

    # 数据操作
    CONVERSATION_CREATED = "data.conversation.created"
    CONVERSATION_DELETED = "data.conversation.deleted"
    DOCUMENT_CREATED = "data.document.created"
    DOCUMENT_DELETED = "data.document.deleted"

    # 系统
    CONFIG_CHANGED = "system.config.changed"
    ERROR = "system.error"


class AuditLogger:
    """
    安全事件结构化审计日志记录器
    以 JSON 格式记录安全事件
    """
    def __init__(self, logger_name: str = "security.audit"):
        """
        初始化审计日志记录器

        Args:
            logger_name: 日志记录器名称
        """
        self.logger = logging.getLogger(logger_name)

        # 确保至少有一个处理器，否则日志将不会输出
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def _get_client_info(self, request: Optional[Request]) -> Dict[str, Any]:
        """从请求中提取客户端信息"""
        if not request:
            return {}

        # 获取客户端 IP
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.headers.get("X-Real-IP", "")
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        return {
            "ip": client_ip,
            "user_agent": request.headers.get("User-Agent", ""),
            "path": str(request.url.path),
            "method": request.method,
        }

    def log(
        self,
        event_type: AuditEventType,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        request: Optional[Request] = None,
        success: bool = True,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        记录日志

        Args:
            event_type: 安全事件类型
            user_id: 用户 ID
            username: 用户名
            request: FastAPI 请求对象，用于获取客户端信息
            success: 操作是否成功
            details: 额外的事件详情
            error: 错误消息
        """
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": event_type.value,
            "success": success,
            "user_id": user_id,
            "username": username,
            "client": self._get_client_info(request),
            "details": details or {},
        }

        if error:
            event["error"] = error

        # 根据事件类型和成功状态确定日志级别
        if not success or event_type in (
            AuditEventType.PROMPT_INJECTION_BLOCKED,
            AuditEventType.RATE_LIMIT_EXCEEDED,
            AuditEventType.ACCOUNT_LOCKED,
        ):
            log_level = logging.WARNING
        elif event_type == AuditEventType.ERROR:
            log_level = logging.ERROR
        else:
            log_level = logging.INFO

        # json格式好解析
        self.logger.log(log_level, json.dumps(event, ensure_ascii=False))

    def login_success(
        self,
        username: str,
        user_id: str,
        request: Optional[Request] = None,
    ) -> None:
        """记录成功登录"""
        self.log(
            AuditEventType.LOGIN_SUCCESS,
            user_id=user_id,
            username=username,
            request=request,
            success=True,
        )

    def login_failure(
        self,
        username: str,
        request: Optional[Request] = None,
        reason: str = "invalid_credentials",
    ) -> None:
        """记录失败的登录尝试"""
        self.log(
            AuditEventType.LOGIN_FAILURE,
            username=username,
            request=request,
            success=False,
            details={"reason": reason},
        )
        
    def account_locked(
        self,
        username: str,
        request: Optional[Request] = None,
        failed_attempts: int = 0,
        lockout_minutes: int = 15,
    ) -> None:
        """记录由于失败尝试导致的账户锁定"""
        self.log(
            AuditEventType.ACCOUNT_LOCKED,
            username=username,
            request=request,
            success=False,
            details={
                "failed_attempts": failed_attempts,
                "lockout_minutes": lockout_minutes,
            },
        )

    def rate_limit_exceeded(
        self,
        request: Optional[Request] = None,
        user_id: Optional[str] = None,
        endpoint: str = "",
        limit: int = 0,
        current: int = 0,
    ) -> None:
        """记录超出速率限制的事件"""
        self.log(
            AuditEventType.RATE_LIMIT_EXCEEDED,
            user_id=user_id,
            request=request,
            success=False,
            details={
                "endpoint": endpoint,
                "limit": limit,
                "current": current,
            },
        )

    def prompt_injection_blocked(
        self,
        user_id: Optional[str] = None,
        request: Optional[Request] = None,
        patterns: Optional[list] = None,
        input_preview: str = "",
    ) -> None:
        """记录被阻止的提示注入尝试"""
        self.log(
            AuditEventType.PROMPT_INJECTION_BLOCKED,
            user_id=user_id,
            request=request,
            success=False,
            details={
                "patterns": patterns or [],
                "input_preview": input_preview[:100] if input_preview else "",
            },
        )

    def token_invalid(
        self,
        request: Optional[Request] = None,
        reason: str = "invalid",
    ) -> None:
        """记录无效令牌尝试"""
        self.log(
            AuditEventType.TOKEN_INVALID,
            request=request,
            success=False,
            details={"reason": reason},
        )

audit_logger = AuditLogger()