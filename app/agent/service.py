"""
AgentService - Agent 模块的主入口

职责单一：组装上下文 → 交给 Agent 执行
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict
from typing import Any, AsyncGenerator, Optional

# 默认截断阈值（字符数）
DEFAULT_TRUNCATE_THRESHOLD = 500
TRUNCATE_SUFFIX = "...[truncated]"

from app.agent.types import AgentChunk, AgentChunkType, AgentContext
from app.agent.agents import BaseAgent
from app.agent.context import AgentContextBuilder, AgentContextCompressor
from app.agent.database.repository import AgentRepository, agent_repository
from app.agent.registry import AgentHub
from app.agent.prompts import VISION_ANALYSIS_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


# 不截断的字段（用户输入和 LLM 输出）
EXCLUDE_TRUNCATE_KEYS = {"content"}


def _truncate_value(
    value: Any,
    threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
    exclude_keys: Optional[set[str]] = None,
    _current_key: Optional[str] = None,
) -> Any:
    """
    递归截断值中的字符串字段。

    Args:
        value: 任意值
        threshold: 字符串截断阈值
        exclude_keys: 不截断的字段名集合
        _current_key: 当前处理的字段名（内部使用）

    Returns:
        截断后的值
    """
    if exclude_keys is None:
        exclude_keys = EXCLUDE_TRUNCATE_KEYS

    if value is None:
        return None

    if isinstance(value, str):
        # 如果当前字段在排除列表中，不截断
        if _current_key in exclude_keys:
            return value
        if len(value) > threshold:
            return value[:threshold] + TRUNCATE_SUFFIX
        return value

    if isinstance(value, dict):
        return {
            k: _truncate_value(v, threshold, exclude_keys, _current_key=k)
            for k, v in value.items()
        }

    if isinstance(value, list):
        return [
            _truncate_value(item, threshold, exclude_keys, _current_key)
            for item in value
        ]

    # 其他类型（int, float, bool 等）直接返回
    return value


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return str(value)


def _build_fallback_agent(name: str) -> BaseAgent:
    from app.agent.agents import DefaultAgent
    from app.agent.types import AgentConfig

    return DefaultAgent(
        AgentConfig(
            name=name,
            description="Default assistant",
            system_prompt="You are a helpful assistant.",
        )
    )


class AgentService:
    """
    Agent 服务层。

    职责：
    1. 管理 Session 生命周期
    2. 组装上下文
    3. 调用 Agent 执行
    4. 保存消息和轨迹

        ┌─────────────────────────────────────────────────────────────────┐
    │                      AgentService.chat()                        │
    ├─────────────────────────────────────────────────────────────────┤
    │  1. 获取或创建 Session                                          │
    │       ↓                                                         │
    │  2. 发送 session 信息事件                                        │
    │       ↓                                                         │
    │  3. 组装上下文（AgentContextBuilder）                            │
    │       ↓                                                         │
    │  4. 图片分析（可选，调用 vision provider）                        │
    │       ↓                                                         │
    │  5. 获取 Agent（从 AgentHub）                                    │
    │       ↓                                                         │
    │  6. 创建 LLM invoker                                            │
    │       ↓                                                         │
    │  7. 执行 Agent（流式或非流式）                                    │
    │       ↓                                                         │
    │  8. 保存消息和轨迹到数据库                                        │
    │       ↓                                                         │
    │  9. 后台压缩上下文（异步任务）                                      │
    └─────────────────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        repository: Optional[AgentRepository] = None,
    ):
        """
        初始化服务。

        Args:
            repository: Agent 仓库
        """
        self.repository = repository or agent_repository
        self.context_builder = AgentContextBuilder(repository=self.repository)
        self.context_compressor = AgentContextCompressor()

    async def chat(
        self,
        session_id: Optional[str],
        user_id: str,
        message: str,
        agent_name: str = "default",
        streaming: bool = False,
        selected_tools: Optional[list[str]] = None,
        images: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        主入口：与 Agent 对话。

        Args:
            session_id: Session ID（可选，为空则创建新 Session）
            user_id: 用户 ID
            message: 用户消息
            agent_name: Agent 名称（用于选择 Agent，不存储在 Session 中）
            streaming: 是否启用流式输出
            selected_tools: 用户选择的工具列表（为空则使用默认工具）
            images: 用户上传的图片列表 [{data, mime_type}]

        Yields:
            SSE 格式的事件字符串
        """
        from app.llm.provider import LLMProvider
        from app.config import settings

        provider = LLMProvider(settings.llm)

        # Start timing
        thinking_start_time = time.time()
        thinking_end_time: Optional[float] = None
        answer_end_time: Optional[float] = None

        try:
            # 1. 获取或创建 Session（不再传入 agent_name）
            session = await self.repository.get_or_create_session(session_id, user_id)
            actual_session_id = str(session.id)

            # 2. 发送 session 信息
            yield self._format_event(
                "session",
                {
                    "session_id": actual_session_id,
                    "title": session.title,
                },
            )

            # 3. 组装上下文
            context = await self.context_builder.build(
                session,
                message,
                user_id,
                agent_name=agent_name,
                selected_tools=selected_tools,
                images=images,
            )

            tool_events = []

            # 4. If images present, run vision analysis and emit event
            if context.images:
                vision_result = await self._analyze_images(context)
                if vision_result:
                    vision_tool_call_id = f"vision-{uuid.uuid4().hex}"
                    context.vision_analysis = vision_result
                    context.vision_tool_call_id = vision_tool_call_id
                    tool_events.append(
                        {
                            "type": "tool_call",
                            "id": vision_tool_call_id,
                            "name": "vision_analysis",
                            "arguments": {
                                "image_count": len(context.images or []),
                            },
                        }
                    )
                    tool_events.append(
                        {
                            "type": "tool_result",
                            "tool_call_id": vision_tool_call_id,
                            "name": "vision_analysis",
                            "success": True,
                            "result": vision_result,
                            "error": None,
                        }
                    )
                    yield self._format_event("vision", vision_result)

            # 5. 获取 Agent
            agent = self._get_agent_or_fallback(agent_name)

            # 6. 创建 LLM invoker
            invoker = provider.create_invoker(
                llm_type="fast",
                streaming=streaming,
            )

            # 7. 执行 Agent
            response_content = ""
            trace_steps = []

            if streaming:
                agent_generator = agent.run_streaming(invoker, context)
            else:
                agent_generator = agent.run(invoker, context)

            async for chunk in agent_generator:
                # 处理不同类型的 chunk
                if chunk.type == AgentChunkType.CONTENT:
                    if thinking_end_time is None:
                        thinking_end_time = time.time()
                    response_content += chunk.data
                    yield self._format_event(
                        "text",
                        {
                            "content": chunk.data,
                        },
                    )

                elif chunk.type == AgentChunkType.TOOL_CALL:
                    tool_call = chunk.data
                    iteration = len(
                        [t for t in trace_steps if t.get("action") == "tool_call"]
                    )
                    tool_events.append(
                        {
                            "type": "tool_call",
                            "id": tool_call.id,
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                        }
                    )
                    trace_steps.append(
                        {
                            "error": None,
                            "action": "tool_call",
                            "content": None,
                            "iteration": iteration,
                            "timestamp": chunk.data.id
                            if hasattr(chunk.data, "id")
                            else None,
                            "tool_calls": [
                                {
                                    "name": tool_call.name,
                                    "arguments": tool_call.arguments,
                                }
                            ],
                        }
                    )
                    yield self._format_event(
                        "tool_call",
                        {
                            "id": tool_call.id,
                            "name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "iteration": iteration,
                        },
                    )

                elif chunk.type == AgentChunkType.TOOL_RESULT:
                    result = chunk.data
                    iteration = len(
                        [t for t in trace_steps if t.get("action") == "tool_result"]
                    )
                    tool_events.append(
                        {
                            "type": "tool_result",
                            "tool_call_id": result.tool_call_id,
                            "name": result.name,
                            "success": result.success,
                            "result": result.result,
                            "error": result.error,
                        }
                    )
                    trace_steps.append(
                        {
                            "error": result.error if not result.success else None,
                            "action": "tool_result",
                            "content": result.result,
                            "iteration": iteration,
                            "timestamp": None,
                            "tool_calls": [
                                {
                                    "name": result.name,
                                    "arguments": {},
                                }
                            ],
                        }
                    )
                    yield self._format_event(
                        "tool_result",
                        {
                            "name": result.name,
                            "success": result.success,
                            "result": result.result,
                            "error": result.error,
                            "iteration": iteration,
                        },
                    )

                elif chunk.type == AgentChunkType.TRACE:
                    trace_step = chunk.data
                    trace_steps.append(asdict(trace_step))
                    yield self._format_event("trace", asdict(trace_step))

                elif chunk.type == AgentChunkType.ERROR:
                    yield self._format_event("error", chunk.data)

                elif chunk.type == AgentChunkType.DONE:
                    answer_end_time = time.time()

                    thinking_duration_ms = None
                    answer_duration_ms = None

                    # Agent 耗时统计规则：
                    # - thinking：从开始执行到首个 CONTENT 事件产生
                    # - answer：从首个 CONTENT 事件产生到执行结束
                    # - 若未产生 CONTENT，则全部耗时均计入 thinking
                    if thinking_end_time is not None:
                        thinking_duration_ms = int(
                            (thinking_end_time - thinking_start_time) * 1000
                        )
                        answer_duration_ms = (
                            int((answer_end_time - thinking_end_time) * 1000)
                            if answer_end_time > thinking_end_time
                            else 0
                        )
                    else:
                        thinking_duration_ms = int(
                            (answer_end_time - thinking_start_time) * 1000
                        )

                    yield self._format_event(
                        "done",
                        {
                            "session_id": actual_session_id,
                            "thinking_duration_ms": thinking_duration_ms,
                            "answer_duration_ms": answer_duration_ms,
                            **chunk.data,
                        },
                    )

            # 8. 保存消息（所有执行过程都存储在 trace 中）
            if answer_end_time is None:
                answer_end_time = time.time()

            user_message_content = message

            # 保存用户图片消息
            user_trace = None
            if context.images:
                image_sources = []
                for img in context.images:
                    if img.get("url"):
                        image_sources.append({
                            "type": "image",
                            "url": img.get("url"),
                            "display_url": img.get("display_url"),
                            "thumb_url": img.get("thumb_url"),
                        })
                if image_sources:
                    user_trace = image_sources

            # 保存用户消息
            await self.repository.save_message(
                actual_session_id,
                "user",
                user_message_content,
                trace=user_trace,
            )

            # 保存工具调用结果
            await self._save_tool_events(
                actual_session_id,
                tool_events,
                trace_steps,
            )

            final_thinking_ms = None
            final_answer_ms = None
            if thinking_end_time is not None:
                final_thinking_ms = int(
                    (thinking_end_time - thinking_start_time) * 1000
                )
                final_answer_ms = (
                    int((answer_end_time - thinking_end_time) * 1000)
                    if answer_end_time > thinking_end_time
                    else 0
                )
            else:
                final_thinking_ms = int((answer_end_time - thinking_start_time) * 1000)

            await self.repository.save_message(
                actual_session_id,
                "assistant",
                response_content,
                trace=trace_steps if trace_steps else None,
                thinking_duration_ms=final_thinking_ms,
                answer_duration_ms=final_answer_ms,
            )

            # 8. 后台压缩上下文
            asyncio.create_task(
                self.context_compressor.maybe_compress(
                    actual_session_id,
                    self.repository,
                    user_id,
                )
            )

        except Exception as e:
            logger.exception(f"AgentService.chat failed: {e}")
            yield self._format_event("error", {"error": str(e)})

    def _get_agent_or_fallback(self, agent_name: str) -> BaseAgent:
        try:
            return AgentHub.get_agent(agent_name)
        except KeyError:
            logger.warning(f"Agent {agent_name} not found, using fallback")
            return _build_fallback_agent("default")

    @staticmethod
    def _tool_call_message_payload(event: dict) -> dict:
        return {
            "id": event.get("id") or "",
            "type": "function",
            "function": {
                "name": event.get("name") or "",
                "arguments": json.dumps(
                    event.get("arguments") or {},
                    ensure_ascii=False,
                    default=str,
                ),
            },
        }

    @staticmethod
    def _find_tool_call_batches(
        tool_events: list[dict],
        trace_steps: list[dict],
    ) -> dict[str, list[str]]:
        """
        找到同一批次的工具调用
        核心原理：
        - trace_steps 记录了 LLM 的执行追踪，每个 tool_call 动作可能包含多个工具调用（同批次）
        - tool_events 是分散的工具调用事件列表
        - 通过匹配 tool_name + arguments，将分散的事件关联到同一批次
        """
        batches: dict[str, list[str]] = {}
        consumed: set[int] = set()
        search_start = 0

        for step in trace_steps:
            if step.get("action") != "tool_call":
                continue

            trace_tool_calls = step.get("tool_calls") or []
            if len(trace_tool_calls) <= 1:
                continue

            matched_indexes: list[int] = []
            matched_ids: list[str] = []
            cursor = search_start

            for trace_call in trace_tool_calls:
                match_index = None
                for index in range(cursor, len(tool_events)):
                    if index in consumed:
                        continue
                    event = tool_events[index]
                    if event.get("type") != "tool_call":
                        continue
                    if (
                        event.get("name") == trace_call.get("name")
                        and (event.get("arguments") or {})
                        == (trace_call.get("arguments") or {})
                    ):
                        match_index = index
                        break

                if match_index is None:
                    matched_indexes = []
                    matched_ids = []
                    break

                # 记录匹配结果
                matched_indexes.append(match_index)
                matched_ids.append(tool_events[match_index].get("id") or "")
                cursor = match_index + 1

            if not matched_ids:
                continue

            for index in matched_indexes:
                consumed.add(index)

            search_start = max(matched_indexes) + 1
            # 构建批次映射：每个tool_call_id都映射到同一批次的所有ID
            for tool_call_id in matched_ids:
                batches[tool_call_id] = matched_ids

        return batches

    async def _save_tool_events(
        self,
        session_id: str,
        tool_events: list[dict],
        trace_steps: list[dict],
    ) -> None:
        trace_batches = self._find_tool_call_batches(tool_events, trace_steps)
        saved_tool_call_ids: set[str] = set()

        for index, event in enumerate(tool_events):
            if event.get("type") == "tool_call":
                tool_call_id = event.get("id") or ""
                if tool_call_id in saved_tool_call_ids:
                    continue

                batch_ids = trace_batches.get(tool_call_id)
                if batch_ids:
                    batch_events = [
                        candidate
                        for candidate in tool_events
                        if candidate.get("type") == "tool_call"
                        and (candidate.get("id") or "") in batch_ids
                    ]
                else:
                    batch_events = [event]
                    for candidate in tool_events[index + 1:]:
                        if candidate.get("type") != "tool_call":
                            break
                        batch_events.append(candidate)

                await self.repository.save_message(
                    session_id,
                    "assistant",
                    "",
                    tool_calls=[
                        self._tool_call_message_payload(tool_event)
                        for tool_event in batch_events
                    ],
                )
                saved_tool_call_ids.update(
                    tool_event.get("id") or "" for tool_event in batch_events
                )
                continue

            if event.get("type") == "tool_result":
                if event.get("success"):
                    result_content = json.dumps(
                        event.get("result"),
                        ensure_ascii=False,
                        default=str,
                    )
                else:
                    result_content = f"Error: {event.get('error') or 'Unknown error'}"
                await self.repository.save_message(
                    session_id,
                    "tool",
                    result_content,
                    tool_call_id=event.get("tool_call_id"),
                    tool_name=event.get("name"),
                )

    async def _analyze_images(self, context: AgentContext) -> Optional[dict]:
        """
        使用vision provider对图片进行分析.

        Args:
            context: 包含图片信息的 Agent 上下文

        Returns:
            分析结果 dict
        """
        if not context.images:
            return None

        try:
            from app.vision.provider import vision_provider, ImageInput

            if not vision_provider.is_enabled:
                logger.warning("Vision provider is not enabled, skipping image analysis")
                return None

            image_inputs = []
            for img in context.images:
                image_inputs.append(
                    ImageInput.from_base64(img["data"], img["mime_type"])
                )

            recent_messages = context.recent_messages if context.recent_messages else []
            recent_text = "\n".join(
                [
                    f"{msg.get('role')}: {msg.get('content', '')}"
                    for msg in recent_messages
                ]
            )

            prompt = VISION_ANALYSIS_PROMPT_TEMPLATE.format(
                recent_text=recent_text or "无",
                current_message=context.current_message,
            )

            result_str = await vision_provider.analyze(
                text=prompt,
                images=image_inputs,
                user_id=context.user_id,
                conversation_id=context.session_id,
            )

            import json
            try:
                result = json.loads(result_str)
                return result
            except json.JSONDecodeError:
                return {
                    "description": result_str,
                    "is_food_related": False,
                    "confidence": 0.5,
                }

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}", exc_info=True)
            return None

    async def get_session(self, session_id: str) -> Optional[dict]:
        """获取 Session 信息。"""
        session = await self.repository.get_session(session_id)
        if session:
            return session.to_dict()
        return None

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """列出 Sessions。"""
        return await self.repository.list_sessions(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def delete_session(self, session_id: str) -> bool:
        """删除 Session。"""
        return await self.repository.delete_session(session_id)

    async def update_session_title(self, session_id: str, title: str) -> bool:
        """更新 Session 标题。"""
        return await self.repository.update_session_title(session_id, title)

    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        truncate_threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
    ) -> list[dict]:
        """
        获取 Session 的消息历史。

        Args:
            session_id: Session ID
            limit: 返回消息数量限制
            truncate_threshold: 截断阈值

        Returns:
            截断后的消息列表
        """
        messages = await self.repository.get_messages(session_id, limit)
        # 对每条消息的内容进行截断
        return [_truncate_value(msg.to_dict(), truncate_threshold) for msg in messages]

    def _format_event(
        self,
        event_type: str,
        data: dict,
        truncate_threshold: int = DEFAULT_TRUNCATE_THRESHOLD,
    ) -> str:
        """
        格式化 SSE 事件。

        Args:
            event_type: 事件类型
            data: 事件数据
            truncate_threshold: 截断阈值

        Returns:
            SSE 格式字符串
        """
        # 截断数据中的字符串字段
        truncated_data = _truncate_value(data, truncate_threshold)
        safe_data = _sanitize_value(truncated_data)
        payload = {"type": event_type, **safe_data}
        return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


# 单例
agent_service = AgentService()
