"""
LLM Provider Layer - 统一的 LLM 初始化和调用入口

使用方式:

1. 创建带 usage tracking 的 invoker（推荐）:

    from app.llm import LLMProvider, llm_context
    from app.config import settings

    provider = LLMProvider(settings.llm)
    invoker = provider.create_invoker("fast")

    with llm_context("my_module", user_id="xxx"):
        response = await invoker.ainvoke(messages)

2. 高级用法：创建原生 ChatOpenAI 实例（不含 usage tracking）:

    from app.llm import LLMProvider
    from app.config import settings

    provider = LLMProvider(settings.llm)
    llm = provider.create_llm("normal", streaming=True)

    response = await llm.ainvoke(messages)
"""

from app.llm.provider import (
    # 核心类
    LLMProvider,
    LLMInvoker,
)
from app.llm.callbacks import get_usage_callbacks
from app.llm.context import (
    LLMCallContext,
    llm_context,
    set_llm_context,
    get_llm_context,
    clear_llm_context,
)

__all__ = [
    # 核心类
    "LLMProvider",
    "LLMInvoker",
    # 上下文管理
    "LLMCallContext",
    "llm_context",
    "set_llm_context",
    "get_llm_context",
    "clear_llm_context",
    # Callbacks
    "get_usage_callbacks",
]
