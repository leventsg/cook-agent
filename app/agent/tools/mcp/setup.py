"""
MCP 服务初始化模块

负责将 MCP 服务注册并集成到统一的 AgentHub Provider 系统中。
"""

import logging

from app.agent.registry import AgentHub

logger = logging.getLogger(__name__)


async def register_mcp_servers() -> None:
    """注册所有 MCP 服务器。"""
    await _register_amap_mcp()
    await _register_custom_mcp_servers()


async def _register_custom_mcp_servers() -> None:
    """注册用户自定义 MCP 服务器。"""
    from app.services.mcp_service import mcp_service

    try:
        await mcp_service.register_all()
    except Exception as e:
        logger.warning(f"Failed to register custom MCP servers: {e}")


async def _register_amap_mcp() -> None:
    """注册高德地图 MCP 服务器。"""
    from app.config import settings
    from app.agent.tools.providers.mcp import MCPToolProvider

    if not settings.mcp.amap.enabled:
        logger.info("Amap MCP is disabled, skipping registration")
        return

    amap_key = settings.mcp.amap_api_key
    if not amap_key:
        logger.warning("AMAP_API_KEY not configured, skipping Amap MCP registration")
        return

    endpoint = f"https://mcp.amap.com/mcp?key={amap_key}"

    # 直接获取 MCPToolProvider 并调用方法
    mcp_provider: MCPToolProvider = AgentHub.get_provider("mcp")  # type: ignore
    mcp_provider.register_server("amap", endpoint)

    try:
        loaded = await mcp_provider.load_server_tools("amap")
        logger.info(f"Loaded {len(loaded)} tools from Amap MCP")
    except Exception as e:
        logger.error(f"Failed to load Amap MCP tools: {e}")
