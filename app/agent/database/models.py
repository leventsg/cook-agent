"""
Agent 模块数据库模型

Agent 有独立的 Session 和 Message 存储，与 Conversation 完全分离。
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models import Base


class AgentSessionModel(Base):
    """Agent 对话会话"""

    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # 上下文压缩
    compressed_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compressed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 会话元数据
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)

    messages: Mapped[List["AgentMessageModel"]] = relationship(
        "AgentMessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessageModel.created_at",
    )

    __table_args__ = (Index("ix_agent_sessions_user_updated", "user_id", "updated_at"),)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "compressed_summary": self.compressed_summary,
            "compressed_count": self.compressed_count,
            "message_count": len(self.messages) if self.messages else 0,
            "last_message_preview": (
                self.messages[-1].content[:80] if self.messages else None
            ),
        }


class AgentMessageModel(Base):
    """Agent 对话消息"""

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,  # "user", "assistant", "tool"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Agent 执行轨迹（assistant 消息）或图片URL列表（user 消息）
    # assistant: [{iteration, action, tool_calls, content, timestamp, error}, ...]
    # user: [{type: "image", url, display_url, thumb_url}, ...]
    trace: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Tool 相关字段
    tool_calls: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # 计时统计（仅 assistant 消息）
    thinking_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationship to session
    session: Mapped["AgentSessionModel"] = relationship(
        "AgentSessionModel", back_populates="messages"
    )

    __table_args__ = (
        Index("ix_agent_messages_session_created", "session_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "trace": self.trace,
            "tool_calls": self.tool_calls,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "thinking_duration_ms": self.thinking_duration_ms,
            "answer_duration_ms": self.answer_duration_ms,
        }


class AgentMCPServerModel(Base):
    """Agent MCP 服务器配置."""

    __tablename__ = "agent_mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_header_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    auth_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_agent_mcp_servers_user_name", "user_id", "name", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "name": self.name,
            "endpoint": self.endpoint,
            "auth_header_name": self.auth_header_name,
            "auth_token": self.auth_token,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class AgentSubagentConfigModel(Base):
    """Agent Subagent 配置模型."""

    __tablename__ = "agent_subagent_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    max_iterations: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_agent_subagent_configs_user_name", "user_id", "name", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": list(self.tools or []),
            "max_iterations": self.max_iterations,
            "category": self.category,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
