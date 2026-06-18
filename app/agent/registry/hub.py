"""
AgentHub：Agent、Tool 与 Provider（MCP、自定义等）的统一入口

设计目标：

- 为所有注册与查询 API 提供统一的导入路径
- 将 Provider 作为一等公民进行管理，支持内置 Provider、MCP Provider 以及未来的自定义 Provider
- 不提供向后兼容层

对外暴露的 API 仅保留代码库实际所需的能力，并与业务使用场景保持一致。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Protocol, Type, runtime_checkable

from app.agent.types import AgentConfig
from app.agent.tools.base import BaseTool, ToolExecutor

logger = logging.getLogger(__name__)


@runtime_checkable
class ToolProvider(Protocol):
    """
    Tool 提供者。

    示例：
    - 内置提供者：注册 Python 实现的 Tool
    - mcp 提供者：加载并注册从 MCP 服务器的 Tool
    - 自定义提供者：从数据库或配置加载用户定义的 Tool
    """

    name: str

    def get_tool(self, name: str) -> Optional[BaseTool]:
        raise NotImplementedError

    def get_tool_schema(self, name: str) -> Optional[dict]:
        raise NotImplementedError

    def get_tool_schemas(self, names: Optional[list[str]] = None) -> list[dict]:
        raise NotImplementedError

    def list_tool_names(self) -> list[str]:
        raise NotImplementedError

    def register_tool(self, tool: BaseTool) -> None:
        raise NotImplementedError

    def unregister_tool(self, name: str) -> bool:
        raise NotImplementedError

    def list_servers_with_tools(self) -> list[dict]:
        """
        返回按服务器分组的 Tool 信息字典列表。

        returns:
            - name: 服务器名称
            - type: "local" 或 "mcp"
            - tools: Tool 列表，每个 Tool 包含 name 和 description
        """
        raise NotImplementedError


@dataclass(frozen=True)
class _AgentEntry:
    cls: Type["BaseAgent"]
    config: AgentConfig


class AgentHub:
    """统一模块入口"""

    _agents: dict[str, _AgentEntry] = {}
    _providers: dict[str, ToolProvider] = {}

    # ==================== Agent ====================

    @classmethod
    def register_agent(cls, agent_cls: Type["BaseAgent"], config: AgentConfig) -> None:
        cls._agents[config.name] = _AgentEntry(cls=agent_cls, config=config)
        logger.info(f"Registered agent: {config.name}")

    @classmethod
    def get_agent(cls, name: str) -> "BaseAgent":
        entry = cls._agents.get(name)
        if not entry:
            raise KeyError(f"Agent '{name}' not found")
        return entry.cls(entry.config)

    @classmethod
    def get_agent_config(cls, name: str) -> AgentConfig:
        entry = cls._agents.get(name)
        if not entry:
            raise KeyError(f"Agent '{name}' not found")
        return entry.config

    @classmethod
    def list_agents(cls) -> list[str]:
        return list(cls._agents.keys())

    @classmethod
    def clear_agents(cls) -> None:
        cls._agents.clear()

    # ==================== Providers ====================

    @classmethod
    def register_provider(cls, provider: ToolProvider) -> None:
        if provider.name in cls._providers:
            raise ValueError(f"Provider already registered: {provider.name}")
        cls._providers[provider.name] = provider
        logger.info(f"Registered tool provider: {provider.name}")

    @classmethod
    def get_provider(cls, name: str) -> ToolProvider:
        provider = cls._providers.get(name)
        if not provider:
            raise KeyError(f"Provider '{name}' not found")
        return provider

    @classmethod
    def list_providers(cls) -> list[str]:
        return list(cls._providers.keys())

    @classmethod
    def clear_providers(cls) -> None:
        cls._providers.clear()

    # ==================== Tool surface (aggregated) ====================

    @classmethod
    def register_tool(cls, tool: BaseTool, provider: str = "local") -> None:
        cls.get_provider(provider).register_tool(tool)

    @classmethod
    def unregister_tool(cls, name: str) -> bool:
        for p in cls._providers.values():
            if p.get_tool(name):
                return p.unregister_tool(name)
        return False

    @classmethod
    def get_tool(cls, name: str, user_id: Optional[str] = None) -> Optional[BaseTool]:
        for p in cls._providers.values():
            # SubagentToolProvider 需要 user_id
            if p.name == "subagent" and user_id:
                tool = p.get_tool(name, user_id)  # type: ignore
            else:
                tool = p.get_tool(name)
            if tool:
                return tool
        return None

    @classmethod
    def get_tool_schemas(
        cls,
        names: Optional[list[str]] = None,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        if names is None:
            schemas: list[dict] = []
            for p in cls._providers.values():
                if p.name == "subagent" and user_id:
                    schemas.extend(p.get_tool_schemas(None, user_id))  # type: ignore
                else:
                    schemas.extend(p.get_tool_schemas(None))
            return schemas

        # keep order per names
        result: list[dict] = []
        for n in names:
            for p in cls._providers.values():
                if p.name == "subagent" and user_id:
                    schema = p.get_tool_schema(n, user_id)  # type: ignore
                else:
                    schema = p.get_tool_schema(n)
                if schema:
                    result.append(schema)
                    break
        return result

    @classmethod
    def list_tools(cls, user_id: Optional[str] = None) -> list[str]:
        names: list[str] = []
        for p in cls._providers.values():
            if p.name == "subagent" and user_id:
                names.extend(p.list_tool_names(user_id))  # type: ignore
            else:
                names.extend(p.list_tool_names())
        return names

    @classmethod
    def list_all_servers(cls, user_id: Optional[str] = None) -> list[dict]:
        """
        返回所有服务器的 Tool 列表

        Returns:
            服务器列表，每个服务器包含：
            [
                { "name": "builtin", "type": "local", "tools": [...] },
                { "name": "amap", "type": "mcp", "tools": [...] },
                { "name": "subagents", "type": "subagent", "tools": [...] },
            ]
        """
        servers: list[dict] = []
        for p in cls._providers.values():
            if p.name == "subagent" and user_id:
                servers.extend(p.list_servers_with_tools(user_id)) 
            else:
                servers.extend(p.list_servers_with_tools())
        return servers

    @classmethod
    def create_tool_executor(
        cls,
        tool_names: Optional[list[str]] = None,
        user_id: Optional[str] = None,
    ) -> ToolExecutor:
        if tool_names is None:
            tools: dict[str, BaseTool] = {}
            for p in cls._providers.values():
                if p.name == "subagent" and user_id:
                    tool_list = p.list_tool_names(user_id)  # type: ignore
                else:
                    tool_list = p.list_tool_names()
                for name in tool_list:
                    if p.name == "subagent" and user_id:
                        tool = p.get_tool(name, user_id)  # type: ignore
                    else:
                        tool = p.get_tool(name)
                    if tool:
                        tools[name] = tool
            return ToolExecutor(tools, user_id=user_id)

        tools = {}
        for n in tool_names:
            tool = cls.get_tool(n, user_id)
            if tool:
                tools[n] = tool
        return ToolExecutor(tools, user_id=user_id)

    # ==================== Cleanup ====================

    @classmethod
    def clear_all(cls) -> None:
        cls.clear_agents()
        cls.clear_providers()


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.agents import BaseAgent  
