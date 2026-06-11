"""
LLM 调用上下文管理

使用 contextvars 在调用栈中传递跟踪信息（module_name, user_id, conversation_id），
无需修改函数签名。
"""

import uuid
import logging
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class LLMCallContext:
    """LLM 调用上下文信息"""

    request_id: str  # 唯一请求 ID
    module_name: str  # 调用模块名称
    user_id: Optional[str] = None  # 用户 ID
    conversation_id: Optional[str] = None  # 对话 ID

# 上下文变量
_llm_context: ContextVar[Optional[LLMCallContext]] = ContextVar(
    "llm_context", default=None
)

def set_llm_context(
    module_name: str,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> LLMCallContext:
    """
    设置当前 LLM 调用上下文

    Args:
        module_name: 调用模块名称
        user_id: 用户 ID（可选）
        conversation_id: 对话 ID（可选）

    Returns:
        创建的上下文实例
    """
    ctx = LLMCallContext(
        request_id=str(uuid.uuid4()),
        module_name=module_name,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    _llm_context.set(ctx)
    return ctx

def get_llm_context() -> Optional[LLMCallContext]:
    """获取当前 LLM 调用上下文"""
    return _llm_context.get()


def clear_llm_context() -> None:
    """清除当前 LLM 调用上下文"""
    _llm_context.set(None)

@contextmanager
def llm_context(
    module_name: str,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
):
    """
    LLM 调用上下文管理器

    自动设置和清除上下文。

    使用方式:
        with llm_context("intent_detector", user_id="user123"):
            response = await llm.ainvoke(messages)

    Args:
        module_name: 调用模块名称
        user_id: 用户 ID（可选）
        conversation_id: 对话 ID（可选）

    Yields:
        创建的上下文实例
    """
    ctx = set_llm_context(module_name, user_id, conversation_id)
    try:
        yield ctx
    finally:
        clear_llm_context()