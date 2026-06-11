"""
LLM Usage Tracking Callbacks

捕获 LLM 调用的 token 使用量，并异步写入数据库。
"""
import asyncio
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from app.llm.context import get_llm_context

logger = logging.getLogger(__name__)

# 后台事件循环（用于异步写入数据库）
_background_loop: Optional[asyncio.AbstractEventLoop] = None
_background_thread: Optional[threading.Thread] = None

def _get_background_loop() -> asyncio.AbstractEventLoop:
    """获取或创建后台事件循环"""
    global _background_loop, _background_thread

    if _background_loop is None or not _background_loop.is_running():
        _background_loop = asyncio.new_event_loop()
        _background_thread = threading.Thread(
            target=_background_loop.run_forever, daemon=True, name="llm-usage-logger"
        )
        _background_thread.start()

    return _background_loop

class LLMUsageCallbackHandler(BaseCallbackHandler):
    """
    LangChain 回调处理器，用于追踪 LLM 使用统计

    在每次 LLM 调用完成时捕获 token 使用信息，并异步写入数据库。
    上下文信息（module_name, user_id, conversation_id）通过 contextvars 获取。
    """

    def __init__(self):
        super().__init__()
        self._start_time: Dict[str, float] = {}

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 调用开始时记录时间"""
        self._start_time[str(run_id)] = time.time()

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """LLM 调用完成时捕获 usage 并写入数据库"""
        duration_ms = (
            int((time.time() - self._start_time.pop(str(run_id), time.time())) * 1000)
        )

        # 获取上下文
        ctx = get_llm_context()
        if not ctx:
            logger.debug("No LLM context set, skipping usage logging")
            return

        # 提取 token 使用信息
        usage_data = self._extract_usage(response)
        model_name = self._extract_model_name(response)
        tool_name = self._extract_tool_name(response)

        # 构建日志数据
        log_data = {
            "request_id": ctx.request_id,
            "module_name": ctx.module_name,
            "user_id": ctx.user_id,
            "conversation_id": ctx.conversation_id,
            "model_name": model_name,
            "tool_name": tool_name,
            "input_tokens": usage_data.get("input_tokens")
            or usage_data.get("prompt_tokens")
            if usage_data
            else None,
            "output_tokens": usage_data.get("output_tokens")
            or usage_data.get("completion_tokens")
            if usage_data
            else None,
            "total_tokens": usage_data.get("total_tokens") if usage_data else None,
            "duration_ms": duration_ms,
        }

        # 异步写入数据库
        self._schedule_write(log_data)

    def _get_first_generation(self, response: LLMResult) -> Any:
        """获取第一个 generation"""
        if response.generations and response.generations[0]:
            return response.generations[0][0]
        return None
    
    def _extract_usage(self, response: LLMResult) -> Optional[Dict[str, Any]]:
        """从 LLMResult 中提取 token 使用信息"""
        # 1. 标准 llm_output 格式 (非 streaming)
        if response.llm_output:
            if token_usage := response.llm_output.get("token_usage"):
                return token_usage
            if "total_tokens" in response.llm_output:
                return response.llm_output

        # 2. 从 usage_metadata 中提取 (streaming 模式 LangChain 会自动聚合)
        gen = self._get_first_generation(response)
        if gen:
            message = getattr(gen, "message", None)
            if message and hasattr(message, "usage_metadata"):
                metadata = getattr(message, "usage_metadata", None)
                if metadata:
                    # usage_metadata 可能是 dict 或 UsageMetadata 对象
                    if isinstance(metadata, dict):
                        return metadata
                    return {
                        "input_tokens": getattr(metadata, "input_tokens", None),
                        "output_tokens": getattr(metadata, "output_tokens", None),
                        "total_tokens": getattr(metadata, "total_tokens", None),
                    }
        return None

    def _extract_model_name(self, response: LLMResult) -> Optional[str]:
        """从 LLMResult 中提取模型名称"""
        # 1. 标准 llm_output 格式
        if response.llm_output:
            if model := response.llm_output.get(
                "model_name"
            ) or response.llm_output.get("model"):
                return model

        # 2. 从 response_metadata 中提取
        gen = self._get_first_generation(response)
        if gen:
            message = getattr(gen, "message", None)
            if message and hasattr(message, "response_metadata"):
                metadata = getattr(message, "response_metadata", None)
                if metadata:
                    if model := metadata.get("model_name") or metadata.get("model"):
                        return model

        return None

    def _extract_tool_name(self, response: LLMResult) -> Optional[str]:
        """从 LLMResult 中提取工具调用信息"""
        gen = self._get_first_generation(response)
        if not gen:
            return None

        # 从 message.tool_calls 中提取
        message = getattr(gen, "message", None)
        if message and hasattr(message, "tool_calls"):
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls and isinstance(tool_calls, list) and tool_calls:
                tool_call = tool_calls[0]
                if isinstance(tool_call, dict):
                    return tool_call.get("name") or tool_call.get("function", {}).get(
                        "name"
                    )
                elif hasattr(tool_call, "name"):
                    return tool_call.name

        return None

    def _schedule_write(self, log_data: Dict[str, Any]) -> None:
        """调度异步写入"""
        try:
            loop = _get_background_loop()
            future = asyncio.run_coroutine_threadsafe(self._write_to_db(log_data), loop)
            future.add_done_callback(self._on_write_done)
        except Exception as e:
            logger.warning("Failed to schedule LLM usage logging: %s", e)

    def _on_write_done(self, fut: Any) -> None:
        """写入完成回调"""
        try:
            fut.result()
        except Exception as e:
            logger.error("LLM usage write failed: %s", e)

    async def _write_to_db(self, log_data: Dict[str, Any]) -> None:
        """异步写入数据库"""
        try:
            from app.database.session import get_background_session_context
            from app.database.models import LLMUsageLogModel

            async with get_background_session_context() as session:
                log = LLMUsageLogModel(
                    id=uuid.uuid4(),
                    request_id=log_data["request_id"],
                    module_name=log_data["module_name"],
                    user_id=log_data.get("user_id"),
                    conversation_id=uuid.UUID(log_data["conversation_id"])
                    if log_data.get("conversation_id")
                    else None,
                    model_name=log_data.get("model_name"),
                    tool_name=log_data.get("tool_name"),
                    input_tokens=log_data.get("input_tokens"),
                    output_tokens=log_data.get("output_tokens"),
                    total_tokens=log_data.get("total_tokens"),
                    duration_ms=log_data.get("duration_ms"),
                )
                session.add(log)

            logger.debug(
                "LLM usage logged: module=%s, model=%s, tokens=%s",
                log_data.get("module_name"),
                log_data.get("model_name"),
                log_data.get("total_tokens"),
            )
        except Exception as e:
            logger.error("Failed to write LLM usage log: %s", e)

# 全局单例
_usage_callback = LLMUsageCallbackHandler()


def get_usage_callbacks() -> List[BaseCallbackHandler]:
    """获取 usage tracking callbacks 列表"""
    return [_usage_callback]