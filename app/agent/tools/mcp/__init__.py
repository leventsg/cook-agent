"""
CookAgent 的 MCP 模块

提供用于 MCP 服务器集成的 StreamableHTTP 客户端
以及相关初始化与配置辅助工具
"""

from app.agent.tools.mcp.client import MCPClient

__all__ = [
    "MCPClient",
]
