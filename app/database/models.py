"""
Cook Agent 的 SQLAlchemy ORM 模型定义。

用于定义数据库中会话（Conversation）、消息（Message）、
用户（User）、长期记忆（Long-Term Memory）
以及会话摘要（Conversation Summary）等数据表结构。
"""
from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from typing import List, Optional
from datetime import datetime
import uuid

class Base(DeclarativeBase):
    """
    ORM 模型基类。
    所有数据库实体模型均继承自该基类。
    """
    pass

class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    occupation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # 用户简介
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 用户画像
    profile: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 用户指南（如：用户偏好、用户需求等）
    user_instruction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_users_username", "username", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "username": self.username,
            "occupation": self.occupation,
            "bio": self.bio,
            "profile": self.profile,
            "user_instruction": self.user_instruction,
            "created_at": self.created_at.isoformat(),
        }
    
class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    
    # 压缩上下文摘要
    compressed_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 压缩上下文消息数量
    compressed_message_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # 会话消息关系
    messages: Mapped[List["MessageModel"]] = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan", # 删除会话时级联删除所有会话消息
        order_by="MessageModel.created_at",
    )

    __table_args__ = (
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    def to_dict(self) -> dict:
        """Serialize conversation to dict for API responses."""
        return {
            "id": str(self.id),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "user_id": self.user_id,
            "title": self.title,
            "message_count": len(self.messages) if self.messages else 0,
            "last_message_preview": (
                self.messages[-1].content[:80] if self.messages else None
            ),
            "compressed_summary": self.compressed_summary,
            "compressed_message_count": self.compressed_message_count,
        }
    
class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False  # "user" or "assistant"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    # 消息来源（如：retriever、knowledge_base、long_term_memory 等）
    sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    thinking: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    
    # 性能指标
    thinking_duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    answer_duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)

    # 会话消息关系
    conversation: Mapped["ConversationModel"] = relationship(
        "ConversationModel", back_populates="messages"
    )

    __table_args__ = (
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )

    def to_dict(self) -> dict:
        """序列化消息为字典，用于 API 响应"""
        return {
            "id": str(self.id),
            "role": self.role,
            "content": self.content,
            "timestamp": self.created_at.isoformat(),
            "sources": self.sources,
            "intent": self.intent,
            "thinking": self.thinking,
            "thinking_duration_ms": self.thinking_duration_ms,
            "answer_duration_ms": self.answer_duration_ms,
        }

class KnowledgeDocumentModel(Base):
    """
    统一的知识文档模型，适用于所有类型的文档。
    同时存储公共文档（如 HowToCook 菜谱、烹饪技巧等）和用户个人文档。
    对于公共文档，user_id 为空（NULL）。
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    dish_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(50), nullable=False)
    # 数据来源（如：recipes、tips、personal）
    data_source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 数据来源具体类型（如：recipes、tips、personal）
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 文档来源（如：recipes、tips、personal）
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    # 是否为菜品索引文档
    is_dish_index: Mapped[bool] = mapped_column(default=False, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )

    __table_args__ = (
        Index("ix_knowledge_docs_user_category", "user_id", "category"),
        Index("ix_knowledge_docs_data_source", "data_source"),
        Index("ix_knowledge_docs_source_type", "source_type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else "GLOBAL",
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "data_source": self.data_source,
            "source_type": self.source_type,
            "source": self.source,
            "is_dish_index": self.is_dish_index,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_metadata(self) -> dict:
        """将文档元数据转换为字典，用于向量数据库存储"""
        return {
            "source": self.source,
            "parent_id": None,  # 会在创建分块时设置为 None
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "is_dish_index": self.is_dish_index,
            "data_source": self.data_source,
            "user_id": str(self.user_id) if self.user_id else "GLOBAL",
            "source_type": self.source_type,
        }
    
# ==================== RAG Evaluation Model ====================
class RAGEvaluationModel(Base):
    """
    用于存储每次启用 RAG 的响应所对应的 RAGAS 评测指标结果。
    """

    __tablename__ = "rag_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # 评测数据原始查询
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)

    # 检索质量指标
    context_precision: Mapped[Optional[float]] = mapped_column(nullable=True)
    context_recall: Mapped[Optional[float]] = mapped_column(nullable=True)

    # 生成质量指标
    faithfulness: Mapped[Optional[float]] = mapped_column(nullable=True)
    answer_relevancy: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Evaluation metadata
    evaluation_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending/completed/failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evaluation_duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_rag_evaluations_conv_created", "conversation_id", "created_at"),
        Index("ix_rag_evaluations_status", "evaluation_status"),
        Index("ix_rag_evaluations_user_created", "user_id", "created_at"),
    )

    def to_dict(self) -> dict:
        """Serialize evaluation to dict for API responses."""
        return {
            "id": str(self.id),
            "message_id": str(self.message_id),
            "conversation_id": str(self.conversation_id),
            "user_id": self.user_id,
            "query": self.query,
            "rewritten_query": self.rewritten_query,
            "context": self.context,  # Full context for alerts
            "response": self.response,  # Full response for alerts
            "context_preview": self.context[:200] + "..." if len(self.context) > 200 else self.context,
            "response_preview": self.response[:200] + "..." if len(self.response) > 200 else self.response,
            "faithfulness": self.faithfulness,  # Direct field for alerts
            "answer_relevancy": self.answer_relevancy,  # Direct field for alerts
            "metrics": {
                "context_precision": self.context_precision,
                "context_recall": self.context_recall,
                "faithfulness": self.faithfulness,
                "answer_relevancy": self.answer_relevancy,
            },
            "evaluation_status": self.evaluation_status,
            "error_message": self.error_message,
            "evaluation_duration_ms": self.evaluation_duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
        }
    
# ==================== LLM Usage Log Model ====================
class LLMUsageLogModel(Base):
    """
    用于记录每次 LLM 调用的 Token 使用情况、耗时信息以及调用上下文。
    出于隐私保护考虑，不存储输入内容（Input）和输出内容（Output）。
    """

    __tablename__ = "llm_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 唯一请求标识符，用于跟踪调用
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # LLM 调用模块名称
    module_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # 用户id（可选）
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    # 对话id（可选）
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    # 模型名称（可选）
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    # 工具名称（如果 LLM 调用涉及工具使用）
    tool_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    # Token 使用统计
    input_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(nullable=True)
    # 调用耗时（毫秒）
    duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    # 时间戳（创建时间）
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )

    __table_args__ = (
        # Time-series query optimization
        Index("ix_llm_usage_created_at_desc", created_at.desc()),
        # User + time query
        Index("ix_llm_usage_user_created", "user_id", "created_at"),
        # Module + time query
        Index("ix_llm_usage_module_created", "module_name", "created_at"),
        # Conversation query
        Index("ix_llm_usage_conversation", "conversation_id"),
        # Model + time query
        Index("ix_llm_usage_model_created", "model_name", "created_at"),
        # Tool + time query
        Index("ix_llm_usage_tool_created", "tool_name", "created_at"),
    )

    def to_dict(self) -> dict:
        """Serialize to dict for API responses."""
        return {
            "id": str(self.id),
            "request_id": self.request_id,
            "module_name": self.module_name,
            "user_id": self.user_id,
            "conversation_id": str(self.conversation_id) if self.conversation_id else None,
            "model_name": self.model_name,
            "tool_name": self.tool_name,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }