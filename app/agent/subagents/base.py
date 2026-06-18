# app/agent/subagents/base.py
"""
Subagent 基类

Subagent 是专业化的子代理，可以被主 Agent 作为 Tool 调用。
每个 Subagent 有自己的 prompt、可用工具集、最大迭代次数等配置。
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.agent.types import ToolResult, TraceStep
from app.agent.registry import AgentHub

logger = logging.getLogger(__name__)


@dataclass
class SubagentConfig:
    """
    Subagent 配置。

    Attributes:
        name: Subagent 唯一标识名
        display_name: 显示名称（用于 UI）
        description: 描述（用于主 Agent 理解何时调用此 Subagent）
        system_prompt: Subagent 的系统提示词
        tools: Subagent 可使用的工具名称列表
        max_iterations: 最大迭代次数
        enabled: 是否启用
        builtin: 是否为内置 Subagent（内置不可删除）
        category: 分类（如 "diet", "fitness", "general"）
    """

    name: str
    display_name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    max_iterations: int = 10
    enabled: bool = True
    builtin: bool = False
    category: str = "general"

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "max_iterations": self.max_iterations,
            "enabled": self.enabled,
            "builtin": self.builtin,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubagentConfig":
        """从字典创建配置。"""
        return cls(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            description=data["description"],
            system_prompt=data["system_prompt"],
            tools=data.get("tools", []),
            max_iterations=data.get("max_iterations", 10),
            enabled=data.get("enabled", True),
            builtin=data.get("builtin", False),
            category=data.get("category", "general"),
        )


class BaseSubagent(ABC):
    """
    Subagent 基类。

    Subagent 与普通 Agent 的区别：
    1. Subagent 被主 Agent 作为 Tool 调用
    2. Subagent 接收任务描述，返回结构化结果
    3. Subagent 有自己独立的工具集
    4. Subagent 不管理对话历史，每次调用是独立的
    """

    def __init__(self, config: SubagentConfig):
        """
        初始化 Subagent。

        Args:
            config: Subagent 配置
        """
        self.config = config
        self.name = config.name
        self.description = config.description
        self.system_prompt = config.system_prompt
        self.tools = config.tools
        self.max_iterations = config.max_iterations

    @abstractmethod
    async def execute(
        self,
        task: str,
        user_id: Optional[str] = None,
        background: Optional[str] = None,
        event_handler: Optional[Callable[[TraceStep], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        执行 Subagent 任务。

        Args:
            task: 任务描述（由主 Agent 传入）
            user_id: 用户 ID（用于获取用户相关信息）
            background: 额外背景信息（可选）

        Returns:
            ToolResult: 执行结果
        """
        pass

    async def run_with_tools(
        self,
        task: str,
        user_id: Optional[str] = None,
        background: Optional[str] = None,
        event_handler: Optional[Callable[[TraceStep], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        使用工具执行任务的通用实现。

        这是一个简化版的 ReAct 循环，用于 Subagent 执行任务。

        Args:
            task: 任务描述
            user_id: 用户 ID
            background: 额外背景

        Returns:
            ToolResult: 执行结果
        """
        from app.llm.provider import LLMProvider
        from app.llm.context import llm_context
        from app.config import settings

        provider = LLMProvider(settings.llm)
        invoker = provider.create_invoker(llm_type="fast")

        # 构建系统提示词
        system_content = self.system_prompt
        if background:
            system_content += f"\n\n## 背景信息\n{background}"

        # 构建消息
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": task},
        ]

        # 获取 Tool schemas
        tool_schemas = (
            AgentHub.get_tool_schemas(self.tools, user_id=user_id)
            if self.tools
            else []
        )

        # 创建 Tool 执行器
        tool_executor = (
            AgentHub.create_tool_executor(self.tools, user_id=user_id)
            if self.tools
            else None
        )

        # ReAct 循环
        for iteration in range(self.max_iterations):
            try:
                with llm_context(f"subagent:{self.name}", user_id, None):
                    if tool_schemas:
                        response = await invoker.ainvoke_with_tools(
                            messages, tool_schemas
                        )
                    else:
                        response = await invoker.ainvoke(messages)

                # 检查是否有 Tool 调用
                tool_calls = self._extract_tool_calls(response)

                if tool_calls and tool_executor:
                    for tc in tool_calls:
                        await self._emit_event(
                            event_handler,
                            TraceStep(
                                iteration=iteration,
                                action="tool_call",
                                tool_calls=[
                                    {"name": tc["name"], "arguments": tc["arguments"]}
                                ],
                                source="subagent",
                                subagent_name=self.name,
                            ),
                        )
                    # 执行 Tool 调用
                    tool_results = []
                    for tc in tool_calls:
                        result = await tool_executor.execute(
                            tc["name"], tc["arguments"]
                        )
                        await self._emit_event(
                            event_handler,
                            TraceStep(
                                iteration=iteration,
                                action="tool_result",
                                content=result.data if result.success else result.error,
                                error=result.error if not result.success else None,
                                tool_calls=[{"name": tc["name"], "arguments": {}}],
                                source="subagent",
                                subagent_name=self.name,
                            ),
                        )
                        tool_results.append(
                            {
                                "tool_call_id": tc["id"],
                                "name": tc["name"],
                                "result": result.data
                                if result.success
                                else result.error,
                                "success": result.success,
                            }
                        )

                    # 将结果加入消息历史
                    messages = self._append_tool_messages(
                        messages, response, tool_results
                    )
                else:
                    # 无 Tool 调用，返回最终结果
                    content = self._extract_content(response)
                    await self._emit_event(
                        event_handler,
                        TraceStep(
                            iteration=iteration,
                            action="subagent_output",
                            content=content,
                            source="subagent",
                            subagent_name=self.name,
                        ),
                    )
                    return ToolResult(
                        success=True,
                        data={
                            "result": content,
                            "iterations": iteration + 1,
                        },
                    )

            except Exception as e:
                logger.exception(
                    f"Subagent {self.name} iteration {iteration} failed: {e}"
                )
                await self._emit_event(
                    event_handler,
                    TraceStep(
                        iteration=iteration,
                        action="error",
                        error=str(e),
                        source="subagent",
                        subagent_name=self.name,
                    ),
                )
                return ToolResult(
                    success=False,
                    error=f"Subagent execution failed: {str(e)}",
                )

        # 达到最大迭代次数
        logger.warning(f"Subagent {self.name} reached max iterations")
        return ToolResult(
            success=False,
            error="Max iterations reached without completing the task",
        )

    async def _emit_event(
        self,
        handler: Optional[Callable[[TraceStep], Awaitable[None]]],
        step: TraceStep,
    ) -> None:
        if not handler:
            return
        try:
            await handler(step)
        except Exception as e:
            logger.debug("Subagent event handler failed: %s", e)

    def _extract_tool_calls(self, response: Any) -> list[dict]:
        """从 LLM 响应中提取 Tool 调用。"""
        tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "arguments": tc.get("args", {}),
                    }
                )
        return tool_calls

    def _extract_content(self, response: Any) -> str:
        """从 LLM 响应中提取文本内容。"""
        if hasattr(response, "content"):
            return response.content
        return str(response)

    def _append_tool_messages(
        self,
        messages: list[dict],
        response: Any,
        tool_results: list[dict],
    ) -> list[dict]:
        """将 Tool 调用和结果添加到消息历史。"""
        # 添加 assistant 消息
        if hasattr(response, "tool_calls") and response.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": response.tool_calls,
                }
            )

        # 添加 tool 结果消息
        for result in tool_results:
            result_content = (
                json.dumps(result["result"], ensure_ascii=False, default=str)
                if result["success"]
                else f"Error: {result['result']}"
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "name": result["name"],
                    "content": result_content,
                }
            )

        return messages


__all__ = ["BaseSubagent", "SubagentConfig"]
