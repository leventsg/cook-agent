"""
Agent 模块数据访问仓库

提供 Agent Session 和 Message 的 CRUD 操作。
"""

import logging
import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.orm import selectinload

from app.agent.database.models import AgentSessionModel, AgentMessageModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)


class AgentRepository:
    """
    Agent 数据访问仓库。
    管理 Agent Session 和 Message 的持久化。
    """

    # ==================== Session Operations ====================

    async def get_or_create_session(
        self,
        session_id: Optional[str] = None,
        user_id: str = "",
        title: Optional[str] = None,
    ) -> AgentSessionModel:
        """获取或创建 Agent Session。"""
        async with get_session_context() as session:
            if session_id:
                try:
                    sess_uuid = uuid.UUID(session_id)
                    stmt = (
                        select(AgentSessionModel)
                        .options(selectinload(AgentSessionModel.messages))
                        .where(AgentSessionModel.id == sess_uuid)
                    )
                    result = await session.execute(stmt)
                    agent_session = result.scalar_one_or_none()
                    if agent_session:
                        return agent_session
                except ValueError:
                    logger.warning(f"Invalid session_id format: {session_id}")

            agent_session = AgentSessionModel(
                user_id=user_id,
                title=title,
            )
            session.add(agent_session)
            await session.flush()
            return agent_session

    async def get_session(self, session_id: str) -> Optional[AgentSessionModel]:
        """根据 ID 获取 Session。"""
        async with get_session_context() as session:
            try:
                sess_uuid = uuid.UUID(session_id)
            except ValueError:
                return None

            stmt = (
                select(AgentSessionModel)
                .options(selectinload(AgentSessionModel.messages))
                .where(AgentSessionModel.id == sess_uuid)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[dict], int]:
        """列出 Sessions。"""
        async with get_session_context() as session:
            filters = []
            if user_id:
                filters.append(AgentSessionModel.user_id == user_id)

            count_stmt = select(func.count(AgentSessionModel.id))
            if filters:
                count_stmt = count_stmt.where(*filters)
            count_result = await session.execute(count_stmt)
            total_count = count_result.scalar() or 0

            stmt = (
                select(AgentSessionModel)
                .options(selectinload(AgentSessionModel.messages))
                .order_by(AgentSessionModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            if filters:
                stmt = stmt.where(*filters)

            result = await session.execute(stmt)
            sessions = result.scalars().all()

            return [s.to_dict() for s in sessions], total_count

    async def delete_session(self, session_id: str) -> bool:
        """删除 Session 及其所有消息。"""
        async with get_session_context() as session:
            try:
                sess_uuid = uuid.UUID(session_id)
            except ValueError:
                return False

            stmt = select(AgentSessionModel).where(AgentSessionModel.id == sess_uuid)
            result = await session.execute(stmt)
            agent_session = result.scalar_one_or_none()
            if not agent_session:
                return False

            await session.delete(agent_session)
            return True

    async def update_session_title(
        self,
        session_id: str,
        title: str,
    ) -> bool:
        """更新 Session 标题。"""
        async with get_session_context() as session:
            try:
                sess_uuid = uuid.UUID(session_id)
            except ValueError:
                return False

            stmt = select(AgentSessionModel).where(AgentSessionModel.id == sess_uuid)
            result = await session.execute(stmt)
            agent_session = result.scalar_one_or_none()

            if not agent_session:
                return False

            agent_session.title = title
            agent_session.updated_at = datetime.utcnow()
            await session.flush()
            return True

    # ==================== Message Operations ====================

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        trace: Optional[list] = None,
        tool_calls: Optional[list] = None,
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        thinking_duration_ms: Optional[int] = None,
        answer_duration_ms: Optional[int] = None,
    ) -> AgentMessageModel:
        """保存消息到 Session。"""
        async with get_session_context() as session:
            sess_uuid = uuid.UUID(session_id)

            # Update session timestamp
            stmt = select(AgentSessionModel).where(AgentSessionModel.id == sess_uuid)
            result = await session.execute(stmt)
            agent_session = result.scalar_one_or_none()

            if not agent_session:
                raise ValueError(f"Session {session_id} not found")

            agent_session.updated_at = datetime.utcnow()

            # Create message
            message = AgentMessageModel(
                session_id=sess_uuid,
                role=role,
                content=content,
                trace=trace,
                tool_calls=tool_calls,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                thinking_duration_ms=thinking_duration_ms,
                answer_duration_ms=answer_duration_ms,
            )
            session.add(message)
            await session.flush()
            return message

    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[AgentMessageModel]:
        """获取 Session 的消息列表。"""
        async with get_session_context() as session:
            sess_uuid = uuid.UUID(session_id)
            stmt = (
                select(AgentMessageModel)
                .where(AgentMessageModel.session_id == sess_uuid)
                .order_by(AgentMessageModel.created_at)
            )
            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_recent_messages(
        self,
        session_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        """
        获取最近的消息，用于上下文组装。

        Args:
            session_id: Session ID
            skip: 跳过的消息数（已压缩的消息）
            limit: 返回的消息数
        """
        async with get_session_context() as session:
            sess_uuid = uuid.UUID(session_id)

            # Get messages ordered by created_at, skip compressed ones
            stmt = (
                select(AgentMessageModel)
                .where(AgentMessageModel.session_id == sess_uuid)
                .order_by(AgentMessageModel.created_at)
                .offset(skip)
                .limit(limit)
            )

            result = await session.execute(stmt)
            messages = result.scalars().all()

            result_list = []
            for msg in messages:
                msg_dict: dict[str, Any] = {
                    "role": msg.role,
                    "content": msg.content,
                }
                if msg.tool_calls:
                    msg_dict["tool_calls"] = msg.tool_calls
                    if not msg.content:
                        msg_dict["content"] = None
                if msg.role == "tool":
                    if msg.tool_call_id:
                        msg_dict["tool_call_id"] = msg.tool_call_id
                    if msg.tool_name:
                        msg_dict["name"] = msg.tool_name
                result_list.append(msg_dict)

            return result_list

    async def get_message_count(self, session_id: str) -> int:
        """获取 Session 的消息总数。"""
        async with get_session_context() as session:
            try:
                sess_uuid = uuid.UUID(session_id)
            except ValueError:
                return 0

            stmt = select(func.count(AgentMessageModel.id)).where(
                AgentMessageModel.session_id == sess_uuid
            )
            result = await session.execute(stmt)
            return result.scalar() or 0

    # ==================== Compression Operations ====================

    async def get_compressed_summary(
        self, session_id: str
    ) -> tuple[Optional[str], int]:
        """获取压缩摘要和已压缩消息数。"""
        async with get_session_context() as session:
            try:
                sess_uuid = uuid.UUID(session_id)
            except ValueError:
                return None, 0

            stmt = select(
                AgentSessionModel.compressed_summary,
                AgentSessionModel.compressed_count,
            ).where(AgentSessionModel.id == sess_uuid)

            result = await session.execute(stmt)
            row = result.one_or_none()

            if row:
                return row[0], row[1]
            return None, 0

    async def update_compressed_summary(
        self,
        session_id: str,
        summary: str,
        message_count: int,
    ) -> bool:
        """更新压缩摘要。"""
        async with get_session_context() as session:
            try:
                sess_uuid = uuid.UUID(session_id)
            except ValueError:
                return False

            stmt = select(AgentSessionModel).where(AgentSessionModel.id == sess_uuid)
            result = await session.execute(stmt)
            agent_session = result.scalar_one_or_none()

            if not agent_session:
                return False

            agent_session.compressed_summary = summary
            agent_session.compressed_count = message_count
            await session.flush()

            logger.info(
                "Updated compressed summary for session %s (messages: %d)",
                session_id,
                message_count,
            )
            return True


agent_repository = AgentRepository()
