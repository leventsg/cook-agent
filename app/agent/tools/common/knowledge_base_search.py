# app/agent/tools/common/knowledge_base_search.py
"""
CookHero 知识库检索 Tool

将 RAG 检索能力封装为 Agent 可调用的内置工具。
"""

import logging

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.services.rag_service import rag_service_instance

logger = logging.getLogger(__name__)


class KnowledgeBaseSearchTool(BaseTool):
    """
    知识库检索 Tool。

    使用 CookAgent 的 RAG 知识库检索相关内容。
    """

    name = "knowledge_base_search"
    description = "搜索 CookAgent 内置知识库，返回可引用的上下文与来源。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题或关键词"},
            "skip_rewrite": {
                "type": "boolean",
                "description": "是否跳过查询重写（默认 false）",
                "default": False,
            },
        },
        "required": ["query"],
    }

    async def execute(
        self, query: str = "", skip_rewrite: bool = False, **kwargs
    ) -> ToolResult:
        if not query:
            return ToolResult(success=False, error="Query is required")

        try:
            retrieval_result = await rag_service_instance.retrieve(
                query=query,
                skip_rewrite=skip_rewrite,
            )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "rewritten_query": retrieval_result.rewritten_query,
                    "context": retrieval_result.context,
                    "sources": retrieval_result.sources,
                    "document_count": len(retrieval_result.documents),
                },
            )
        except Exception as e:
            logger.exception("Knowledge base search failed: %s", e)
            return ToolResult(
                success=False,
                error=f"Knowledge base search failed: {str(e)}",
            )


__all__ = ["KnowledgeBaseSearchTool"]
