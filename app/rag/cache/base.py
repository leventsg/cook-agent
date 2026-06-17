"""
缓存后端接口

- KeywordCacheBackend：
  基于键值对的缓存（用于精确匹配， Redis 缓存）

- VectorCacheBackend：
  基于向量插入与检索的缓存（用于语义匹配， Milvus 实现）
"""
from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple


class KeywordCacheBackend(ABC):
    """基于键值对的缓存（用于精确匹配）"""
    
    @abstractmethod
    async def get(self, key: str):
        """Get a value by key."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
        """Set a value with optional TTL."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value by key."""
        pass
    
    @abstractmethod
    async def clear(self, pattern: str | None = None) -> bool:
        """Clear cache entries matching pattern."""
        pass


class VectorCacheBackend(ABC):
    """基于向量插入与检索的缓存（用于语义匹配）"""
    
    @abstractmethod
    async def add(
        self,
        key: str,
        embedding: List[float],
        payload: Any,
        ttl_seconds: int | None = None,
        scope: str | None = None,
    ) -> bool:
        """
        将向量与payload添加到缓存中，可选过期时间。
        
        Args:
            key: 唯一键缓存键
            embedding: 搜索向量嵌入
            payload: 缓存数据
            ttl_seconds: 可选缓存过期时间（秒）
        """
        pass
    
    @abstractmethod
    async def search(
        self,
        embedding: List[float],
        threshold: float,
        scope: str | None = None,
    ) -> Optional[Tuple[Any, float]]:
        """
        搜索相似向量，返回(payload, 相似度分数)
        
        Args:
            embedding: 查询向量嵌入
            threshold: 最小相似度阈值
            scope: 可选作用域（例如用户ID）
        """
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """Clear all cached vectors."""
        pass

