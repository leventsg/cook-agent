# app/agent/subagents/tool.py
"""
SubagentTool - 将 Subagent 包装为 Tool

这个模块提供了将 Subagent 转换为 Tool 的机制，使主 Agent 可以通过
标准的 function calling 机制调用 Subagent。
"""

import json
import logging
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult, TraceStep

if TYPE_CHECKING:
    from app.agent.subagents.base import BaseSubagent, SubagentConfig

logger = logging.getLogger(__name__)


class SubagentTool(BaseTool):
    """
    Subagent 的 Tool 包装器。

    将 Subagent 包装为标准的 Tool，使其可以被主 Agent 调用。

    工作流程：
    1. 主 Agent 通过 function calling 调用 SubagentTool
    2. SubagentTool.execute() 被触发
    3. 内部调用 Subagent.execute() 执行实际任务
    4. 返回结果给主 Agent
    """

    def __init__(self, subagent: "BaseSubagent"):
        """
        初始化 SubagentTool。

        Args:
            subagent: 要包装的 Subagent 实例
        """
        self.subagent = subagent

        # 设置 Tool 属性
        # 使用 subagent_ 前缀区分普通 Tool
        self.name = f"subagent_{subagent.name}"
        self.description = self._build_description(subagent)
        self.parameters = self._build_parameters()

        super().__init__()

    def _build_description(self, subagent: "BaseSubagent") -> str:
        """构建 Tool 描述。"""
        return (
            f"调用专业子代理「{subagent.config.display_name}」来处理任务。\n"
            f"{subagent.description}\n"
            f"当用户的请求需要 {subagent.config.display_name} 的专业能力时，应调用此工具。"
        )

    def _build_parameters(self) -> dict:
        """构建参数 schema。"""
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "需要子代理完成的具体任务描述，应包含足够的上下文信息",
                },
                "background": {
                    "type": "string",
                    "description": "额外背景信息（可选），由主 Agent 汇总后提供",
                },
            },
            "required": ["task"],
        }

    async def execute(
        self,
        task: str = "",
        background: Optional[str] = None,
        user_id: Optional[str] = None,
        event_handler: Optional[Callable[[TraceStep], Awaitable[None]]] = None,
        **kwargs,
    ) -> ToolResult:
        """
        执行 Subagent 任务。

        Args:
            task: 任务描述
            background: 额外背景信息
            user_id: 用户 ID（从 kwargs 中获取）
            **kwargs: 其他参数

        Returns:
            ToolResult: 执行结果
        """
        if not task:
            return ToolResult(
                success=False,
                error="Task description is required",
            )

        # 用户 ID 可能在 kwargs 中
        actual_user_id = user_id or kwargs.get("user_id")
        if background is not None and not isinstance(background, str):
            try:
                background = json.dumps(background, ensure_ascii=False, default=str)
            except Exception:
                background = str(background)

        try:
            logger.info(
                f"Executing subagent {self.subagent.name} with task: {task[:100]}..."
            )

            result = await self.subagent.execute(
                task=task,
                user_id=actual_user_id,
                background=background,
                event_handler=event_handler,
            )

            return result

        except Exception as e:
            logger.exception(f"SubagentTool {self.name} execution failed: {e}")
            return ToolResult(
                success=False,
                error=f"Subagent execution failed: {str(e)}",
            )

               
def create_subagent_tool(subagent: "BaseSubagent") -> SubagentTool:
    """
    创建 Subagent 的 Tool 包装。

    Args:
        subagent: Subagent 实例

    Returns:
        SubagentTool 实例
    """
    return SubagentTool(subagent)


__all__ = ["SubagentTool", "create_subagent_tool"]
