"""
RAG 统一文档处理器
负责文档分块（Chunk Splitting）以及检索结果文档的后处理
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from app.database.document_repository import document_repository

logger = logging.getLogger(__name__)


# 所有文档都必须包含的元数据键值
REQUIRED_METADATA_KEYS = (
    "source",
    "parent_id",
    "dish_name",
    "category",
    "difficulty",
    "is_dish_index",
    "data_source",
    "user_id",
    "source_type",
)


class DocumentProcessor:
    """
    RAG 统一文档处理器
    负责文档分块（Chunk Splitting）以及检索结果文档的后处理
    """

    def __init__(self, headers_to_split_on: List[tuple] | None = None):
        self.headers_to_split_on = headers_to_split_on or [
            ("#", "header_1"),
            ("##", "header_2"),
        ]
        self._splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on,
            strip_headers=False,
        )

    def create_chunks(
        self,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any],
    ) -> List[Document]:
        """
        将文档拆分为用于向量索引的多个 Chunk
        
        Args:
            doc_id: 父文档 ID（将以 parent_id 的形式存储到 Chunk 元数据中）
            content: 待拆分的文档内容
            metadata: 基础元数据（会复制到每个 Chunk 中）
        Returns:
            List of Documents，每个文档都有一个 parent_id 元数据键
        """
        chunks: List[Document] = []
        
        # 按标题拆分文档
        md_chunks = self._splitter.split_text(content)
        
        for chunk_doc in md_chunks:
            chunk_metadata = self._clone_metadata(metadata, parent_id=doc_id)
            chunks.append(Document(
                id=str(uuid.uuid4()),
                page_content=chunk_doc.page_content,
                metadata=chunk_metadata,
            ))
        
        return chunks

    async def post_process_retrieval(
        self,
        retrieved_chunks: List[Document],
    ) -> List[Document]:
        """
        将检索到的 Chunk 转换回完整的父文档。
        从数据库中获取父文档。
        
        实现 "small to large" 检索模式:
        - 按 parent_id 分组 chunks
        - 从 PostgreSQL 获取完整的父文档内容
        - 保留每个父文档的最高检索分和重排分
        
        Args:
            retrieved_chunks: List of Documents，每个文档都有一个 parent_id 元数据键
            
        Returns:
            List of Documents，每个文档都有完整的父文档内容
        """
        if not retrieved_chunks:
            return []

        # 按 parent_id 聚合分数
        parent_scores: Dict[str, Dict[str, float]] = {}
        
        for chunk in retrieved_chunks:
            parent_id = chunk.metadata.get("parent_id")
            if not parent_id:
                continue
            
            retrieval_score = chunk.metadata.get("retrieval_score", 0.0)
            rerank_score = chunk.metadata.get("rerank_score")
            
            if parent_id not in parent_scores:
                parent_scores[parent_id] = {
                    "retrieval_score": retrieval_score,
                    "rerank_score": rerank_score if rerank_score is not None else 0.0,
                    "is_index": chunk.metadata.get("is_dish_index", False),
                }
            else:
                # 保留最高分数的文档
                if retrieval_score > parent_scores[parent_id]["retrieval_score"]:
                    parent_scores[parent_id]["retrieval_score"] = retrieval_score
                if rerank_score is not None and rerank_score > parent_scores[parent_id].get("rerank_score", 0.0):
                    parent_scores[parent_id]["rerank_score"] = rerank_score

        # 从数据库获取父文档内容
        parent_ids = list(parent_scores.keys())
        parent_docs = await document_repository.get_parent_documents(parent_ids)

        # 创建新的 Document 列表，包含完整内容和分数信息
        final_docs: List[Document] = []
        
        for parent_id, scores in parent_scores.items():
            if parent_id not in parent_docs:
                logger.warning("Parent document not found in database: %s", parent_id)
                continue
            
            parent_doc = parent_docs[parent_id]
            
            doc_copy = Document(
                id=parent_doc.id,
                page_content=parent_doc.page_content,
                metadata=parent_doc.metadata.copy(),
            )
            doc_copy.metadata["retrieval_score"] = scores["retrieval_score"]
            if scores.get("rerank_score"):
                doc_copy.metadata["rerank_score"] = scores["rerank_score"]
            
            final_docs.append(doc_copy)
    
        # Sort by rerank_score 降序排序，再按 retrieval_score 降序排序
        final_docs.sort(
            key=lambda d: (
                d.metadata.get("rerank_score", 0.0),
                d.metadata.get("retrieval_score", 0.0),
            ),
            reverse=True,
        )

        logger.info(
            "Post-processed %d chunks -> %d parent documents",
            len(retrieved_chunks),
            len(final_docs),
        )
        
        return final_docs

    def _clone_metadata(
        self,
        metadata: Dict[str, Any],
        *,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """复制元数据并设置父文档 ID parent_id."""
        cloned = {key: metadata.get(key) for key in REQUIRED_METADATA_KEYS}
        if parent_id is not None:
            cloned["parent_id"] = parent_id
        return cloned

    def _create_index_chunk_content(self, index_metadata: Dict[str, Any]) -> str:
        """
        创建菜品索引文档的 Chunk 内容。
        突出推荐关键词，以提高语义匹配。
        """
        content_parts = ["推荐菜,菜谱列表,菜品,食谱,有哪些菜品推荐"]
        
        source = index_metadata.get("source", "")
        category = index_metadata.get("category", "")
        difficulty = index_metadata.get("difficulty", "")

        if "category" in source and category:
            content_parts.append(f"{category}推荐，")
        elif "difficulty" in source and difficulty:
            content_parts.append(f"{difficulty}难度推荐，")

        content_parts.append("欢迎根据口味挑选合适的菜谱")
        return "".join(content_parts)


document_processor = DocumentProcessor()
