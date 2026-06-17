"""缓存实现"""
import asyncio
import base64
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import redis.asyncio as redis
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from app.rag.cache.base import KeywordCacheBackend, VectorCacheBackend

logger = logging.getLogger(__name__)


class RedisKeywordCache(KeywordCacheBackend):
    """Redis 基于的关键词缓存后端（精确匹配，L1 缓存）"""
    
    def __init__(self, client: redis.Redis):
        """
        初始化 Redis 关键词缓存后端
        
        Args:
            client: Redis 客户端实例
        """
        self.client = client

    async def get(self, key: str):
        """get key"""
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.warning(f"Error getting key '{key}' from Redis: {e}")
            return None

    async def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
        """set key"""
        try:
            if ttl_seconds is not None:
                result = await self.client.setex(key, ttl_seconds, value)
            else:
                result = await self.client.set(key, value)
            success = bool(result)
            if not success:
                logger.warning("Redis did not acknowledge set for key '%s'", key)
            return success
        except Exception as e:
            logger.warning(f"Error setting key '{key}' in Redis: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key"""
        try:
            deleted = await self.client.delete(key)
            success = deleted > 0
            if not success:
                logger.debug("Redis delete skipped for key '%s' (not found)", key)
            return success
        except Exception as e:
            logger.warning(f"Error deleting key '{key}' from Redis: {e}")
            return False

    async def clear(self, pattern: str | None = None) -> bool:
        """Clear all keys matching a pattern."""
        pat = pattern or "*"
        try:
            cursor = 0
            while True:
                cursor, keys = await self.client.scan(cursor=cursor, match=pat, count=500)
                if keys:
                    await self.client.delete(*keys)
                if cursor == 0:
                    break
            return True
        except Exception as e:
            logger.warning(f"Error clearing Redis cache with pattern '{pat}': {e}")
            return False


class MilvusVectorCache(VectorCacheBackend):
    """Milvus 基于的向量缓存"""

    def __init__(
        self,
        host: str,
        port: int,
        collection_name: str,
        dimension: int,
        user: Optional[str] = None,
        password: Optional[str] = None,
        secure: bool = False,
        alias: str = "cache_milvus",
        index_params: Optional[Dict[str, Any]] = None,
        search_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        if dimension <= 0:
            raise ValueError("Embedding dimension for MilvusVectorCache must be positive")
        self._collection_name = collection_name
        self._dimension = dimension
        self._alias = alias
        self._search_params = search_params or {
            "metric_type": "IP",
            "params": {"nprobe": 16},
        }
        # 索引类型：内积计算相似度、倒排索引（索引），nlist 是聚类中心数量
        self._index_params = index_params or {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 1024},
        }

        self._connect(host, port, user, password, secure)
        self._collection = self._get_or_create_collection(force_build=True)
        self._ensure_index()
        self._collection.load()

    async def add(
        self,
        key: str,
        embedding: List[float],
        payload: Any,
        ttl_seconds: int | None = None,
        scope: str | None = None,
    ) -> bool:
        # 向量归一化处理
        vector = np.asarray(embedding, dtype="float32")
        if vector.ndim != 1 or vector.shape[0] != self._dimension:
            logger.warning(
                "Milvus vector cache expects 1-D embeddings of size %d. Got shape %s",
                self._dimension,
                vector.shape,
            )
            return False

        norm = np.linalg.norm(vector)
        if norm == 0.0:
            logger.warning("Skipping zero vector for cache key '%s'", key)
            return False
        normalized = (vector / norm).tolist()
        expires_at = time.time() + ttl_seconds if ttl_seconds else 0.0
        # scope 用于区分不同的缓存命名空间，默认为 "global"
        scope_value = scope or "global"

        # 删除已有的缓存
        await asyncio.to_thread(self._delete_existing, key)
        try:
            # 将原始数据转为base64编码
            if isinstance(payload, bytes):
                payload_str = base64.b64encode(payload).decode('utf-8')
            else:
                payload_str = str(payload)
            
            await asyncio.to_thread(
                self._collection.insert,
                [
                    [key],
                    [normalized],
                    [payload_str],
                    [float(expires_at)],
                    [scope_value],
                ],
            )
            return True
        except Exception as exc: 
            logger.warning("Failed to insert cache entry into Milvus: %s", exc)
            return False

    async def search(
        self,
        embedding: List[float],
        threshold: float,
        scope: str | None = None,
    ) -> Optional[Tuple[Any, float]]:
        if not self._collection:
            return None
        vector = np.asarray(embedding, dtype="float32")
        if vector.ndim != 1 or vector.shape[0] != self._dimension:
            logger.warning("Search embedding dimension mismatch. Expected %d", self._dimension)
            return None
        norm = np.linalg.norm(vector)
        if norm == 0.0:
            logger.debug("Skipping L2 cache lookup for zero vector query")
            return None
        normalized = (vector / norm).tolist()
        # 构建过滤表达式："((expires_at == 0) or (expires_at > current_time)) and (scope == 'global')"
        expr = self._build_valid_expr(scope)
        try:
            results = await asyncio.to_thread(
                self._collection.search,
                [normalized],
                "embedding",
                self._search_params,
                1,
                expr=expr,
                output_fields=["payload_data"],
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Milvus vector cache search failed: %s", exc)
            return None

        if not results or len(results[0]) == 0:  # type: ignore
            return None
        hit = results[0][0]  # type: ignore
        logger.info("Milvus cache hit with distance: %f", hit.distance)
        similarity = float(hit.distance)
        # 判断相似度是否超过阈值
        if similarity < threshold:
            return None
        
        payload_str = None
        if hasattr(hit, "entity") and hit.entity is not None:
            payload_str = hit.entity.get("payload_data")
        if payload_str is None:
            try:
                payload_str = hit.get("payload_data")  # type: ignore[attr-defined]
            except AttributeError:
                payload_str = None
        
        if payload_str is None:
            return None
        
        # 将base64编码的payload解码
        try:
            payload = base64.b64decode(payload_str.encode('utf-8'))
        except Exception:
            payload = payload_str
        
        return (payload, similarity)

    async def clear(self) -> bool:
        if not self._collection:
            return False
        try:
            await asyncio.to_thread(self._collection.delete, expr='cache_key >= ""')
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to clear Milvus vector cache: %s", exc)
            return False

    # --- Internal helpers -------------------------------------------------

    def  _connect(
        self,
        host: str,
        port: int,
        user: Optional[str],
        password: Optional[str],
        secure: bool,
    ) -> None:
        if connections.has_connection(self._alias):
            return
        auth_args: Dict[str, Any] = {"host": host, "port": port, "secure": secure}
        if user and password:
            auth_args["user"] = user
            auth_args["password"] = password
        try:
            connections.connect(alias=self._alias, **auth_args)
        except Exception as exc:  # pragma: no cover - defensive logging
            raise RuntimeError(f"Failed to connect to Milvus for cache: {exc}") from exc

    def _get_or_create_collection(self, force_build: bool) -> Collection:
        if utility.has_collection(self._collection_name, using=self._alias):
            _ = utility.drop_collection(self._collection_name, using=self._alias)

        if force_build or not utility.has_collection(self._collection_name, using=self._alias):
            schema = CollectionSchema(
                fields=[
                    FieldSchema(
                        name="cache_key",
                        dtype=DataType.VARCHAR,
                        max_length=128,
                        is_primary=True,
                        auto_id=False,
                    ),
                    FieldSchema(
                        name="embedding",
                        dtype=DataType.FLOAT_VECTOR,
                        dim=self._dimension,
                    ),
                    FieldSchema(
                        name="payload_data",
                        dtype=DataType.VARCHAR,
                        max_length=65535,
                    ),
                    FieldSchema(
                        name="expires_at",
                        dtype=DataType.DOUBLE,
                    ),
                    FieldSchema(
                        name="scope",
                        dtype=DataType.VARCHAR,
                        max_length=128,
                    ),
                ],
                description="CookAgent retrieval L2 cache",
            )
            collection = Collection(
                name=self._collection_name,
                schema=schema,
                using=self._alias,
            )
            logger.info("Created Milvus collection '%s' for response cache", self._collection_name)
        else:
            collection = Collection(name=self._collection_name, using=self._alias)
        return collection

    def _ensure_index(self) -> None:
        if not self._collection.has_index():
            self._collection.create_index(field_name="embedding", index_params=self._index_params) # type: ignore
            logger.info("Created Milvus index for cache collection '%s'", self._collection_name)
            logger.info("Created Milvus index for cache collection '%s'", self._collection_name)

    def _delete_existing(self, cache_key: str) -> None:
        try:
            self._collection.delete(expr=f'cache_key == "{cache_key}"')
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Failed to delete existing Milvus cache key %s: %s", cache_key, exc)

    def _build_valid_expr(self, scope: str | None = None) -> str:
        now = time.time()
        ttl_expr = f"((expires_at == 0) or (expires_at > {float(now)}))"
        scope_value = scope or "global"
        scope_expr = f'(scope == "{scope_value}")'
        return f"{ttl_expr} and {scope_expr}"

