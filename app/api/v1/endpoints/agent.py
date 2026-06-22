"""
Agent API 接口，用于支持工具增强对话
独立于会话接口（Conversation API），专为基于 Agent 的交互场景设计
"""
import asyncio
import base64
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator, HttpUrl

from app.config import settings
from app.agent.service import agent_service
from app.agent.registry import AgentHub
from app.security.dependencies import check_message_security
from app.services.mcp_service import mcp_service
from app.services.subagent_service import subagent_service

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGE_LENGTH = settings.MAX_MESSAGE_LENGTH  # 10000 characters
MAX_IMAGES = 4
MAX_IMAGE_SIZE_MB = 10.0
SUPPORTED_IMAGE_FORMATS = ["image/jpeg", "image/png", "image/gif", "image/webp"]


class ToolSchema(BaseModel):
    """Tool schema for the tools API."""

    name: str
    description: str


class ServerInfo(BaseModel):
    """Server info for the tools API."""

    name: str
    type: str  # "local" or "mcp"
    tools: List[ToolSchema]


class ToolsListResponse(BaseModel):
    """Response model for the tools list endpoint."""

    servers: List[ServerInfo]


class MCPServerRequest(BaseModel):
    """Request model for creating MCP server."""

    name: str = Field(..., min_length=2, max_length=64)
    endpoint: HttpUrl
    auth_header_name: Optional[str] = Field(default=None, max_length=128)
    auth_token: Optional[str] = None


class MCPServerResponse(BaseModel):
    """Response model for MCP server info."""

    id: str
    name: str
    endpoint: str
    auth_header_name: Optional[str] = None
    auth_token: Optional[str] = None
    enabled: bool
    created_at: str
    updated_at: str


class MCPServerListResponse(BaseModel):
    """Response model for MCP server list."""

    servers: List[MCPServerResponse]


class MCPServerUpdateRequest(BaseModel):
    """Request model for updating MCP server."""

    endpoint: Optional[HttpUrl] = None
    auth_header_name: Optional[str] = Field(default=None, max_length=128)
    auth_token: Optional[str] = None
    enabled: Optional[bool] = None


class ImageData(BaseModel):
    """Image data for multimodal requests."""

    data: str  # Base64 encoded image data
    mime_type: str = "image/jpeg"

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """校验图片MIME格式"""
        if v not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(
                f"不支持的图片格式: {v}。支持的格式: {SUPPORTED_IMAGE_FORMATS}"
            )
        return v

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str) -> str:
        """校验base64图片数据大小"""
        try:
            # Decode to check size (base64 is ~33% larger than binary)
            decoded_size = len(base64.b64decode(v))
            max_size = MAX_IMAGE_SIZE_MB * 1024 * 1024
            if decoded_size > max_size:
                raise ValueError(f"图片大小超过限制 ({MAX_IMAGE_SIZE_MB}MB)")
        except Exception as e:
            if "图片大小超过限制" in str(e):
                raise
            raise ValueError("无效的 base64 图片数据")
        return v


class AgentChatRequest(BaseModel):
    """Request model for agent chat endpoint."""

    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    images: Optional[List[ImageData]] = Field(default=None, max_length=MAX_IMAGES)
    session_id: Optional[str] = None
    agent_name: str = Field(default="default", max_length=100)
    stream: bool = True
    selected_tools: Optional[List[str]] = None  # User-selected tools

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """校验消息内容."""
        if not v or not v.strip():
            raise ValueError("消息不能为空")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"消息长度超过限制 ({MAX_MESSAGE_LENGTH} 字符)")
        return v


class AgentSessionResponse(BaseModel):
    """Response model for agent session."""

    id: str
    user_id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int
    last_message_preview: Optional[str] = None


