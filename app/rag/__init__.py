"""
CookAgent 的 RAG（检索增强生成）模块

本模块提供 RAG 流程的核心能力，包括：
- 文档处理与分块
- 向量嵌入与存储
- 检索优化
- 性能缓存
- 相关性重排序（Reranking）
"""

from app.rag.cache import CacheManager
from app.rag.pipeline.document_processor import document_processor
from app.rag.pipeline.retrieval import RetrievalOptimizationModule
from app.rag.pipeline.generation import GenerationIntegrationModule
from app.rag.pipeline.metadata_filter import MetadataFilterExtractor

__all__ = [
    # Cache
    "CacheManager",
    # Pipeline
    "document_processor",
    "RetrievalOptimizationModule",
    "GenerationIntegrationModule",
    "MetadataFilterExtractor",
]
