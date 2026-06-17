"""
RAG 检索结果缓存管理器

缓存策略：

- L1 缓存（精确匹配）
  基于 Redis 实现
  key = hash(query)
  value = 序列化后的检索文档

- L2 缓存（语义匹配）
  基于 Milvus 实现
  通过向量相似度检索查找语义相近的查询

仅缓存：
- Query → Retrieved Documents（检索上下文）

不缓存：
- LLM 生成的回答结果
"""
import hashlib
import logging
import pickle
from typing import List, Optional

import redis.asyncio as redis
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.rag.cache.base import KeywordCacheBackend, VectorCacheBackend
from app.rag.cache.backends import MilvusVectorCache, RedisKeywordCache

logger = logging.getLogger(__name__)


class CacheManager:
    """
    管理 RAG 检索结果的两级缓存

    L1 缓存（Redis - 精确匹配）：
    - 用于相同查询的快速命中
    - Key：重写后查询的哈希值
    - Value：序列化后的检索文档列表

    L2 缓存（Milvus - 语义匹配）：
    - 处理语义高度相似的查询变体
    - 使用向量 Embedding 执行相似度检索
    - 当 L1 缓存未命中但存在相似查询时作为回退方案
    """
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        ttl: int = 3600,
        similarity_threshold: float = 0.92,
        embeddings: Optional[Embeddings] = None,
        l2_enabled: bool = True,
        vector_host: Optional[str] = None,
        vector_port: Optional[int] = None,
        vector_collection: str = "cookagent_retrieval_cache",
        vector_user: Optional[str] = None,
        vector_password: Optional[str] = None,
        vector_secure: bool = False,
    ):
        """
        初始化缓存管理器
        
        Args:
            redis_host: 主机地址
            redis_port: 端口号
            redis_db: 数据库编号
            redis_password: 密码
            similarity_threshold: L2 缓存匹配阈值（0-1）
            embeddings: 语义匹配模型
            l2_enabled: 是否启用 L2 缓存
            vector_host/vector_port: Milvus 连接信息
            vector_collection: Milvus 缓存集合名称
            vector_user/vector_password: Milvus 用户名和密码
            vector_secure: 是否使用 TLS
        """
        self.ttl = ttl
        self.similarity_threshold = similarity_threshold
        self.l2_enabled = l2_enabled
        self.embeddings = embeddings
        
        # 初始化 Redis 连接（L1 缓存）
        self.redis_client: Optional[redis.Redis] = None
        self.keyword_cache: Optional[KeywordCacheBackend] = None
        try:
            client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            self.redis_client = client
            self.keyword_cache = RedisKeywordCache(client)
            logger.info(f"Redis L1 cache connected: {redis_host}:{redis_port}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. L1 cache disabled.")
        
        # 初始化 Milvus 连接 (L2 缓存)
        self.vector_cache: Optional[VectorCacheBackend] = None
        self._embedding_dimension: Optional[int] = None
        
        if self.l2_enabled and self.embeddings:
            self._embedding_dimension = self._infer_embedding_dimension()
            if self._embedding_dimension:
                host = vector_host or redis_host
                port = vector_port or 19530
                try:
                    self.vector_cache = MilvusVectorCache(
                        host=host,
                        port=port,
                        collection_name=vector_collection,
                        dimension=self._embedding_dimension,
                        user=vector_user,
                        password=vector_password,
                        secure=vector_secure,
                    )
                    logger.info(f"Milvus L2 cache connected: {host}:{port} (collection={vector_collection})")
                except Exception as exc:
                    logger.warning(f"Failed to initialize Milvus L2 cache: {exc}")
                    self.l2_enabled = False
            else:
                logger.warning("Could not infer embedding dimension. L2 cache disabled.")
                self.l2_enabled = False
        elif self.l2_enabled:
            logger.warning("Embeddings not provided. L2 cache disabled.")
            self.l2_enabled = False
    
    def _compute_hash(self, text: str) -> str:
        """计算字符串的 SHA256 哈希值"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def _get_cache_key(self, data_source: str, query: str, scope: str | None = None) -> str:
        """生成检索query的缓存键"""
        query_hash = self._compute_hash(query)
        scope_label = scope or "global"
        return f"rag:retrieval:{data_source}:{scope_label}:{query_hash}"
    
    async def get(
        self,
        data_source: str,
        query: str,
        scope: str | None = None,
    ) -> Optional[List[Document]]:
        """
        使用 L1 + L2 策略获取缓存的检索结果
        
        Args:
            data_source: 数据源名称
            query: 查询字符串（通常是重写后的查询）
            
        Returns:
            如果找到缓存文档 否则返回 None
        """
        # 先尝试 L1 缓存（精确匹配）
        if self.keyword_cache:
            try:
                cache_key = self._get_cache_key(data_source, query, scope)
                cached_data = await self.keyword_cache.get(cache_key)
                
                if cached_data:
                    docs = pickle.loads(cached_data)
                    logger.info(f"L1 cache HIT for '{data_source}': {len(docs)} documents")
                    return docs
            except Exception as e:
                logger.warning(f"Error reading L1 cache: {e}")
        
        # 再尝试 L2 缓存（语义相似度）
        if self._should_use_l2():
            try:
                query_embedding = self.embeddings.embed_query(query)  
                result = await self.vector_cache.search(  
                    query_embedding,
                    self.similarity_threshold,
                    scope=scope,
                )
                
                if result:
                    cached_data, similarity = result
                    if cached_data:
                        docs = pickle.loads(cached_data)
                        logger.info(f"L2 cache HIT for '{data_source}': similarity={similarity:.4f}, {len(docs)} documents")
                        return docs
            except Exception as e:
                logger.warning(f"Error reading L2 cache: {e}")
        
        logger.debug(f"Cache MISS for '{data_source}'")
        return None
    
    async def set(
        self,
        data_source: str,
        query: str,
        documents: List[Document],
        scope: str | None = None,
    ) -> bool:
        """
        设置 L1 + L2 缓存检索结果
        
        Args:
            data_source: 数据源名称
            query: 查询字符串（通常是重写后的查询）
            documents: 要缓存的文档
            
        Returns:
            如果缓存成功则返回 True，失败返回 False
        """
        serialized = pickle.dumps(documents)
        success = True
        
        # 先设置 L1 缓存（精确匹配）
        if self.keyword_cache:
            try:
                cache_key = self._get_cache_key(data_source, query, scope)
                stored = await self.keyword_cache.set(cache_key, serialized, ttl_seconds=self.ttl)
                if stored:
                    logger.info(f"L1 cache SET for '{data_source}': {len(documents)} documents (TTL={self.ttl}s)")
                else:
                    success = False
            except Exception as e:
                logger.warning(f"Error writing L1 cache: {e}")
                success = False
        
        # 再设置 L2 缓存
        if self._should_use_l2():
            try:
                query_embedding = self.embeddings.embed_query(query)
                scoped = scope or "global"
                cache_key = self._compute_hash(f"{data_source}:{scoped}:{query}")
                stored = await self.vector_cache.add( 
                    cache_key,
                    query_embedding,
                    serialized,
                    ttl_seconds=self.ttl,
                    scope=scope,
                )
                if stored:
                    logger.info(f"L2 cache SET for '{data_source}': semantic index updated")
                else:
                    success = False
            except Exception as e:
                logger.warning(f"Error writing L2 cache: {e}")
                success = False
        
        return success
    
    def _infer_embedding_dimension(self) -> Optional[int]:
        """通过运行测试查询来推断嵌入维度"""
        if not self.embeddings:
            return None
        try:
            probe = self.embeddings.embed_query("test query for dimension")
            return len(probe)
        except Exception as exc:
            logger.warning(f"Failed to infer embedding dimension: {exc}")
            return None
    
    def _should_use_l2(self) -> bool:
        """检查是否应该使用 L2 缓存"""
        return bool(self.l2_enabled and self.vector_cache and self.embeddings)