class AgentMessageResponse(BaseModel):
    """Response model for agent message."""

    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    trace: Optional[List[Dict[str, Any]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    thinking_duration_ms: Optional[int] = None
    answer_duration_ms: Optional[int] = None


class AgentSessionListResponse(BaseModel):
    """Response model for listing agent sessions."""

    sessions: List[AgentSessionResponse]
    total_count: int
    limit: int
    offset: int


class AgentHistoryResponse(BaseModel):
    """Response model for agent session history."""

    session_id: str
    messages: List[AgentMessageResponse]


@router.get("/agent/tools")
async def list_available_tools(http_request: Request) -> ToolsListResponse:
    """
    按服务分组列出所有可用工具。

    **Response:**
    ```json
    {
        "servers": [
            {
                "name": "builtin",
                "type": "local",
                "tools": [
                    {"name": "calculator", "description": "执行数学计算..."}
                ]
            },
            {
                "name": "amap",
                "type": "mcp",
                "tools": [
                    {"name": "mcp_amap_poi_search", "description": "搜索兴趣点..."}
                ]
            }
        ]
    }
    ```
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    servers_data = AgentHub.list_all_servers(user_id=user_id)
    servers_data = [s for s in servers_data if s.get("type") != "subagent"]

    servers = [
        ServerInfo(
            name=s["name"],
            type=s["type"],
            tools=[ToolSchema(**t) for t in s["tools"]],
        )
        for s in servers_data
    ]

    return ToolsListResponse(servers=servers)


@router.get("/agent/mcp-servers")
async def list_mcp_servers(http_request: Request) -> MCPServerListResponse:
    """列出当前用户的所有MCP Service"""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    servers = await mcp_service.list_servers(user_id)
    return MCPServerListResponse(
        servers=[MCPServerResponse(**server.to_dict()) for server in servers]
    )


@router.post("/agent/mcp-servers", status_code=201)
async def create_mcp_server(
    payload: MCPServerRequest, http_request: Request
) -> MCPServerResponse:
    """创建 MCP server 并注册"""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        server = await mcp_service.create_server(
            user_id=user_id,
            name=payload.name,
            endpoint=str(payload.endpoint),
            enabled=True,
            auth_header_name=payload.auth_header_name,
            auth_token=payload.auth_token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MCPServerResponse(**server.to_dict())


@router.patch("/agent/mcp-servers/{server_name}")
async def update_mcp_server(
    server_name: str,
    payload: MCPServerUpdateRequest,
    http_request: Request,
) -> MCPServerResponse:
    """更新 MCP server 配置"""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    update_data = payload.model_dump(exclude_unset=True)
    update_auth = any(
        key in update_data for key in ("auth_header_name", "auth_token")
    )

    try:
        server = await mcp_service.update_server(
            user_id=user_id,
            name=server_name,
            endpoint=str(update_data["endpoint"]) if "endpoint" in update_data else None,
            enabled=update_data.get("enabled"),
            auth_header_name=update_data.get("auth_header_name"),
            auth_token=update_data.get("auth_token"),
            update_auth=update_auth,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    return MCPServerResponse(**server.to_dict())


@router.delete("/agent/mcp-servers/{server_name}")
async def delete_mcp_server(server_name: str, http_request: Request):
    """删除 MCP server 配置."""
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        deleted = await mcp_service.delete_server(user_id, server_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="MCP server not found")

    return {"message": "MCP server deleted successfully"}


@router.post("/agent/chat")
async def agent_chat(request: AgentChatRequest, http_request: Request):
    """
    使用 Agent 系统处理聊天消息。
    Agent 可以通过 Tools 和 Skills 来回答用户问题。
    该接口独立于基于 RAG 的对话接口，不依赖知识库检索流程。

    **Request Body:**
    - `message`: 用户输入的消息
    - `images`: 可选的图片列表 (base64 编码, 最多 4 张)
    - `session_id`: 可选的会话 ID，用于继续之前的会话
    - `agent_name`: 要使用的 agent 名称 (默认: "default")
    - `stream`: 是否流式返回响应 (默认: true)
    - `selected_tools`: 要使用的工具名称列表 (默认: 所有工具)

    **Response (SSE stream when stream=true):**
    ```
    data: {"type": "session", "session_id": "...", "agent_name": "..."}
    data: {"type": "vision", "is_food_related": true, "description": "..."}
    data: {"type": "text", "content": "..."}
    data: {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
    data: {"type": "tool_result", "name": "...", "success": true, "result": "..."}
    data: {"type": "trace", "iteration": 1, "action": "...", ...}
    data: {"type": "done", "session_id": "..."}
    ```
    """
    # ==========================================================================
    # Security Check: 使用统一的安全检查函数
    # ==========================================================================
    secured_message = await check_message_security(request.message, http_request)

    images_data = None
    if request.images:
        images_data = [
            {"data": img.data, "mime_type": img.mime_type} for img in request.images
        ]

    logger.info(
        f"Agent chat request: '{secured_message[:50]}...', agent={request.agent_name}, images={len(images_data) if images_data else 0}"
    )

    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")


    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def process_in_background():
        """
        后台任务：处理聊天请求并将结果写入队列
        该任务独立于客户端连接运行，即使客户端刷新页面或断开连接，也能够继续完成处理流程，并确保消息被正确保存到数据库中。
        """
        try:
            async for chunk in agent_service.chat(
                session_id=request.session_id,
                user_id=user_id,
                message=secured_message,
                agent_name=request.agent_name,
                streaming=request.stream,
                selected_tools=request.selected_tools,
                images=images_data,
            ):
                await queue.put(chunk)
        except Exception as e:
            logger.error(f"Background processing error: {e}", exc_info=True)
        finally:
            await queue.put(None) 

    async def stream_from_queue() -> AsyncGenerator[str, None]:
        """
        从队列 queue 中获取数据并返回给客户端。
        如果客户端断开连接，生成器会停止运行，但后台任务会继续处理消息并确保消息被正确保存到数据库中。
        """
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        except asyncio.CancelledError:
            # Client 断开连接 
            logger.info(
                "Stream cancelled by client, backend continues processing in background"
            )

    try:
        if request.stream:
            # 启动后台任务处理聊天请求并写入队列
            asyncio.create_task(process_in_background())

            return StreamingResponse(
                stream_from_queue(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no", 
                },
            )
        else:
            full_response = ""
            session_id = None
            tool_results = []

            async for event in agent_service.chat(
                session_id=request.session_id,
                user_id=user_id,
                message=secured_message,
                agent_name=request.agent_name,
                streaming=False,
                selected_tools=request.selected_tools,
                images=images_data,
            ):
                if event.startswith("data: "):
                    import json

                    data = json.loads(event[6:].strip())

                    if data["type"] == "text":
                        full_response += data.get("content", "")
                    elif data["type"] == "session":
                        session_id = data.get("session_id")
                    elif data["type"] == "tool_result":
                        tool_results.append(data)
                    elif data["type"] == "done":
                        session_id = data.get("session_id", session_id)

            return {
                "session_id": session_id,
                "response": full_response,
                "tool_results": tool_results,
            }

    except Exception as e:
        logger.error(f"Error processing agent chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="处理请求时发生错误")


@router.get("/agent/session/{session_id}")
async def get_agent_session(session_id: str, http_request: Request):
    """
    根据 ID 获取 Agent 会话

    **Parameters:**
    - `session_id`: 会话 ID

    **Response:**
    ```json
    {
        "id": "...",
        "user_id": "...",
        "agent_name": "...",
        "created_at": "...",
        "updated_at": "...",
        "message_count": 10
    }
    ```
    """
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此会话")

    return session


@router.get("/agent/session/{session_id}/messages")
async def get_agent_session_messages(
    session_id: str,
    http_request: Request,
    limit: Optional[int] = None,
):
    """
    根据会话 ID 获取 Agent 会话中的所有消息。

    **Parameters:**
    - `session_id`: 会话 ID
    - `limit`: 可选的返回消息数量限制，默认返回所有消息

    **Response:**
    ```json
    {
        "session_id": "...",
        "messages": [
            {
                "id": "...",
                "role": "user",
                "content": "...",
                "created_at": "...",
                "trace": null,
                "tool_calls": null
            },
            ...
        ]
    }
    ```
    """
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权访问此会话")

    messages = await agent_service.get_messages(session_id, limit)
    return AgentHistoryResponse(
        session_id=session_id,
        messages=[AgentMessageResponse(**msg) for msg in messages],
    )


@router.delete("/agent/session/{session_id}")
async def delete_agent_session(session_id: str, http_request: Request):
    """
    根据会话 ID 删除 Agent 会话。

    **Parameters:**
    - `session_id`: 会话 ID
    """
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权删除此会话")

    success = await agent_service.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="删除会话失败")

    return {"message": "Session deleted successfully"}


class UpdateSessionTitleRequest(BaseModel):
    """Request model for updating session title."""

    title: str = Field(..., max_length=255)


@router.patch("/agent/session/{session_id}/title")
async def update_agent_session_title(
    session_id: str, request: UpdateSessionTitleRequest, http_request: Request
):
    """
    更新 agent 会话标题

    **Parameters:**
    - `session_id`: 会话 ID

    **Request Body:**
    - `title`: 新标题
    """
    session = await agent_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_id = getattr(http_request.state, "user_id", None)
    if user_id and session.get("user_id") != str(user_id):
        raise HTTPException(status_code=403, detail="无权修改此会话")

    success = await agent_service.update_session_title(session_id, request.title)
    if not success:
        raise HTTPException(status_code=500, detail="更新会话标题失败")

    return {"message": "Title updated successfully", "title": request.title}


@router.get("/agent/sessions")
async def list_agent_sessions(
    http_request: Request,
    limit: int = 50,
    offset: int = 0,
) -> AgentSessionListResponse:
    """
    列出当前用户的所有 agent 会话。

    **Query Parameters:**
    - `limit`:  (default: 50)
    - `offset`:  (default: 0)
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    sessions, total_count = await agent_service.list_sessions(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )

    return AgentSessionListResponse(
        sessions=[AgentSessionResponse(**s) for s in sessions],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


# ==================== Subagent API Endpoints ====================


class SubagentSchema(BaseModel):
    """Subagent schema for API responses."""

    name: str
    display_name: str
    description: str
    system_prompt: str
    tools: List[str]
    max_iterations: int
    enabled: bool
    builtin: bool
    category: str


class SubagentListResponse(BaseModel):
    """Response model for subagent list."""

    subagents: List[SubagentSchema]


class SubagentToggleRequest(BaseModel):
    """Request model for enabling/disabling a subagent."""

    enabled: bool


class CreateSubagentRequest(BaseModel):
    """Request model for creating a custom subagent."""

    name: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=10, max_length=500)
    system_prompt: str = Field(..., min_length=20, max_length=10000)
    tools: List[str] = Field(default_factory=list)
    max_iterations: int = Field(default=10, ge=1, le=50)
    category: str = Field(default="custom", max_length=32)


class UpdateSubagentRequest(BaseModel):
    """Request model for updating a custom subagent."""

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, min_length=10, max_length=500)
    system_prompt: Optional[str] = Field(default=None, min_length=20, max_length=10000)
    tools: Optional[List[str]] = None
    max_iterations: Optional[int] = Field(default=None, ge=1, le=50)
    category: Optional[str] = Field(default=None, max_length=32)


@router.get("/agent/subagents")
async def list_subagents(http_request: Request) -> SubagentListResponse:
    """
    获取当前用户可用的所有 Subagent 列表。

    **Response:**
    ```json
    {
        "subagents": [
            {
                "name": "diet_planner",
                "display_name": "饮食规划专家",
                "description": "专业的饮食规划助手...",
                "tools": ["datetime", "web_search", "diet_analysis"],
                "max_iterations": 15,
                "enabled": true,
                "builtin": true,
                "category": "diet"
            }
        ]
    }
    ```
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    configs = await subagent_service.sync_user_subagents(user_id)

    subagents = [
        SubagentSchema(
            name=config.name,
            display_name=config.display_name,
            description=config.description,
            system_prompt=config.system_prompt,
            tools=config.tools,
            max_iterations=config.max_iterations,
            enabled=config.enabled,
            builtin=config.builtin,
            category=config.category,
        )
        for config in configs
    ]

    return SubagentListResponse(subagents=subagents)


@router.patch("/agent/subagents/{subagent_name}")
async def toggle_subagent(
    subagent_name: str,
    request: SubagentToggleRequest,
    http_request: Request,
):
    """
    启动当前用户的 Subagent。

    **Parameters:**
    - `subagent_name`: 需要启用的 Subagent 名称

    **Request Body:**
    - `enabled`: 
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        success = await subagent_service.set_enabled(
            user_id, subagent_name, request.enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not success:
        raise HTTPException(status_code=404, detail="Subagent not found")

    return {
        "message": f"Subagent {'enabled' if request.enabled else 'disabled'} successfully"
    }


@router.post("/agent/subagents", status_code=201)
async def create_subagent(
    request: CreateSubagentRequest,
    http_request: Request,
) -> SubagentSchema:
    """
    创建当前用户的自定义 Subagent。

    **Request Body:**
    - `name`: Subagent 名称（唯一标识）
    - `display_name`: UI 显示名称
    - `description`: Subagent 描述
    - `system_prompt`: Subagent 的System Prompt
    - `tools`: Subagent 可使用的工具名称列表
    - `max_iterations`: 最大迭代次数 (default: 10)
    - `category`: 分类用于组织 (default: "custom")
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        config = await subagent_service.create_subagent(
            user_id=user_id,
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            system_prompt=request.system_prompt,
            tools=request.tools,
            max_iterations=request.max_iterations,
            category=request.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SubagentSchema(
        name=config.name,
        display_name=config.display_name,
        description=config.description,
        system_prompt=config.system_prompt,
        tools=config.tools,
        max_iterations=config.max_iterations,
        enabled=config.enabled,
        builtin=config.builtin,
        category=config.category,
    )


@router.put("/agent/subagents/{subagent_name}")
async def update_subagent(
    subagent_name: str,
    request: UpdateSubagentRequest,
    http_request: Request,
) -> SubagentSchema:
    """
    更新当前用户的 Subagent 配置。
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    update_data = request.model_dump(exclude_unset=True)

    try:
        config = await subagent_service.update_subagent(
            user_id=user_id,
            name=subagent_name,
            display_name=update_data.get("display_name"),
            description=update_data.get("description"),
            system_prompt=update_data.get("system_prompt"),
            tools=update_data.get("tools"),
            max_iterations=update_data.get("max_iterations"),
            category=update_data.get("category"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not config:
        raise HTTPException(status_code=404, detail="Subagent not found")

    return SubagentSchema(
        name=config.name,
        display_name=config.display_name,
        description=config.description,
        system_prompt=config.system_prompt,
        tools=config.tools,
        max_iterations=config.max_iterations,
        enabled=config.enabled,
        builtin=config.builtin,
        category=config.category,
    )


@router.delete("/agent/subagents/{subagent_name}")
async def delete_subagent(subagent_name: str, http_request: Request):
    """
    删除一个自定义 Subagent。

    注意：内置 Subagent 不能被删除，只能被禁用。

    **Parameters:**
    - `subagent_name`: Subagent 名称
    """
    user_id = getattr(http_request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")

    try:
        success = await subagent_service.delete_subagent(user_id, subagent_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="Subagent not found")

    return {"message": "Subagent deleted successfully"}
