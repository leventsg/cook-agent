# app/agent/agents/base.py
"""
BaseAgent 和 AgentLoop

Agent 的核心执行逻辑，实现 ReAct 模式的自主执行循环。
"""

import asyncio
import json
import logging
from abc import ABC
from typing import Any, AsyncGenerator

from app.agent.types import (
    AgentChunk,
    AgentChunkType,
    AgentConfig,
    AgentContext,
    ToolCallInfo,
    ToolResult,
    ToolResultInfo,
    TraceStep,
)
from app.agent.registry import AgentHub
from app.agent.context import AgentContextBuilder
from app.llm.provider import LLMInvoker

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Agent 基类。

    所有 Agent 必须继承此类。Agent 采用 ReAct 模式执行：
    1. 思考（Reasoning）
    2. 行动（Action）- 调用 Tool
    3. 观察（Observation）- 获取 Tool 结果
    4. 重复直到任务完成
    """

    def __init__(self, config: AgentConfig):
        """
        初始化 Agent。

        Args:
            config: Agent 配置
        """
        self.config = config
        self.name = config.name
        self.description = config.description
        self.system_prompt = config.system_prompt
        self.tools = config.tools
        self.max_iterations = config.max_iterations

        # 上下文构建器
        self.context_builder = AgentContextBuilder()

    async def run(
        self,
        invoker: Any,  # LLMInvoker
        context: AgentContext,
    ) -> AsyncGenerator[AgentChunk, None]:
        """
        执行 Agent ReAct 循环。

        Args:
            invoker: LLM 调用器
            context: Agent 上下文

        Yields:
            AgentChunk: 执行过程中的输出块
        """
        from app.llm.context import llm_context

        # 构建初始消息
        messages = self.context_builder.build_messages(context)

        # 获取 Tool schemas
        tool_schemas = context.available_tools

        # 从 tool_schemas 提取工具名称，创建对应的 Tool 执行器
        # 这样 executor 的工具集和 LLM 看到的 tools 完全一致
        # 传入 user_id 以支持 Subagent Tools
        selected_tool_names = (
            [t["function"]["name"] for t in tool_schemas] if tool_schemas else []
        )
        tool_executor = AgentHub.create_tool_executor(
            selected_tool_names if selected_tool_names else None,
            user_id=context.user_id,
        )

        # ReAct 循环
        for iteration in range(self.max_iterations):
            try:
                # 调用 LLM
                with llm_context(
                    f"agent:{self.name}", context.user_id, context.session_id
                ):
                    if tool_schemas:
                        # 使用 function calling
                        response = await self._invoke_with_tools(
                            invoker, messages, tool_schemas
                        )
                    else:
                        response = await invoker.ainvoke(messages)

                # 检查是否有 Tool 调用
                tool_calls = self._extract_tool_calls(response)

                if tool_calls:
                    # 有 Tool 调用
                    tool_results = []

                    for tool_call in tool_calls:
                        # 发送 Tool 调用事件
                        yield AgentChunk(
                            type=AgentChunkType.TOOL_CALL,
                            data=tool_call,
                        )

                        # 执行 Tool（支持 Subagent 流式轨迹）
                        result = None
                        async for event_type, payload in self._execute_tool_call(
                            tool_executor,
                            tool_call,
                        ):
                            if event_type == "trace":
                                yield AgentChunk(
                                    type=AgentChunkType.TRACE,
                                    data=payload,
                                )
                            else:
                                result = payload
                        if result is None:
                            result = ToolResult(
                                success=False,
                                error="Tool execution returned no result",
                            )

                        # 构建结果信息
                        result_info = ToolResultInfo(
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                            success=result.success,
                            result=result.data,
                            error=result.error,
                        )
                        tool_results.append(result_info)

                        # 发送 Tool 结果事件
                        yield AgentChunk(
                            type=AgentChunkType.TOOL_RESULT,
                            data=result_info,
                        )

                    # 将 Tool 调用和结果加入消息历史
                    messages = self._append_tool_messages(
                        messages, response, tool_results
                    )

                    # 发送轨迹事件
                    yield AgentChunk(
                        type=AgentChunkType.TRACE,
                        data=TraceStep(
                            iteration=iteration,
                            action="tool_call",
                            tool_calls=[
                                {
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                }
                                for tc in tool_calls
                            ],
                        ),
                    )

                else:
                    # 无 Tool 调用，输出最终响应
                    content = self._extract_content(response)

                    yield AgentChunk(
                        type=AgentChunkType.CONTENT,
                        data=content,
                    )

                    yield AgentChunk(
                        type=AgentChunkType.TRACE,
                        data=TraceStep(
                            iteration=iteration,
                            action="finish",
                            content=content,
                        ),
                    )

                    # 发送完成信号
                    yield AgentChunk(
                        type=AgentChunkType.DONE,
                        data={"iterations": iteration + 1},
                    )

                    break

            except Exception as e:
                logger.exception(f"Agent iteration {iteration} failed: {e}")

                yield AgentChunk(
                    type=AgentChunkType.ERROR,
                    data={"error": str(e), "iteration": iteration},
                )

                yield AgentChunk(
                    type=AgentChunkType.TRACE,
                    data=TraceStep(
                        iteration=iteration,
                        action="error",
                        error=str(e),
                    ),
                )

                break

        else:
            # 达到最大迭代次数
            logger.warning(f"Agent {self.name} reached max iterations")
            yield AgentChunk(
                type=AgentChunkType.ERROR,
                data={
                    "error": "Max iterations reached",
                    "iteration": self.max_iterations,
                },
            )

    async def run_streaming(
        self,
        invoker: LLMInvoker,
        context: AgentContext,
    ) -> AsyncGenerator[AgentChunk, None]:
        """
        流式执行 Agent（支持内容流式输出）。

        Args:
            invoker: LLM 调用器（需启用 streaming=True）
            context: Agent 上下文

        Yields:
            AgentChunk: 执行过程中的输出块
        """
        from app.llm.context import llm_context

        messages = self.context_builder.build_messages(context)
        tool_schemas = context.available_tools

        # 从 tool_schemas 提取工具名称，创建对应的 Tool 执行器
        # 传入 user_id 以支持 Subagent Tools
        selected_tool_names = (
            [t["function"]["name"] for t in tool_schemas] if tool_schemas else []
        )
        tool_executor = AgentHub.create_tool_executor(
            selected_tool_names if selected_tool_names else None,
            user_id=context.user_id,
        )

        for iteration in range(self.max_iterations):
            try:
                with llm_context(
                    f"agent:{self.name}", context.user_id, context.session_id
                ):
                    if tool_schemas:
                        # 流式调用（带 Tool）
                        collected_content = ""
                        collected_tool_calls = []

                        async for chunk in self._stream_with_tools(
                            invoker, messages, tool_schemas
                        ):
                            if hasattr(chunk, "content") and chunk.content:
                                collected_content += chunk.content
                                yield AgentChunk(
                                    type=AgentChunkType.CONTENT,
                                    data=chunk.content,
                                )

                            # Collect tool calls from streaming chunks
                            # LangChain uses tool_call_chunks for streaming partial data
                            if (
                                hasattr(chunk, "tool_call_chunks")
                                and chunk.tool_call_chunks
                            ):
                                for tc in chunk.tool_call_chunks:
                                    collected_tool_calls.append(tc)
                            elif hasattr(chunk, "tool_calls") and chunk.tool_calls:
                                for tc in chunk.tool_calls:
                                    collected_tool_calls.append(tc)

                        # 处理收集的 Tool 调用
                        if collected_tool_calls:
                            tool_calls = self._parse_streaming_tool_calls(
                                collected_tool_calls
                            )
                            tool_results = []

                            for tool_call in tool_calls:
                                yield AgentChunk(
                                    type=AgentChunkType.TOOL_CALL,
                                    data=tool_call,
                                )

                                result = None
                                async for event_type, payload in self._execute_tool_call(
                                    tool_executor,
                                    tool_call,
                                ):
                                    if event_type == "trace":
                                        yield AgentChunk(
                                            type=AgentChunkType.TRACE,
                                            data=payload,
                                        )
                                    else:
                                        result = payload
                                if result is None:
                                    result = ToolResult(
                                        success=False,
                                        error="Tool execution returned no result",
                                    )

                                result_info = ToolResultInfo(
                                    tool_call_id=tool_call.id,
                                    name=tool_call.name,
                                    success=result.success,
                                    result=result.data,
                                    error=result.error,
                                )
                                tool_results.append(result_info)

                                yield AgentChunk(
                                    type=AgentChunkType.TOOL_RESULT,
                                    data=result_info,
                                )

                            # 构建消息继续对话
                            messages = self._append_tool_messages_streaming(
                                messages, collected_content, tool_calls, tool_results
                            )

                            yield AgentChunk(
                                type=AgentChunkType.TRACE,
                                data=TraceStep(
                                    iteration=iteration,
                                    action="tool_call",
                                    tool_calls=[
                                        {
                                            "name": tc.name,
                                            "arguments": tc.arguments,
                                        }
                                        for tc in tool_calls
                                    ],
                                ),
                            )
                        else:
                            # 无 Tool 调用，结束
                            yield AgentChunk(
                                type=AgentChunkType.TRACE,
                                data=TraceStep(
                                    iteration=iteration,
                                    action="finish",
                                    content=collected_content,
                                ),
                            )
                            yield AgentChunk(
                                type=AgentChunkType.DONE,
                                data={"iterations": iteration + 1},
                            )
                            break
                    else:
                        # 无 Tool，直接流式输出
                        async for chunk in invoker.astream(messages):
                            if hasattr(chunk, "content") and chunk.content:
                                yield AgentChunk(
                                    type=AgentChunkType.CONTENT,
                                    data=chunk.content,
                                )

                        yield AgentChunk(
                            type=AgentChunkType.DONE,
                            data={"iterations": iteration + 1},
                        )
                        break

            except Exception as e:
                logger.exception(f"Agent streaming iteration {iteration} failed: {e}")
                yield AgentChunk(
                    type=AgentChunkType.ERROR,
                    data={"error": str(e), "iteration": iteration},
                )
                break
        else:
            # 达到最大迭代次数
            logger.warning(f"Agent {self.name} reached max iterations")
            yield AgentChunk(
                type=AgentChunkType.ERROR,
                data={"error": "Max iterations reached", "iteration": self.max_iterations},
            )

    # ==================== 辅助方法 ====================

    async def _execute_tool_call(
        self,
        tool_executor,
        tool_call: ToolCallInfo,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        if not tool_executor:
            yield (
                "result",
                ToolResult(success=False, error="Tool executor unavailable"),
            )
            return
        if tool_call.name.startswith("subagent_"):
            queue: asyncio.Queue[TraceStep] = asyncio.Queue()

            async def handle_event(step: TraceStep) -> None:
                await queue.put(step)

            task = asyncio.create_task(
                tool_executor.execute(
                    tool_call.name,
                    tool_call.arguments,
                    event_handler=handle_event,
                )
            )
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    step = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield ("trace", step)
                except asyncio.TimeoutError:
                    await asyncio.sleep(0)

            result = await task
            yield ("result", result)
            return

        result = await tool_executor.execute(
            tool_call.name,
            tool_call.arguments,
        )
        yield ("result", result)

    async def _invoke_with_tools(
        self,
        invoker: LLMInvoker,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> Any:
        """使用 Tool 调用 LLM。"""
        # 使用 LLMInvoker 的方法来确保 callbacks 被正确附加
        return await invoker.ainvoke_with_tools(messages, tool_schemas)

    async def _stream_with_tools(
        self,
        invoker: LLMInvoker,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> AsyncGenerator[Any, None]:
        """流式调用 LLM（带 Tool）。"""
        # 使用 LLMInvoker 的方法来确保 callbacks 被正确附加
        async for chunk in invoker.astream_with_tools(messages, tool_schemas):
            yield chunk

    def _extract_tool_calls(self, response: Any) -> list[ToolCallInfo]:
        """从 LLM 响应中提取 Tool 调用。"""
        tool_calls = []

        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_calls.append(
                    ToolCallInfo(
                        id=tc.get("id", ""),
                        name=tc.get("name", ""),
                        arguments=tc.get("args", {}),
                    )
                )

        return tool_calls

    def _parse_streaming_tool_calls(
        self,
        collected_tool_calls: list,
    ) -> list[ToolCallInfo]:
        """解析流式收集的 Tool 调用。"""
        # 流式 Tool 调用需要合并
        tool_calls_map: dict[int, dict] = {}

        for tc in collected_tool_calls:
            # Handle both dict and object formats (ToolCallChunk)
            if isinstance(tc, dict):
                index = tc.get("index", 0)
                tc_id = tc.get("id") or ""
                tc_name = tc.get("name") or ""
                tc_args = tc.get("args") or ""
            else:
                # Object format (ToolCallChunk from LangChain)
                index = getattr(tc, "index", 0) or 0
                tc_id = getattr(tc, "id", "") or ""
                tc_name = getattr(tc, "name", "") or ""
                tc_args = getattr(tc, "args", "") or ""

            if index not in tool_calls_map:
                tool_calls_map[index] = {
                    "id": "",
                    "name": "",
                    "args": "",
                }

            if tc_id:
                tool_calls_map[index]["id"] = tc_id
            if tc_name:
                tool_calls_map[index]["name"] = tc_name
            if tc_args:
                tool_calls_map[index]["args"] += tc_args

        result = []
        for tc in tool_calls_map.values():
            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse tool args: {tc['args']}")
                args = {}

            result.append(
                ToolCallInfo(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=args,
                )
            )

        return result

    def _extract_content(self, response: Any) -> str:
        """从 LLM 响应中提取文本内容。"""
        if hasattr(response, "content"):
            return response.content
        return str(response)

    def _append_tool_messages(
        self,
        messages: list[dict],
        response: Any,
        tool_results: list[ToolResultInfo],
    ) -> list[dict]:
        """将 Tool 调用和结果添加到消息历史。"""
        # 添加 assistant 消息（包含 tool_calls）
        assistant_content = self._extract_content(response)
        assistant_msg = {
            "role": "assistant",
            "content": assistant_content or "",
        }

        if hasattr(response, "tool_calls") and response.tool_calls:
            assistant_msg["tool_calls"] = response.tool_calls
            assistant_msg["content"] = None # type: ignore

        messages.append(assistant_msg)

        # 添加 tool 结果消息
        for result in tool_results:
            result_content = (
                json.dumps(result.result, ensure_ascii=False)
                if result.success
                else f"Error: {result.error}"
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "name": result.name,
                    "content": result_content,
                }
            )

        return messages

    def _append_tool_messages_streaming(
        self,
        messages: list[dict],
        content: str,
        tool_calls: list[ToolCallInfo],
        tool_results: list[ToolResultInfo],
    ) -> list[dict]:
        """将流式收集的 Tool 调用和结果添加到消息历史。"""
        # 添加 assistant 消息
        assistant_msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ],
        }
        messages.append(assistant_msg)

        # 添加 tool 结果消息
        for result in tool_results:
            result_content = (
                json.dumps(result.result, ensure_ascii=False)
                if result.success
                else f"Error: {result.error}"
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "name": result.name,
                    "content": result_content,
                }
            )

        return messages


__all__ = ["BaseAgent"]
