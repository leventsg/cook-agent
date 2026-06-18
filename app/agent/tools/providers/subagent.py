"""
SubagentToolProvider - Subagent 工具提供者

将已启用的 Subagent 作为 Tool 提供给主 Agent。
"""

import logging
from typing import Optional

from app.agent.tools.base import BaseTool

logger = logging.getLogger(__name__)


class SubagentToolProvider:
    """
    Subagent 工具提供者。

    根据用户的 Subagent 启用配置，动态生成对应的 Tool。
    """

    name = "subagent"

    def get_tools_for_user(self, user_id: str) -> dict[str, BaseTool]:
        """
        获取用户启用的所有 Subagent Tool。

        Args:
            user_id: 用户 ID

        Returns:
            Tool 名称到实例的映射
        """
        from app.agent.subagents import subagent_registry

        # 获取用户启用的 Subagent 并生成 Tool
        tools = {}
        subagent_tools = subagent_registry.get_enabled_subagent_tools(user_id)

        for tool in subagent_tools:
            tools[tool.name] = tool

        return tools

    def register_tool(self, tool: BaseTool) -> None:
        """不支持直接注册。"""
        raise NotImplementedError(
            "SubagentToolProvider does not support direct registration"
        )

    def unregister_tool(self, name: str) -> bool:
        """不支持直接取消注册。"""
        return False

    def get_tool(self, name: str, user_id: Optional[str] = None) -> Optional[BaseTool]:
        """
        获取 Subagent Tool。

        注意：需要 user_id 才能正确获取用户的 Subagent Tool。
        """
        if not user_id:
            return None

        tools = self.get_tools_for_user(user_id)
        return tools.get(name)

    def list_tool_names(self, user_id: Optional[str] = None) -> list[str]:
        """列出所有 Subagent Tool 名称。"""
        if not user_id:
            return []

        tools = self.get_tools_for_user(user_id)
        return list(tools.keys())

    def get_tool_schema(
        self, name: str, user_id: Optional[str] = None
    ) -> Optional[dict]:
        """获取 Tool schema。"""
        tool = self.get_tool(name, user_id)
        if tool:
            return tool.to_openai_schema()
        return None

    def get_tool_schemas(
        self,
        names: Optional[list[str]] = None,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """获取 Tool schemas。"""
        tools = self.get_tools_for_user(user_id) if user_id else {}

        if names is None:
            return [t.to_openai_schema() for t in tools.values()]

        return [tools[n].to_openai_schema() for n in names if n in tools]

    def list_servers_with_tools(self, user_id: Optional[str] = None) -> list[dict]:
        """返回 Subagent 作为一个虚拟 server。"""
        if not user_id:
            return []

        tools = self.get_tools_for_user(user_id)

        return [
            {
                "name": "subagents",
                "type": "subagent",
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                    }
                    for t in tools.values()
                ],
            }
        ]


__all__ = ["SubagentToolProvider"]
