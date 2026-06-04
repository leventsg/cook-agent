"""
基于 PostgreSQL 的会话持久化存储。
提供会话（Conversation）和消息（Message）的异步 CRUD 操作。
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload

from app.database.models import ConversationModel, MessageModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)

class ConversationRepository:
    """
    用于会话异步持久化存储的实现。
    提供基于数据库的持久化存储能力。
    """
    async def get_or_create(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> ConversationModel:
        """获取或创建一个会话"""
        async with get_session_context() as session:
            if conversation_id:
                try:
                    conv_uuid = uuid.UUID(conversation_id)
                    stmt = (
                        select(ConversationModel)
                        .options(selectinload(ConversationModel.messages))
                        .where(ConversationModel.id == conv_uuid)
                    )
                    result = await session.execute(stmt)
                    conversation = result.scalar_one_or_none()
                    if conversation:
                        return conversation
                except ValueError:
                    logger.warning(f"无效的conversation_id格式: {conversation_id}")

            # 创建新的会话
            conversation = ConversationModel(user_id=user_id)
            session.add(conversation)
            await session.flush()
            return conversation
        
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: Optional[list] = None,
        intent: Optional[str] = None,
        thinking: Optional[list] = None,
        thinking_duration_ms: Optional[int] = None,
        answer_duration_ms: Optional[int] = None,
    ) -> MessageModel:
        """添加一条消息到会话"""
        async with get_session_context() as session:
            conv_uuid = uuid.UUID(conversation_id)

            # 更新会话时间戳
            stmt = select(ConversationModel).where(ConversationModel.id == conv_uuid)
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise ValueError(f"会话 {conversation_id} 不存在")

            conversation.updated_at = datetime.now()

            # 创建消息
            message = MessageModel(
                conversation_id=conv_uuid,
                role=role,
                content=content,
                sources=sources,
                intent=intent,
                thinking=thinking,
                thinking_duration_ms=thinking_duration_ms,
                answer_duration_ms=answer_duration_ms,
            )
            session.add(message)
            await session.flush()
            return message
        
    async def get_history(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
    ) -> Optional[List[dict]]:
        """获取会话历史记录作为字典列表（对外使用）"""
        async with get_session_context() as session:
            try:
                conv_uuid = uuid.UUID(conversation_id)
            except ValueError:
                return None

            stmt = (
                select(MessageModel)
                .where(MessageModel.conversation_id == conv_uuid)
                .order_by(MessageModel.created_at)
            )
            if limit and limit > 0:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            messages = result.scalars().all()

            if not messages:
                conv_stmt = select(ConversationModel).where(
                    ConversationModel.id == conv_uuid
                )
                conv_result = await session.execute(conv_stmt)
                if not conv_result.scalar_one_or_none():
                    return None
                return []

            return [msg.to_dict() for msg in messages]
        
    async def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
    ) -> List[MessageModel]:
        """获取会话消息（对内使用，获取模型对象列表）"""
        async with get_session_context() as session:
            conv_uuid = uuid.UUID(conversation_id)
            stmt = (
                select(MessageModel)
                .where(MessageModel.conversation_id == conv_uuid)
                .order_by(MessageModel.created_at)
            )
            if limit and limit > 0:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())
        
    async def clear(self, conversation_id: str) -> bool:
        """删除会话及所有消息"""
        async with get_session_context() as session:
            try:
                conv_uuid = uuid.UUID(conversation_id)
            except ValueError:
                return False

            stmt = delete(ConversationModel).where(ConversationModel.id == conv_uuid)
            result = await session.execute(stmt)
            return result.rowcount > 0 
    
    async def update_title(self, conversation_id: str, title: str) -> bool:
        """更新会话标题"""
        async with get_session_context() as session:
            try:
                conv_uuid = uuid.UUID(conversation_id)
            except ValueError:
                return False

            stmt = select(ConversationModel).where(ConversationModel.id == conv_uuid)
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                return False

            conversation.title = title
            await session.flush()

            logger.info(
                "更新会话 %s 标题为 '%s'",
                conversation_id,
                title,
            )
            return True
        
    async def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """
        列出会话及其元数据，按 updated_at 降序排列
        Returns:
            (会话列表, 总数)
        """
        async with get_session_context() as session:
            if limit <= 0:
                limit = 50
            if offset < 0:
                offset = 0
            # 基础过滤条件
            base_filter = []
            if user_id:
                base_filter.append(ConversationModel.user_id == user_id)

            # 获取总数
            count_stmt = select(func.count(ConversationModel.id))
            if base_filter:
                count_stmt = count_stmt.where(*base_filter)
            count_result = await session.execute(count_stmt)
            total_count = count_result.scalar() or 0

            # 分页
            stmt = (
                select(ConversationModel)
                .options(selectinload(ConversationModel.messages))
                .order_by(ConversationModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )

            if base_filter:
                stmt = stmt.where(*base_filter)

            result = await session.execute(stmt)
            conversations = result.scalars().all()

            return [conv.to_dict() for conv in conversations], total_count
        
    async def get_conversation(
        self, conversation_id: str
    ) -> Optional[ConversationModel]:
        """获取会话详情"""
        async with get_session_context() as session:
            try:
                conv_uuid = uuid.UUID(conversation_id)
            except ValueError:
                return None

            stmt = (
                select(ConversationModel)
                .options(selectinload(ConversationModel.messages))
                .where(ConversationModel.id == conv_uuid)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        
    async def get_compressed_summary(
        self, conversation_id: str
    ) -> tuple[Optional[str], int]:
        """
        获取会话压缩摘要和消息数量
        Returns:
            (压缩摘要, 压缩消息数量)
        """
        async with get_session_context() as session:
            try:
                conv_uuid = uuid.UUID(conversation_id)
            except ValueError:
                return None, 0

            stmt = select(
                ConversationModel.compressed_summary,
                ConversationModel.compressed_message_count,
            ).where(ConversationModel.id == conv_uuid)

            result = await session.execute(stmt)
            row = result.one_or_none()

            if row:
                return row[0], row[1]
            return None, 0
        
    async def update_compressed_summary(
        self,
        conversation_id: str,
        summary: str,
        message_count: int,
    ) -> bool:
        """
        更新会话压缩摘要和消息数量

        Args:
            conversation_id: 会话 ID
            summary: 压缩摘要内容
            message_count: 压缩消息数量
        """
        async with get_session_context() as session:
            try:
                conv_uuid = uuid.UUID(conversation_id)
            except ValueError:
                return False

            stmt = select(ConversationModel).where(ConversationModel.id == conv_uuid)
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                return False

            conversation.compressed_summary = summary
            conversation.compressed_message_count = message_count
            await session.flush()

            logger.info(
                "更新会话 %s 压缩摘要为 '%s'，压缩消息数量为 %d",
                conversation_id,
                summary,
                message_count,
            )
            return True
    
    async def get_message_count(self, conversation_id: str) -> int:
        """获取会话消息数量"""
        async with get_session_context() as session:
            try:
                conv_uuid = uuid.UUID(conversation_id)
            except ValueError:
                return 0

            stmt = select(func.count(MessageModel.id)).where(
                MessageModel.conversation_id == conv_uuid
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
        
# 单例
conversation_repository = ConversationRepository()
