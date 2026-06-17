import logging
import httpx
from typing import List

from app.rag.rerankers.base import BaseReranker
from langchain_core.documents import Document
from app.config.rag_config import RerankerConfig

logger = logging.getLogger(__name__)

class SiliconFlowReranker(BaseReranker):
    """
    SiliconFlow Reranker
    用于对文档列表进行重新排序或过滤，根据用户查询。
    """

    def __init__(self, reranker_config: RerankerConfig):
        """
        初始化 SiliconFlow Reranker
        Args:
            reranker_config: Reranker 配置
        """
        self.config = reranker_config
        self.api_url = self.config.base_url
        self.headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

    async def rerank(self, query: str, documents: List[Document]) -> List[Document]:
        """
        使用 SiliconFlow API 对文档进行重新排序和过滤。

        Args:
            query: 用户查询文本
            documents: 待重新排序的文档列表

        Returns:
            重新排序后的文档列表
        """
        if not documents:
            return []

        logger.info(f"Reranking {len(documents)} documents with SiliconFlow API...")
        
        doc_contents = [doc.page_content for doc in documents]
        
        payload = {
            "model": self.config.model_name,
            "query": query,
            "documents": doc_contents,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.api_url, headers=self.headers, json=payload, timeout=30.0)  # type: ignore
                response.raise_for_status()
                api_results = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred during rerank API call: {e}")
            logger.error(f"Response content: {e.response.text}")
            return documents
        except Exception as e:
            logger.error(f"An unexpected error occurred during rerank API call: {e}")
            return documents

        results = api_results.get("results", [])
        if not results:
            logger.warning("Rerank API returned no results.")
            return []

        # 过滤并排序文档
        ranked_docs = []
        for res in results:
            score = res.get("relevance_score", 0.0)
            index = res.get("index")

            logger.info(f"Document {documents[index].metadata.get('dish_name', 'unknown')} received rerank score: {score}")

            if score >= self.config.score_threshold * 0.9:
                # API 返回的 index 与原始 documents 列表中的文档一一对应
                original_doc = documents[index]
                # 存储新的 rerank 分数到元数据中，用于后续 downstream 子任务中使用
                original_doc.metadata["rerank_score"] = score
                ranked_docs.append(original_doc)
        
        # 按 rerank_score 降序排序文档
        ranked_docs.sort(key=lambda doc: doc.metadata.get("rerank_score", 0.0), reverse=True)

        logger.info(f"Reranking complete. {len(documents)} -> {len(ranked_docs)} documents.")
        
        return ranked_docs
