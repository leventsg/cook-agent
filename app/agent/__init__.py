"""
Agent 模块

独立的对话处理系统，与现有 ConversationService 完全分离。
"""

from app.agent.types import (
    AgentChunk,
    AgentChunkType,
    AgentConfig,
    AgentContext,
    AgentMessage,
    AgentSession,
    ToolCallInfo,
    ToolResult,
    ToolResultInfo,
    TraceStep,
)
from app.agent.agents import BaseAgent, DefaultAgent
from app.agent.registry import AgentHub
from app.agent.tools.providers import (
    LocalToolProvider,
    MCPToolProvider,
    SubagentToolProvider,
)
from app.agent.service import AgentService, agent_service
from app.agent.prompts import DEFAULT_AGENT_SYSTEM_PROMPT
from app.agent.context import (
    AgentContextBuilder,
    AgentContextCompressor,
    agent_context_builder,
    agent_context_compressor,
)
from app.agent.tools.base import BaseTool, MCPTool, ToolExecutor


def setup_agent_module():
    """
    初始化 Agent 模块（同步部分）。

    注册内置 Agent、Tool、Skill 和 Subagent。
    应在应用启动时调用。
    """
    # Register tool providers once
    if not AgentHub.list_providers():
        AgentHub.register_provider(LocalToolProvider())
        AgentHub.register_provider(MCPToolProvider())
        AgentHub.register_provider(SubagentToolProvider())

    # 注册内置 Tools
    from app.agent.tools.common import register_common_tools

    register_common_tools()

    # 注册饮食模块 Tools
    from app.diet.tools import register_diet_tools

    register_diet_tools()

    # 注册内置 Subagents
    from app.agent.subagents import register_builtin_subagents

    register_builtin_subagents()

    # 注册默认 Agent
    _register_default_agent()


async def setup_mcp_servers():
    """
    初始化 MCP 服务器（异步部分）。

    注册并加载所有配置的 MCP 服务器。
    应在应用启动时、setup_agent_module 之后调用。
    """
    from app.agent.tools.mcp.setup import register_mcp_servers

    await register_mcp_servers()


def _register_default_agent():
    """注册默认 Agent。"""
    default_config = AgentConfig(
        name="default",
        description="通用助手 Agent，可以进行对话、使用工具完成任务。",
        system_prompt=DEFAULT_AGENT_SYSTEM_PROMPT,
        # 不再绑定默认工具 - 完全由前端决定
        tools=[],
        max_iterations=10,
    )

    AgentHub.register_agent(DefaultAgent, default_config)


__all__ = [
    # Types
    "AgentChunk",
    "AgentChunkType",
    "AgentConfig",
    "AgentContext",
    "AgentMessage",
    "AgentSession",
    "ToolCallInfo",
    "ToolResult",
    "ToolResultInfo",
    "TraceStep",
    # Base classes
    "BaseAgent",
    "DefaultAgent",
    "BaseTool",
    "MCPTool",
    "ToolExecutor",
    # Service
    "AgentService",
    "agent_service",
    # Context
    "AgentContextBuilder",
    "AgentContextCompressor",
    "agent_context_builder",
    "agent_context_compressor",
    # Setup
    "setup_agent_module",
    "setup_mcp_servers",
]
