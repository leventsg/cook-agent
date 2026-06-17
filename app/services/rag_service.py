"""
RAG 服务

负责协调知识检索与响应生成的整个 RAG 流程

所有文档均存储于 PostgreSQL 和 Milvus 中，
不使用任何内存级文档存储
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.config import (
    DefaultRAGConfig,
    RAGConfig,
    settings,
)
from app.database.document_repository import document_repository
from app.rag.embeddings.embedding_factory import get_embedding_model
from app.rag.vector_stores.vector_store_factory import get_vector_store
from app.rag.pipeline.document_processor import document_processor
from app.rag.pipeline.retrieval import RetrievalOptimizationModule
from app.rag.pipeline.generation import GenerationIntegrationModule
from app.rag.pipeline.metadata_filter import MetadataFilterExtractor
from app.rag.rerankers.base import BaseReranker
from app.rag.cache import CacheManager

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """
    RAG 检索操作的结果
    """

    original_query: str
    rewritten_query: str
    context: str
    documents: List[Document]
    sources: List[Dict]


class RAGService:
    """
    RAG服务类，负责处理与RAG相关的业务逻辑

    包括文档检索、生成结果处理、评测指标计算等功能
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RAGService, cls).__new__(cls)
        return cls._instance

    def __init__(self, config: RAGConfig | None = None):
        if hasattr(self, "_initialized") and self._initialized:
            return

        logger.info("Initializing RAGService")
        self.config = config or DefaultRAGConfig
        self.db_config = settings.database
        self.embeddings = get_embedding_model(self.config)

        self.retrieval_modules: Dict[str, RetrievalOptimizationModule] = {}
        self.reranker: BaseReranker | None = None

        # 初始化向量数据库连接
        self._init_vector_stores()

        self.generation_module = GenerationIntegrationModule(llm_type="fast")

        self.metadata_filter_extractor = MetadataFilterExtractor(llm_type="fast")

        if self.config.reranker.enabled:
            if self.config.reranker.type == "siliconflow":
                from app.rag.rerankers.siliconflow_reranker import SiliconFlowReranker

                self.reranker = SiliconFlowReranker(self.config.reranker)
            else:
                logger.warning(
                    f"Reranker type '{self.config.reranker.type}' not recognized. Reranking disabled."
                )

        # 初始化缓存管理器（如果启用）
        self.cache_manager: CacheManager | None = None
        if self.config.cache.enabled:
            self.cache_manager = CacheManager(
                redis_host=self.db_config.redis.host,
                redis_port=self.db_config.redis.port,
                redis_db=self.db_config.redis.db,
                redis_password=self.db_config.redis.password,
                ttl=self.config.cache.ttl,
                similarity_threshold=self.config.cache.similarity_threshold,
                embeddings=self.embeddings,
                l2_enabled=self.config.cache.l2_enabled,
                vector_host=self.db_config.milvus.host,
                vector_port=self.db_config.milvus.port,
                vector_collection=self.config.cache.vector_collection,
                vector_user=self.db_config.milvus.user,
                vector_password=self.db_config.milvus.password,
                vector_secure=self.db_config.milvus.secure,
            )
            logger.info("Cache manager enabled")
        else:
            logger.info("Caching disabled")
        
        # 初始化私人菜谱文档的 Markdown 解析器
        self._md_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "header_1"), ("##", "header_2")],
            strip_headers=False,
        )

        self._initialized = True
        logger.info("RAGService initialized")

    def _init_vector_stores(self):
        """
        初始化向量数据库milvus连接
        """
        logger.info("Initializing vector store connections")

        for name in ("recipes", "personal"):
            collection = self.config.vector_store.collection_names.get(name)
            if not collection:
                continue
            try:
                vector_store = get_vector_store(
                    milvus_config=self.db_config.milvus,
                    collection_name=collection,
                    embeddings=self.embeddings,
                    chunks=[],
                    force_rebuild=False,
                )
                retrieval_module = RetrievalOptimizationModule(
                    vectorstore=vector_store,
                    score_threshold=self.config.retrieval.score_threshold,
                    default_ranker_type=self.config.retrieval.ranker_type,
                    default_ranker_weights=self.config.retrieval.ranker_weights,
                )
                self.retrieval_modules[name] = retrieval_module
                logger.info("Connected to %s collection: %s", name, collection)
            except Exception as e:
                logger.warning("Failed to connect to %s collection: %s", name, e)

    # =========================================================================
    # Public API
    # =========================================================================

    async def retrieve(
        self,
        query: str,
        use_intelligent_ranker: bool = True,
        skip_rewrite: bool = False,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> RetrievalResult:
        """
        仅执行查询改写与检索流程，不进行 LLM 生成

        负责：
        - 查询改写（Query Rewriting）
        - 知识检索（Retrieval）

        不负责：
        - LLM 回答生成（Generation）
        """
        if not self.retrieval_modules:
            raise RuntimeError("RAG Service is not properly initialized.")

        logger.info("retrieval start query='%s'", query[:80])

        # Query 重写
        rewritten_query = (
            query
            if skip_rewrite
            else await self.generation_module.rewrite_query(
                query, user_id=user_id, conversation_id=conversation_id
            )
        )

        # 元数据过滤提取（从缓存元数据，不访问数据库）
        filter_catalog = document_repository.get_metadata_for_filter(user_id)
        metadata_expression = (
            await self.metadata_filter_extractor.build_filter_expression(
                query, filter_catalog, user_id, conversation_id
            )
        )

        # 执行所有来源的检索（包括公共和私人）
        all_retrieved_docs = await self._execute_retrieval(
            rewritten_query,
            self.config.retrieval.top_k,
            use_intelligent_ranker,
            metadata_expression,
            user_id,
        )

        # 重排
        reranked_docs = await self._rerank_if_needed(
            rewritten_query, all_retrieved_docs
        )

        # 处理检索结果（从数据库获取父文档）
        processed_docs = await document_processor.post_process_retrieval(reranked_docs)

        # 构建上下文字符串
        context_parts = [doc.page_content for doc in processed_docs]
        context = "\n\n".join(context_parts) if context_parts else ""

        # 提取检索来源信息
        sources = self._extract_sources(processed_docs)
        self._log_retrieval_summary("processed", processed_docs)

        return RetrievalResult(
            original_query=query,
            rewritten_query=rewritten_query,
            context=context,
            documents=processed_docs,
            sources=sources,
        )

    # =========================================================================
    # 检索执行模块
    # =========================================================================

    async def _execute_retrieval(
        self,
        rewritten_query: str,
        top_k: int,
        use_intelligent_ranker: bool,
        metadata_expression: Optional[str],
        user_id: Optional[str] = None,
    ) -> List[Document]:
        """聚合多个数据源的结果检索"""
        all_docs: List[Document] = []

        for source_name, module in self.retrieval_modules.items():
            docs = await self._retrieve_from_source(
                source_name=source_name,
                retrieval_module=module,
                rewritten_query=rewritten_query,
                top_k=top_k,
                use_intelligent_ranker=use_intelligent_ranker,
                metadata_expression=metadata_expression,
                user_id=user_id,
            )
            all_docs.extend(docs)

            self._log_retrieval_summary(f"source={source_name}", docs)

        logger.info("aggregated retrieved docs=%d", len(all_docs))
        return all_docs

    async def _retrieve_from_source(
        self,
        source_name: str,
        retrieval_module: RetrievalOptimizationModule,
        rewritten_query: str,
        top_k: int,
        use_intelligent_ranker: bool,
        metadata_expression: Optional[str],
        user_id: Optional[str] = None,
    ) -> List[Document]:
        """从单个数据源检索文档并使用缓存."""
        logger.info("retrieving source=%s", source_name)

        # 先查缓存
        if self.cache_manager:
            cached_docs = await self.cache_manager.get(
                source_name,
                rewritten_query,
                user_id if source_name == "personal" else None,
            )
            if cached_docs:
                logger.info(
                    "Using cached results for source '%s': %d documents",
                    source_name,
                    len(cached_docs),
                )
                for doc in cached_docs:
                    if "retrieval_score" not in doc.metadata:
                        doc.metadata["retrieval_score"] = 1.0
                    doc.metadata["data_source"] = source_name
                return cached_docs

        # 确定ranker配置
        ranker_type = ranker_weights = None
        if use_intelligent_ranker:
            ranker_type, ranker_weights = retrieval_module.intelligent_ranker_selection(
                rewritten_query
            )

        # 执行检索
        try:
            expr = self._build_filter_expr(metadata_expression, source_name, user_id)
            retrieved_docs, retrieved_scores = await retrieval_module.hybrid_search(
                rewritten_query,
                top_k=top_k,
                ranker_type=ranker_type,
                ranker_weights=ranker_weights,
                expr=expr,
            )
        except Exception as exc:
            logger.error(
                "Error during retrieval from source '%s': %s", source_name, exc
            )
            return []

        # 为文档补充评分信息和来源信息
        for doc, score in zip(retrieved_docs, retrieved_scores):
            existing_source = doc.metadata.get("data_source")
            if existing_source and existing_source != source_name:
                logger.warning(
                    "Data source mismatch (metadata=%s, expected=%s). Overriding.",
                    existing_source,
                    source_name,
                )
            doc.metadata["data_source"] = existing_source or source_name
            doc.metadata["retrieval_score"] = score

        # 按 parent_id 去重，并保留得分最高的文档
        unique_docs: Dict[Optional[str], Document] = {}
        for doc in retrieved_docs:
            parent_id = doc.metadata.get("parent_id")
            if parent_id not in unique_docs:
                unique_docs[parent_id] = doc
            elif (
                doc.metadata["retrieval_score"]
                > unique_docs[parent_id].metadata["retrieval_score"]
            ):
                unique_docs[parent_id] = doc

        final_docs = sorted(
            unique_docs.values(),
            key=lambda d: d.metadata.get("retrieval_score", 0.0),
            reverse=True,
        )

        # 缓存检索结果
        if self.cache_manager:
            await self.cache_manager.set(
                source_name,
                rewritten_query,
                final_docs,
                user_id if source_name == "personal" else None,
            )

        return final_docs

    @staticmethod
    def _build_filter_expr(
        metadata_expression: Optional[str], source_name: str, user_id: Optional[str]
    ) -> Optional[str]:
        """根据用户ID构建过滤表达式，用于个人文档的检索."""
        if source_name != "personal" or not user_id:
            return metadata_expression

        user_filter = f'user_id == "{user_id}"'
        if metadata_expression:
            return f"({metadata_expression}) and ({user_filter})"
        return user_filter

    # =========================================================================
    # Personal document management
    # =========================================================================

    async def add_personal_document(
        self,
        *,
        user_id: str,
        document_id: str,
        dish_name: str,
        category: str,
        difficulty: str,
        data_source: str,
        content: str,
    ) -> None:
        """添加个人菜谱文档到向量数据库"""
        if not user_id:
            raise ValueError("user_id is required for personal documents")

        if "personal" not in self.retrieval_modules:
            raise RuntimeError("Personal retriever not initialized")

        metadata = {
            "source": f"personal::{user_id}",
            "parent_id": document_id,
            "dish_name": dish_name,
            "category": category,
            "difficulty": difficulty,
            "is_dish_index": False,
            "data_source": "personal",
            "user_id": user_id,
            "source_type": data_source,
        }

        # 分块
        chunks = document_processor.create_chunks(document_id, content, metadata)

        if chunks:
            retrieval_module = self.retrieval_modules["personal"]
            await asyncio.to_thread(retrieval_module.vectorstore.add_documents, chunks)
            logger.info("Indexed %d personal chunks for user %s", len(chunks), user_id)

    async def update_personal_document(
        self,
        *,
        user_id: str,
        document_id: str,
        dish_name: str,
        category: str,
        difficulty: str,
        data_source: str,
        content: str,
    ) -> None:
        """更新个人菜谱文档"""
        await self.delete_personal_document(user_id=user_id, document_id=document_id)
        await self.add_personal_document(
            user_id=user_id,
            document_id=document_id,
            dish_name=dish_name,
            category=category,
            difficulty=difficulty,
            data_source=data_source,
            content=content,
        )
        logger.info("Updated personal document id=%s user=%s", document_id, user_id)

    async def delete_personal_document(
        self,
        *,
        user_id: str,
        document_id: str,
    ) -> None:
        """删除个人菜谱文档的所有 chunks"""
        if "personal" not in self.retrieval_modules:
            logger.warning("Personal retriever not initialized, skipping delete")
            return

        retrieval_module = self.retrieval_modules["personal"]
        expr = f'parent_id == "{document_id}" and user_id == "{user_id}"'

        try:
            await asyncio.to_thread(
                retrieval_module.vectorstore.col.delete,  # type: ignore
                expr,
            )
            logger.info(
                "Deleted personal document chunks id=%s user=%s", document_id, user_id
            )
        except Exception as e:
            logger.warning("Failed to delete personal document chunks: %s", e)

    # =========================================================================
    # Helper methods
    # =========================================================================

    async def _rerank_if_needed(self, rewritten_query: str, docs_for_rerank):
        if self.reranker and self.config.reranker.enabled:
            logger.info("reranking docs=%d", len(docs_for_rerank))
            return await self.reranker.rerank(rewritten_query, docs_for_rerank)
        return docs_for_rerank

    def _log_retrieval_summary(self, stage: str, docs: List[Document]) -> None:
        """记录检索结果元数据日志"""
        summaries = []
        for doc in docs:
            meta = doc.metadata or {}
            summaries.append(
                {
                    "rerank_score": meta.get("rerank_score"),
                    "dish_name": meta.get("dish_name"),
                    "difficulty": meta.get("difficulty"),
                    "category": meta.get("category"),
                    "parent_id": meta.get("parent_id"),
                    "retrieval_score": meta.get("retrieval_score"),
                }
            )
        logger.info("retrieval %s docs=%d", stage, len(docs))
        for summary in summaries:
            logger.info("  %s", summary)

    def _extract_sources(self, documents: List[Document]) -> List[Dict]:
        """
        从文档中提取来源信息，用于前端显示。

        返回统一格式：{"type": "rag", "info": str, "url": optional str}
        info 字段结合 dish_name/title。
        """
        sources = []
        seen = set()

        for doc in documents:
            metadata = doc.metadata or {}
            # 从标题或分类中构建 info 字段
            title = (
                metadata.get("dish_name")
                or metadata.get("title")
                or metadata.get("source_title")
            )
            info = title or metadata.get("category") or "CookAgent 知识库"

            # 构建统一来源字典，包含 type 和 info 字段
            source_info: Dict[str, str] = {
                "type": "rag",  # Always "rag" for knowledge base sources
                "info": info,
            }

            # 如果有 URL，添加到字典
            if metadata.get("url"):
                source_info["url"] = str(metadata["url"])

            # 按 (type, info) 去重
            key = (source_info["type"], source_info["info"])
            if key not in seen:
                seen.add(key)
                sources.append(source_info)

        return sources


rag_service_instance = RAGService()
