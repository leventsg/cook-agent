"""
MCP StreamableHTTP 客户端

基于 StreamableHTTP 传输协议实现的 MCP（Model Context Protocol）客户端。

参考文档：
https://modelcontextprotocol.io/docs/concepts/transports#streamable-http
"""

import logging
import uuid
from typing import Any, Optional

import httpx

from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


class MCPClient:
    """
    MCP StreamableHTTP 客户端。

    实现 MCP 协议的 HTTP 传输层，支持：
    - tools/list: 获取服务器提供的工具列表
    - tools/call: 调用指定工具
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        headers: Optional[dict[str, str]] = None,
    ):
        """
        初始化 MCP 客户端。

        Args:
            endpoint: MCP 服务器端点 URL
            timeout: 请求超时时间（秒）
            headers: 可选请求头
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.headers = headers or {}
        self._session_id: Optional[str] = None

    def _generate_request_id(self) -> str:
        """生成唯一请求 ID。"""
        return str(uuid.uuid4())

    async def _send_request(
        self,
        method: str,
        params: Optional[dict] = None,
    ) -> dict:
        """
        发送 JSON-RPC 请求到 MCP 服务器。

        Args:
            method: JSON-RPC 方法名
            params: 方法参数

        Returns:
            响应结果
        """
        request_id = self._generate_request_id()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            payload["params"] = params  # type: ignore

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }

        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()

                if "Mcp-Session-Id" in response.headers:
                    self._session_id = response.headers["Mcp-Session-Id"]

                result = response.json()

                # 处理 JSON-RPC error
                if "error" in result:
                    error = result["error"]
                    raise MCPError(
                        code=error.get("code", -1),
                        message=error.get("message", "Unknown error"),
                        data=error.get("data"),
                    )

                return result.get("result", {})

            except httpx.HTTPStatusError as e:
                logger.error(f"MCP HTTP error: {e}")
                raise MCPError(
                    code=-1,
                    message=f"HTTP error: {e.response.status_code}",
                )
            except httpx.RequestError as e:
                logger.error(f"MCP request error: {e}")
                raise MCPError(
                    code=-1,
                    message=f"Request error: {str(e)}",
                )

    async def initialize(self) -> dict:
        """
        初始化 MCP 会话。

        Returns:
            服务器信息和能力
        """
        return await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
                "clientInfo": {
                    "name": "CookAgent",
                    "version": "1.0.0",
                },
            },
        )

    async def list_tools(self) -> list[dict]:
        """
        获取 MCP 服务器提供的工具列表。

        Returns:
            工具列表，每个工具包含 name、description、inputSchema
        """
        result = await self._send_request("tools/list")
        return result.get("tools", [])

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """
        调用 MCP 工具。

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        try:
            result = await self._send_request(
                "tools/call",
                {
                    "name": name,
                    "arguments": arguments,
                },
            )

            content = result.get("content", [])
            is_error = result.get("isError", False)

            if is_error:
                error_text = ""
                for item in content:
                    if item.get("type") == "text":
                        error_text += item.get("text", "")
                logger.info(f"MCP tool {name} returned error: {error_text}")
                return ToolResult(
                    success=False,
                    error=error_text or "Tool execution failed",
                )

            result_data = []
            for item in content:
                if item.get("type") == "text":
                    result_data.append(item.get("text", ""))
                elif item.get("type") == "image":
                    result_data.append(
                        {
                            "type": "image",
                            "data": item.get("data"),
                            "mimeType": item.get("mimeType"),
                        }
                    )
                elif item.get("type") == "resource":
                    result_data.append(
                        {
                            "type": "resource",
                            "resource": item.get("resource"),
                        }
                    )

            return ToolResult(
                success=True,
                data=result_data
                if len(result_data) > 1
                else result_data[0]
                if result_data
                else None,
            )

        except MCPError as e:
            logger.error(f"MCP tool call failed: {e}")
            return ToolResult(
                success=False,
                error=str(e),
            )
        except Exception as e:
            logger.exception(f"MCP tool call error: {e}")
            return ToolResult(
                success=False,
                error=f"Tool call failed: {str(e)}",
            )


class MCPError(Exception):
    """MCP 协议错误。"""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"MCP Error {code}: {message}")
