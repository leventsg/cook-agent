import asyncio
import logging
from typing import List, Tuple, Optional

from langchain_milvus import Milvus
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

class RetrievalOptimizationModule:
    """
    负责基于 Milvus 内置混合检索能力实现高级检索策略
    结合稠密向量检索与稀疏 BM25 检索，
    利用 Milvus 原生能力执行混合搜索
    """
    def __init__(
        self, 
        vectorstore: Milvus, 
        score_threshold: float = 0.0,
        default_ranker_type: str = "rrf",
        default_ranker_weights: List[float] = [0.5, 0.5]
    ):
        """
        初始化检索优化模块。
        Args:
            vectorstore: 包含 BM25 内置函数的 Milvus 向量存储
            score_threshold: 过滤低质量结果的最小分数阈值
            default_ranker_type: 默认排名器类型 ("rrf" 或 "weighted")  rrf: 基于排名的融合，不依赖绝对分数；weighted: 基于权重的融合，依赖绝对分数
            default_ranker_weights: 当使用加权排名器时，默认权重 [语义搜索, 关键词搜索]
        """
        if not vectorstore:
            raise ValueError("Vectorstore must be provided.")
            
        self.vectorstore = vectorstore
        self.score_threshold = score_threshold
        self.default_ranker_type = default_ranker_type
        self.default_ranker_weights = default_ranker_weights
        
        logger.info("Retrieval module initialized with Milvus hybrid search")
        
    async def hybrid_search(
        self, 
        query: str, 
        top_k: int,
        ranker_type: Optional[str] = None,
        ranker_weights: Optional[List[float]] = None,
        score_threshold: Optional[float] = None,
        expr: Optional[str] = None,
    ) -> Tuple[List[Document], List[float]]:
        """
        使用 Milvus 内置 BM25 与稠密向量检索执行混合搜索
        支持动态排序器配置以及基于得分的结果过滤
        
        Args:
            query: 用户查询
            top_k: 返回的最大文档数（在过滤前）
            ranker_type: 排序器类型 ("rrf" 或 "weighted") 
            ranker_weights: 当使用加权排名器时，权重 [稠密向量,稀疏向量]
            score_threshold: 过滤低质量结果的最小分数阈值
            
        Returns:
            (文档列表, 分数列表)
        """
        ranker_type = ranker_type or self.default_ranker_type
        ranker_weights = ranker_weights or self.default_ranker_weights
        score_threshold = score_threshold if score_threshold is not None else self.score_threshold
        
        logger.info(
            "hybrid search top_k=%d ranker=%s threshold=%s",
            top_k,
            ranker_type,
            score_threshold,
        )
        
        # 配置排名器参数
        ranker_params = {"norm_score": True}
        if ranker_type == "weighted":
            ranker_params = {"weights": ranker_weights, "norm_score": True}
        
        # Milvus 混合搜索
        # 使用 asyncio.to_thread 并发执行混合搜索
        results = await asyncio.to_thread(
            self.vectorstore.similarity_search_with_score,
            query=query,
            k=top_k,
            fetch_k=int(top_k * 4),
            ranker_type=ranker_type,
            ranker_params=ranker_params if ranker_params else None,
            expr=expr,
        )
        
        # 提取文档和分数
        docs, scores = [], []
        for doc, score in results:
            docs.append(doc)
            scores.append(score)
        
        logger.info("hybrid search docs=%d", len(docs))
        
        # 基于得分过滤结果
        if score_threshold > 0 and ranker_type == "weighted":
            filtered_results = [(doc, score) for doc, score in zip(docs, scores) if score >= score_threshold]
            filtered_docs, filtered_scores = [], []
            for doc, score in filtered_results:
                filtered_docs.append(doc)
                filtered_scores.append(score)
            
            logger.info(
                "score filtering %d -> %d (threshold=%s)",
                len(docs),
                len(filtered_docs),
                score_threshold,
            )
            
            return filtered_docs, filtered_scores
        
        return docs, scores
    
    def intelligent_ranker_selection(self, query: str) -> Tuple[str, List[float]]:
        """
        智能选择排名器类型和权重
        可以扩展为更复杂的逻辑或 ML 模型
        
        Args:
            query: 用户查询
            
        Returns:
            (ranker_type, weights)
        """
        query_lower = query.lower()
        
        # 关键词查询（包含具体术语）→ 优先 BM25 搜索偏置
        keyword_indicators = ["怎么做", "如何", "步骤", "方法", "做法", "recipe", "how to"]
        if any(indicator in query_lower for indicator in keyword_indicators):
            logger.debug("keyword indicators detected; weighted ranker BM25 bias")
            return "weighted", [0.4, 0.6]  # Favor sparse/BM25
        
        # 语义/概念查询（包含推荐、类似、什么菜等）→ 优先稠密向量搜索偏置
        # 扩展指示符以包含推荐查询
        semantic_indicators = [
            "推荐", "类似", "什么菜", "有哪些", "有什么", "适合", "建议", 
            "recommend", "similar", "suggest", "what", "which",
        ]
        if any(indicator in query_lower for indicator in semantic_indicators):
            logger.debug("semantic indicators detected; weighted ranker dense bias")
            return "weighted", [0.6, 0.4]  # Favor dense/semantic
        
        # 使用默认权重（平衡查询）
        return "weighted", [0.5, 0.5]
