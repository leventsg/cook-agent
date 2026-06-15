"""
Security Check Utilities

统一的安全检查辅助函数，可以在需要安全检查的 endpoint 中使用。
替代在 agent.py 和 conversation.py 中重复的安全检查逻辑。
"""

import logging

from fastapi import HTTPException, Request

from app.security.prompt_guard import prompt_guard, ThreatLevel
from app.security.guardrails import guard as nemo_guard, GuardResult
from app.security.audit import audit_logger

logger = logging.getLogger(__name__)
async def check_message_security(message: str, request: Request) -> str:
    """
    统一的消息安全检查函数。

    执行：
    1. 基础模式检查（prompt_guard）
    2. 深度 LLM 检查（nemo_guard，如果启用）

    Args:
        message: 需要检查的消息内容
        request: FastAPI 请求对象

    Returns:
        str: 清理后的消息（如果检查通过）

    Raises:
        HTTPException: 如果检测到威胁
    """
    # ==========================================================================
    # Security Layer 1: 基础模式检查（快速，无 LLM）
    # ==========================================================================
    scan_result = prompt_guard.scan(message)
    if scan_result.threat_level == ThreatLevel.BLOCKED:
        audit_logger.prompt_injection_blocked(
            user_id=getattr(request.state, "user_id", None),
            request=request,
            patterns=scan_result.matched_patterns,
            input_preview=message[:100],
        )
        raise HTTPException(
            status_code=400,
            detail=scan_result.reason or "检测到潜在的恶意输入，请修改您的问题",
        )

    # ==========================================================================
    # Security Layer 2: 深度 LLM 检查（如果启用）
    # ==========================================================================
    try:
        guard_result = await nemo_guard.check_input(message)
        if guard_result.should_block:
            audit_logger.prompt_injection_blocked(
                user_id=getattr(request.state, "user_id", None),
                request=request,
                patterns=[
                    "guardrails:"
                    + (guard_result.details or {}).get("threat_type", "unknown")
                ],
                input_preview=message[:100],
            )
            raise HTTPException(
                status_code=400,
                detail=guard_result.reason or "检测到潜在的恶意输入，请修改您的问题",
            )
        elif guard_result.result == GuardResult.WARNING:
            logger.warning(f"Guardrails warning: {guard_result.reason}")
    except HTTPException:
        raise  # 直接抛出 HTTPException
    except Exception as e:
        # 不阻塞在 guardrails 错误上，仅记录日志
        logger.error(f"Guardrails check error (non-blocking): {e}")

    # 如果都通过了，返回净化后的输入（如果有）
    return scan_result.sanitized_input or message