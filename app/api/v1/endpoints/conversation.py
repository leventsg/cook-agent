"""
多轮对话 API 接口，集成 RAG 功能

包含以下安全特性：
- 输入校验
- Prompt 注入攻击防护
"""
"""
饮食管理 API 接口
提供饮食计划、餐食记录、饮食日志以及饮食分析等 RESTful API
"""
import asyncio
import base64
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.services.conversation_service import conversation_service
from app.security.dependencies import check_message_security

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGE_LENGTH = settings.MAX_MESSAGE_LENGTH  # 10000 characters
MAX_IMAGE_SIZE_MB = settings.MAX_IMAGE_SIZE_MB  # 5 MB
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

class ImageData(BaseModel):
    """
    用于多模态请求的图像数据
    """
    data: str  # Base64 encoded image data
    mime_type: str = "image/jpeg"  # MIME type of the image

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """验证图片 MIME 类型是否受支持."""
        if v not in ALLOWED_IMAGE_TYPES:
            raise ValueError(f"不支持的图片类型: {v}. 支持: {', '.join(ALLOWED_IMAGE_TYPES)}")
        return v

    @field_validator("data")
    @classmethod
    def validate_image_size(cls, v: str) -> str:
        """验证 base64 图片大小."""
        try:
            # 计算解码后的大小
            decoded_size = len(v) * 3 / 4
            if decoded_size > MAX_IMAGE_SIZE_BYTES:
                raise ValueError(f"图片大小超过限制 ({MAX_IMAGE_SIZE_MB}MB)")
        except Exception:
            pass  # 如果无法计算大小，允许通过当前值
        return v
    
class ConversationRequest(BaseModel):
    """
    聊天请求模型
    """
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)
    conversation_id: Optional[str] = None
    stream: bool = True
    extra_options: Optional[Dict[str, Any]] = None  # e.g., {"web_search": true}
    images: Optional[List[ImageData]] = Field(
        default=None,
        description="List of images (base64 encoded) for multimodal understanding",
        max_length=5,  # Max 5 images per request
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """验证消息内容是否符合要求"""
        if not v or not v.strip():
            raise ValueError("消息不能为空")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"消息长度超过限制 ({MAX_MESSAGE_LENGTH} 字符)")
        return v
    
class ConversationHistoryResponse(BaseModel):
    """
    会话历史响应模型
    """
    conversation_id: str
    messages: list

class ConversationSummary(BaseModel):
    """
    会话摘要模型
    """
    id: str
    title: Optional[str] = None
    created_at: str
    updated_at: str
    message_count: int
    last_message_preview: str | None = None

