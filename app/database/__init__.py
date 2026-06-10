"""
CookAgent 数据库模块。
提供异步数据库会话管理、ORM 模型定义以及存储层实现。
"""

from app.database.session import (
    async_session_factory,
    close_db,
    get_async_session,
    get_session_context,
    init_db,
)
from app.database.models import (
    Base,
    ConversationModel,
    KnowledgeDocumentModel,
    LLMUsageLogModel,
    MessageModel,
    RAGEvaluationModel,
    UserModel,
)
from app.database.conversation_repository import (
    ConversationRepository,
    conversation_repository,
)
from app.database.document_repository import (
    DocumentRepository,
    document_repository,
)
from app.database.evaluation_repository import (
    EvaluationRepository,
    evaluation_repository,
)
from app.database.llm_usage_repository import (
    LLMUsageRepository,
    llm_usage_repository,
)

__all__ = [
    # Session management
    "async_session_factory",
    "close_db",
    "get_async_session",
    "get_session_context",
    "init_db",
    # Models
    "Base",
    "UserModel",
    "ConversationModel",
    "MessageModel",
    "KnowledgeDocumentModel",
    "RAGEvaluationModel",
    "LLMUsageLogModel",
    # Repositories
    "ConversationRepository",
    "conversation_repository",
    "DocumentRepository",
    "document_repository",
    "EvaluationRepository",
    "evaluation_repository",
    "LLMUsageRepository",
    "llm_usage_repository",
]
