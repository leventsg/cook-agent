"""
Tool 基类和辅助类

Tool 是 Agent 可以调用的外部功能，如搜索、计算、API 调用等。
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional

from pydantic import BaseModel

from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Tool 基类。

    所有 Tool 必须继承此类并实现 execute 方法。
    """

    # Tool 基本信息
    name: str
    description: str

    # JSON Schema 格式的参数定义
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self):
        """初始化 Tool。"""
        if not hasattr(self, "name") or not self.name:
            raise ValueError("Tool must have a name")
        if not hasattr(self, "description") or not self.description:
            raise ValueError("Tool must have a description")

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """
        执行 Tool。

        Args:
            **kwargs: Tool 参数

        Returns:
            ToolResult: 执行结果
        """
        pass

    async def safe_execute(self, **kwargs) -> ToolResult:
        """
        安全执行 Tool，捕获异常。

        Args:
            **kwargs: Tool 参数

        Returns:
            ToolResult: 执行结果
        """
        try:
            return await self.execute(**kwargs)
        except Exception as e:
            logger.exception(f"Tool {self.name} execution failed: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=str(e),
            )

    def to_openai_schema(self) -> dict:
        """
        转换为 OpenAI function calling 格式。

        Returns:
            OpenAI tool schema
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def parse_arguments(self, arguments: str | dict) -> dict:
        """
        解析 Tool 调用参数。

        Args:
            arguments: JSON 字符串或字典

        Returns:
            解析后的参数字典
        """
        if isinstance(arguments, str):
            try:
                return json.loads(arguments)
            except json.JSONDecodeError:
                return {}
        return arguments

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"


class MCPTool(BaseTool):
    """
    MCP (Model Context Protocol) Tool 封装。

    用于调用外部 MCP 服务。
    """

    mcp_endpoint: str
    mcp_tool_name: str

    def __init__(
        self,
        name: str,
        description: str,
        mcp_endpoint: str,
        mcp_tool_name: str,
        mcp_headers: Optional[dict[str, str]] = None,
        parameters: Optional[dict] = None,
    ):
        self.name = name
        self.description = description
        self.mcp_endpoint = mcp_endpoint
        self.mcp_tool_name = mcp_tool_name
        self.mcp_headers = mcp_headers or {}
        if parameters:
            self.parameters = parameters
        super().__init__()

    async def execute(self, **kwargs) -> ToolResult:
        """
        调用 MCP 服务。

        使用 MCPClient 在远程 MCP 服务器上执行工具
        """
        try:
            from app.agent.tools.mcp.client import MCPClient

            client = MCPClient(self.mcp_endpoint, headers=self.mcp_headers)

            if kwargs and "user_id" in kwargs:
                kwargs.pop("user_id")

            return await client.call_tool(self.mcp_tool_name, kwargs)

        except Exception as e:
            logger.exception(f"MCP Tool {self.name} execution failed: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"MCP tool execution failed: {str(e)}",
            )


class ToolExecutor:
    """
    Tool 执行器。

    负责执行 Tool 调用并返回结果。
    """

    def __init__(self, tools: dict[str, BaseTool], user_id: Optional[str] = None):
        """
        初始化执行器。

        Args:
            tools: Tool 名称到实例的映射
            user_id: 用户 ID（用于自动注入工具调用）
        """
        self.tools = tools
        self.user_id = user_id

    async def execute(
        self,
        tool_name: str,
        arguments: str | dict,
        event_handler: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        执行指定的 Tool。

        Args:
            tool_name: Tool 名称
            arguments: Tool 参数

        Returns:
            ToolResult: 执行结果
        """
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                data=None,
                error=f"Tool '{tool_name}' not found",
            )

        parsed_args = tool.parse_arguments(arguments) or {}
        parsed_args = dict(parsed_args)
        if self.user_id and "user_id" not in parsed_args:
            parsed_args["user_id"] = self.user_id
        if event_handler and tool_name.startswith("subagent_"):
            parsed_args["event_handler"] = event_handler
        return await tool.safe_execute(**parsed_args)

    def get_schemas(self, tool_names: Optional[list[str]] = None) -> list[dict]:
        """
        获取 Tool schemas。

        Args:
            tool_names: 要获取的 Tool 名称列表，None 表示全部

        Returns:
            OpenAI tool schema 列表
        """
        if tool_names is None:
            return [t.to_openai_schema() for t in self.tools.values()]
        return [
            self.tools[name].to_openai_schema()
            for name in tool_names
            if name in self.tools
        ]