@router.post("/conversation")
async def conversation(request: ConversationRequest, http_request: Request):
    """
    处理对话消息，支持 RAG 功能

    判断当前查询是否需要通过知识库检索（RAG）获取知识，或是否可以直接由 LLM 生成回答

    **Request Body:**
    - `message`: 用户输入的消息
    - `conversation_id`: 会话 ID，用于继续会话
    - `stream`: 是否流式响应，默认值为 true
    - `extra_options`: 可选的额外选项，例如 `{"web_search": true}`
    - `images`: 多模态图像数据列表，用于图像理解

    **Response (SSE stream when stream=true):**
    ```
    data: {"type": "vision", "data": {"is_food_related": true, "intent": "...", "description": "..."}}
    data: {"type": "intent", "data": {"need_rag": true, "intent": "recipe_search", "reason": "..."}}
    data: {"type": "web_search", "data": {"confidence": 8, "reason": "...", "should_search": true}}
    data: {"type": "thinking", "content": "重写后的检索语句：番茄炒蛋的做法"}
    data: {"type": "text", "content": "..."}
    data: {"type": "sources", "data": [...]}
    data: {"type": "done", "conversation_id": "..."}
    ```
    """
    # ==========================================================================
    # 安全检查：使用统一的安全检查函数
    # ==========================================================================
    secured_message = await check_message_security(request.message, http_request)

    logger.info(f"Received conversation request: '{secured_message[:50]}...', images={len(request.images) if request.images else 0}")
    
    # ==========================================================================
    # 处理图像数据，确保在服务端正确处理
    # ==========================================================================
    images_data = None
    if request.images:
        images_data = [
            {"data": img.data, "mime_type": img.mime_type}
            for img in request.images
        ]
    
    # ==========================================================================
    # 使用基于队列的方法，确保即使客户端断开连接，后端也能继续处理
    # ==========================================================================
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    user_id = getattr(http_request.state, "user_id", None)

    async def process_in_background():
        """
        处理对话消息并将其结果放入队列中。
        该任务独立于客户端连接运行，确保即使客户端刷新或断开连接，也能将消息保存到数据库。
        """
        try:
            async for chunk in conversation_service.chat(
                message=secured_message,
                conversation_id=request.conversation_id,
                user_id=user_id,
                stream=True,
                extra_options=request.extra_options,
                images=images_data,
            ):
                await queue.put(chunk)
        except Exception as e:
            logger.error(f"Background processing error: {e}", exc_info=True)
        finally:
            await queue.put(None)  # Signal completion

    async def stream_from_queue() -> AsyncGenerator[str, None]:
        """
        将队列中的数据流式传输给客户端
        如果客户端断开连接，该生成器会停止运行，
        但后台任务仍会继续执行，以确保消息能够被正确保存
        """
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        except asyncio.CancelledError:
            # 客户端已断开连接（例如页面刷新）
            # 后台任务将继续独立运行
            logger.info("Stream cancelled by client, backend continues processing in background")
            # 不抛出异常，让后台任务正常执行完成

    try:
        if request.stream:
            # 启动后台任务，确保即使客户端断开连接，也能继续处理对话
            # 确保处理继续进行，即使客户端断开连接，也能将消息保存到数据库
            asyncio.create_task(process_in_background())

            return StreamingResponse(
                stream_from_queue(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"  # Disable nginx buffering
                }
            )
        else:
            # 非流式响应：收集所有数据块
            full_response = ""
            sources = []
            conv_id = None
            intent_data = None
            
            async for event in conversation_service.chat(
                message=secured_message,
                conversation_id=request.conversation_id,
                user_id=getattr(http_request.state, "user_id", None),
                stream=False,
                extra_options=request.extra_options,
                images=images_data,
            ):
                # 解析 SSE 事件，聚合文本响应
                if event.startswith("data: "):
                    import json
                    data = json.loads(event[6:].strip())
                    
                    if data["type"] == "text":
                        full_response += data["content"]
                    elif data["type"] == "sources":
                        sources = data["data"]
                    elif data["type"] == "done":
                        conv_id = data["conversation_id"]
                    elif data["type"] == "intent":
                        intent_data = data["data"]
                    elif data["type"] == "thinking":
                        # Thinking 事件仅用于信息展示，非流式模式下无需进行聚合处理
                        continue
            
            return {
                "conversation_id": conv_id,
                "response": full_response,
                "sources": sources,
                "intent": intent_data
            }
            
    except Exception as e:
        logger.error(f"Error processing conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while processing your request.")

@router.get("/conversation/{conversation_id}")
async def get_conversation_history(conversation_id: str):
    """
    获取对话历史记录。
    
    **参数:**
    - `conversation_id`: 对话 ID
    
    **响应:**
    ```json
    {
        "conversation_id": "...",
        "messages": [
            {
                "role": "user",
                "content": "...",
                "timestamp": "...",
                "sources": null,
                "intent": null
            },
            {
                "role": "assistant",
                "content": "...",
                "timestamp": "...",
                "sources": [...],
                "intent": "recipe_search"
            }
        ]
    }
    ```
    """
    history = await conversation_service.get_conversation_history(conversation_id)
    
    if history is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        messages=history
    )

@router.delete("/conversation/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """
    删除对话历史记录。
    
    **参数:**
    - `conversation_id`: 对话 ID
    """
    success = await conversation_service.clear_conversation(conversation_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"message": "Conversation cleared successfully"}

class UpdateTitleRequest(BaseModel):
    """更新会话标题请求模型"""
    title: str

@router.put("/conversation/{conversation_id}/title")
async def update_conversation_title(conversation_id: str, request: UpdateTitleRequest):
    """
    更新会话标题。
    
    **参数:**
    - `conversation_id`: 对话 ID
    - `title`: 新标题
    """
    success = await conversation_service.update_conversation_title(conversation_id, request.title)
    
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {"message": "Title updated successfully"}

class ConversationListResponse(BaseModel):
    """会话列表响应模型"""
    conversations: list[ConversationSummary]
    total_count: int
    limit: int
    offset: int

@router.get("/conversation")
async def list_conversations(
    http_request: Request,
    limit: int = 50,
    offset: int = 0,
) -> ConversationListResponse:
    """
    获取当前用户的所有会话。
    
    **查询参数:**
    - `limit`: 返回的最大会话数量 (默认值: 50)
    - `offset`: 跳过的会话数量 (默认值: 0)
    """
    conversations, total_count = await conversation_service.list_conversations(
        user_id=getattr(http_request.state, "user_id", None),
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        conversations=[ConversationSummary(**c) for c in conversations],
        total_count=total_count,
        limit=limit,
        offset=offset,
    )