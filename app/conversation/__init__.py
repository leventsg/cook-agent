"""
CookAgent 会话模块

负责处理对话流程、意图识别、查询改写以及 LLM 编排

本模块为所有会话相关功能提供统一接口，
同时包含上下文管理能力（为方便使用，从 app.context 重新导出）
"""

from app.conversation.intent import IntentDetectionResult, IntentDetector, QueryIntent
from app.conversation.llm_orchestrator import LLMOrchestrator
from app.conversation.query_rewriter import QueryRewriter
from app.database.conversation_repository import conversation_repository
from app.conversation.types import ChatContext, ExtraOptions, UnifiedSource
from app.conversation.prompts import SYSTEM_PROMPT

# 上下文管理模块
from app.context import ContextManager, ContextCompressor

__all__ = [
    # Types
    "ChatContext",
    "ExtraOptions",
    "UnifiedSource",
    # Intent detection
    "IntentDetectionResult",
    "IntentDetector",
    "QueryIntent",
    # LLM and query
    "LLMOrchestrator",
    "QueryRewriter",
    # Prompts
    "SYSTEM_PROMPT",
    # Repository
    "conversation_repository",
    # Context management 
    "ContextManager",
    "ContextCompressor",
]
