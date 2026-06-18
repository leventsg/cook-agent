"""MCP tool provider."""

from __future__ import annotations

import logging
from typing import Optional

from app.agent.tools.base import BaseTool, MCPTool
from app.agent.tools.mcp.client import MCPClient

logger = logging.getLogger(__name__)


class MCPToolProvider:
    name = "mcp"

    def __init__(self):
        self._tools: dict[str, MCPTool] = {}
        self._servers: dict[str, str] = {}
        self._server_headers: dict[str, dict[str, str]] = {}
        self._clients: dict[str, MCPClient] = {}

    # ----- server management -----

    def register_server(
        self, name: str, endpoint: str, headers: Optional[dict[str, str]] = None
    ) -> None:
        self._servers[name] = endpoint
        if headers:
            self._server_headers[name] = headers
        elif name in self._server_headers:
            del self._server_headers[name]
        if name in self._clients:
            del self._clients[name]

    def list_servers(self) -> list[str]:
        return list(self._servers.keys())

    def _get_client(self, name: str) -> Optional[MCPClient]:
        endpoint = self._servers.get(name)
        if not endpoint:
            return None
        if name not in self._clients:
            self._clients[name] = MCPClient(
                endpoint,
                headers=self._server_headers.get(name),
            )
        return self._clients[name]

    def _remove_server_tools(self, name: str) -> None:
        prefix = f"mcp_{name}_"
        for tool_name in list(self._tools.keys()):
            if tool_name.startswith(prefix):
                del self._tools[tool_name]

    async def load_server_tools(self, name: str) -> list[MCPTool]:
        client = self._get_client(name)
        if not client:
            logger.warning(f"MCP server not registered: {name}")
            return []

        try:
            self._remove_server_tools(name)
            await client.initialize()
            tools = await client.list_tools()
            loaded: list[MCPTool] = []

            for tool_info in tools:
                tool_name = tool_info.get("name", "")
                if not tool_name:
                    continue
                full_tool_name = f"mcp_{name}_{tool_name}"

                mcp_tool = MCPTool(
                    name=full_tool_name,
                    description=tool_info.get("description", ""),
                    mcp_endpoint=self._servers[name],
                    mcp_tool_name=tool_name,
                    mcp_headers=self._server_headers.get(name),
                    parameters=tool_info.get("inputSchema", {}),
                )

                self._tools[mcp_tool.name] = mcp_tool
                loaded.append(mcp_tool)

            logger.info(f"Loaded {len(loaded)} tools from MCP server: {name}")
            return loaded
        except Exception as e:
            logger.exception(f"Failed to load tools from MCP server {name}: {e}")
            return []

    def unregister_server(self, name: str) -> None:
        self._remove_server_tools(name)
        if name in self._servers:
            del self._servers[name]
        if name in self._server_headers:
            del self._server_headers[name]
        if name in self._clients:
            del self._clients[name]

    # ----- ToolProvider surface -----

    def register_tool(self, tool: BaseTool) -> None:
        if not isinstance(tool, MCPTool):
            raise TypeError("MCPToolProvider only accepts MCPTool")
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tool_schema(self, name: str) -> Optional[dict]:
        tool = self._tools.get(name)
        if not tool:
            return None
        return tool.to_openai_schema()

    def get_tool_schemas(self, names: Optional[list[str]] = None) -> list[dict]:
        if names is None:
            return [t.to_openai_schema() for t in self._tools.values()]
        return [self._tools[n].to_openai_schema() for n in names if n in self._tools]

    def list_servers_with_tools(self) -> list[dict]:
        """
        返回按 MCP 服务分组后的工具列表

        返回：
            List[dict]，其中每个字典包含：

            - name：MCP 服务名称
            - type：服务类型（固定为 "mcp"）
            - tools：该服务提供的工具信息列表
        """
        # Group tools by server
        servers: dict[str, list[dict]] = {}

        for t in self._tools.values():
            # name format: mcp_{server}_{tool}
            server_name = None
            if t.name.startswith("mcp_"):
                parts = t.name.split("_", 2)
                if len(parts) >= 2:
                    server_name = parts[1]

            if server_name is None:
                server_name = "unknown"

            if server_name not in servers:
                servers[server_name] = []

            servers[server_name].append(
                {
                    "name": t.name,
                    "description": t.description,
                }
            )

        # Convert to list format
        return [
            {
                "name": server_name,
                "type": "mcp",
                "tools": tools,
            }
            for server_name, tools in servers.items()
        ]
