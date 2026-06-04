"""
知识文档 CRUD 模块。
为存储在 PostgreSQL 中的知识文档提供异步数据库访问能力。
"""

import logging
import uuid
from typing import Dict, List, Optional

from sqlalchemy import delete, select, func
from langchain_core.documents import Document

from app.database.models import KnowledgeDocumentModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)

class DocumentRepository:
    """
    用于管理 PostgreSQL 中知识文档的 CRUD 操作。
    提供以下功能：
    - 根据文档 ID 获取父文档（用于 post_process_retrieval 后处理阶段）
    - 文档的增删改查（CRUD）操作
    - 数据导入场景下的批量操作
    - 基于缓存的元数据选项查询，以提升检索效率
    """

    # 类级缓存，用于存储元数据选项（应用启动时加载一次）
    _global_cache: Dict[str, List[str]] = {}  # Global recipes metadata
    _user_cache: Dict[str, Dict[str, List[str]]] = {}  # user_id -> personal metadata
    _cache_initialized: bool = False

    @classmethod
    async def init_all_metadata_cache(cls) -> None:
        """
        从数据库初始化所有元数据缓存。应在应用启动时调用一次。
        加载内容包括：
        - 全局菜谱文档的元数据
        - 所有用户个人文档的元数据
        """
        if cls._cache_initialized:
            return
        
        async with get_session_context() as session:
            # 1. Load global metadata (user_id is NULL)
            global_stmt = select(
                func.array_agg(func.distinct(KnowledgeDocumentModel.dish_name)),
                func.array_agg(func.distinct(KnowledgeDocumentModel.category)),
                func.array_agg(func.distinct(KnowledgeDocumentModel.difficulty)),
            ).where(KnowledgeDocumentModel.user_id.is_(None))
            global_row = (await session.execute(global_stmt)).one()
            cls._global_cache = {
                "dish_name": sorted([v for v in (global_row[0] or []) if v]),
                "category": sorted([v for v in (global_row[1] or []) if v]),
                "difficulty": sorted([v for v in (global_row[2] or []) if v]),
            }
            
            # 2. Load all user metadata (grouped by user_id)
            cls._user_cache = {}
            user_stmt = (
                select(
                    KnowledgeDocumentModel.user_id,
                    func.array_agg(func.distinct(KnowledgeDocumentModel.dish_name)),
                    func.array_agg(func.distinct(KnowledgeDocumentModel.category)),
                    func.array_agg(func.distinct(KnowledgeDocumentModel.difficulty)),
                )
                .where(KnowledgeDocumentModel.user_id.is_not(None))
                .group_by(KnowledgeDocumentModel.user_id)
            )
            rows = (await session.execute(user_stmt)).all()
            for user_uuid, dish_names, categories, difficulties in rows:
                cls._user_cache[str(user_uuid)] = {
                    "dish_name": sorted([v for v in (dish_names or []) if v]),
                    "category": sorted([v for v in (categories or []) if v]),
                    "difficulty": sorted([v for v in (difficulties or []) if v]),
                }
        
        cls._cache_initialized = True
        logger.info(
            "文档元数据缓存初始化: global(%d 菜谱, %d 分类, %d 难度), %d 用户",
            len(cls._global_cache.get("dish_name", [])),
            len(cls._global_cache.get("category", [])),
            len(cls._global_cache.get("difficulty", [])),
            len(cls._user_cache),
        )

    @classmethod
    def _update_cache_on_create(
        cls,
        dish_name: str,
        category: str,
        difficulty: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        在文档创建时增量更新元数据缓存。
        """
        if user_id:
            # Update user-specific cache
            if user_id not in cls._user_cache:
                cls._user_cache[user_id] = {
                    "dish_name": [],
                    "category": [],
                    "difficulty": [],
                }
            user_cache = cls._user_cache[user_id]
            if dish_name and dish_name not in user_cache["dish_name"]:
                user_cache["dish_name"] = sorted(user_cache["dish_name"] + [dish_name])
            if category and category not in user_cache["category"]:
                user_cache["category"] = sorted(user_cache["category"] + [category])
            if difficulty and difficulty not in user_cache["difficulty"]:
                user_cache["difficulty"] = sorted(user_cache["difficulty"] + [difficulty])
        else:
            raise NotImplementedError(
                "全局文档由管理员批量导入，而非用户实时创建"
            )

    @classmethod
    async def _update_cache_on_delete(
        cls,
        user_id: Optional[str] = None,
    ) -> None:
        """
        在文档删除时通过重新加载来更新元数据缓存。
        """
        if user_id:
            async with get_session_context() as session:
                user_uuid = uuid.UUID(user_id)
                stmt = select(
                    func.array_agg(func.distinct(KnowledgeDocumentModel.dish_name)),
                    func.array_agg(func.distinct(KnowledgeDocumentModel.category)),
                    func.array_agg(func.distinct(KnowledgeDocumentModel.difficulty)),
                ).where(KnowledgeDocumentModel.user_id == user_uuid)
                row = (await session.execute(stmt)).one()
                cls._user_cache[user_id] = {
                    "dish_name": sorted([v for v in (row[0] or []) if v]),
                    "category": sorted([v for v in (row[1] or []) if v]),
                    "difficulty": sorted([v for v in (row[2] or []) if v]),
                }
        else:
            raise NotImplementedError(
                "全局文档由管理员批量删除，而非用户实时删除"
            )
        
    @classmethod
    def get_metadata_options(cls, user_id: Optional[str] = None) -> Dict[str, List[str]]:
        """
        获取合并后的元数据选项（不访问数据库）
        如果提供了 user_id，则将全局缓存与用户专属缓存进行合并后返回
        """
        if not user_id:
            return cls._global_cache.copy()
        
        # 合并全局和用户元数据缓存
        user_meta = cls._user_cache.get(user_id, {})
        merged = {}
        for key in ("dish_name", "category", "difficulty"):
            global_values = set(cls._global_cache.get(key, []))
            user_values = set(user_meta.get(key, []))
            merged[key] = sorted(global_values | user_values)
        
        return merged
    
    @classmethod
    def get_metadata_for_filter(cls, user_id: Optional[str] = None) -> Dict[str, Dict[str, List[str]]]:
        """
        获取用于过滤条件提取的元数据（不访问数据库）
        返回结果按数据来源分组：
        - Global Recipes（全局菜谱）
        - Personal Documents（个人文档）
        """
        result: Dict[str, Dict[str, List[str]]] = {}
        
        if cls._global_cache:
            result["Global Recipes"] = cls._global_cache.copy()
        
        if user_id:
            user_meta = cls._user_cache.get(user_id, {})
            if user_meta and any(user_meta.values()):
                result["Personal Documents"] = user_meta.copy()
        
        return result
    
    @staticmethod
    async def get_by_id(doc_id: str) -> Optional[KnowledgeDocumentModel]:
        """根据ID获取单个文档"""
        try:
            doc_uuid = uuid.UUID(doc_id)
        except (TypeError, ValueError):
            return None

        async with get_session_context() as session:
            stmt = select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id == doc_uuid
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        
    @staticmethod
    async def get_by_id_for_user(doc_id: str, user_id: str) -> Optional[KnowledgeDocumentModel]:
        """根据ID和用户ID获取单个文档"""
        try:
            doc_uuid = uuid.UUID(doc_id)
            user_uuid = uuid.UUID(user_id)
        except (TypeError, ValueError):
            return None

        async with get_session_context() as session:
            stmt = select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id == doc_uuid,
                KnowledgeDocumentModel.user_id == user_uuid,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        
    @staticmethod
    async def get_by_ids(doc_ids: List[str]) -> Dict[str, KnowledgeDocumentModel]:
        """
        根据ID列表获取多个文档
        """
        if not doc_ids:
            return {}

        try:
            doc_uuids = [uuid.UUID(doc_id) for doc_id in doc_ids]
        except (TypeError, ValueError):
            logger.warning("无效的文档ID格式,无法转换为UUID: %s", doc_ids)
            return {}

        async with get_session_context() as session:
            stmt = select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id.in_(doc_uuids)
            )
            result = await session.execute(stmt)
            docs = result.scalars().all()
            return {str(doc.id): doc for doc in docs}
        
    @staticmethod
    async def get_parent_documents(parent_ids: List[str]) -> Dict[str, Document]:
        """
        根据ID获取父文档并转换为LangChain文档。
        由post_process_retrieval使用以恢复完整的文档内容。
        """
        if not parent_ids:
            return {}

        doc_models = await DocumentRepository.get_by_ids(parent_ids)
        
        result = {}
        for doc_id, model in doc_models.items():
            result[doc_id] = Document(
                id=doc_id,
                page_content=model.content,
                metadata=model.to_metadata(),
            )
        return result

    @staticmethod
    async def create(
        *,
        doc_id: Optional[str] = None,
        user_id: Optional[str] = None,
        dish_name: str,
        category: str,
        difficulty: str,
        data_source: str,
        source_type: str,
        source: str,
        is_dish_index: bool = False,
        content: str,
    ) -> KnowledgeDocumentModel:
        """创建新文档"""
        async with get_session_context() as session:
            doc = KnowledgeDocumentModel(
                id=uuid.UUID(doc_id) if doc_id else uuid.uuid4(),
                user_id=uuid.UUID(user_id) if user_id else None,
                dish_name=dish_name.strip(),
                category=category.strip(),
                difficulty=difficulty.strip(),
                data_source=data_source,
                source_type=source_type,
                source=source,
                is_dish_index=is_dish_index,
                content=content,
            )
            session.add(doc)
            await session.flush()
            logger.info("创建文档: id=%s dish_name=%s", doc.id, dish_name)
            
            # Update metadata cache
            DocumentRepository._update_cache_on_create(
                dish_name=dish_name.strip(),
                category=category.strip(),
                difficulty=difficulty.strip(),
                user_id=user_id,
            )
            
            return doc
        
    @staticmethod
    async def create_batch(documents: List[Dict]) -> List[KnowledgeDocumentModel]:
        """
        批量创建多个文档。
        每个字典应包含: doc_id, user_id (可选), dish_name, category, 
        difficulty, data_source, source_type, source, is_dish_index, content
        """
        if not documents:
            return []

        async with get_session_context() as session:
            models = []
            for doc_data in documents:
                doc = KnowledgeDocumentModel(
                    id=uuid.UUID(doc_data["doc_id"]) if doc_data.get("doc_id") else uuid.uuid4(),
                    user_id=uuid.UUID(doc_data["user_id"]) if doc_data.get("user_id") else None,
                    dish_name=doc_data["dish_name"].strip(),
                    category=doc_data["category"].strip(),
                    difficulty=doc_data["difficulty"].strip(),
                    data_source=doc_data["data_source"],
                    source_type=doc_data["source_type"],
                    source=doc_data["source"],
                    is_dish_index=doc_data.get("is_dish_index", False),
                    content=doc_data["content"],
                )
                session.add(doc)
                models.append(doc)
            
            await session.flush()
            logger.info("Batch created %d documents", len(models))
            return models

    @staticmethod
    async def update(
        doc_id: str,
        user_id: Optional[str] = None,
        **updates
    ) -> Optional[KnowledgeDocumentModel]:
        """更新文档的指定字段"""
        try:
            doc_uuid = uuid.UUID(doc_id)
            user_uuid = uuid.UUID(user_id) if user_id else None
        except (TypeError, ValueError):
            return None

        async with get_session_context() as session:
            # 构建查询语句
            stmt = select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id == doc_uuid
            )
            if user_uuid:
                stmt = stmt.where(KnowledgeDocumentModel.user_id == user_uuid)
            
            result = await session.execute(stmt)
            doc = result.scalar_one_or_none()
            
            if not doc:
                return None
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(doc, key) and value is not None:
                    if isinstance(value, str):
                        value = value.strip()
                    setattr(doc, key, value)
            
            await session.flush()
            logger.info("更新文档: id=%s", doc_id)
            return doc
        
    @staticmethod
    async def delete(doc_id: str, user_id: Optional[str] = None) -> bool:
        """删除指定ID的文档。对于个人文档，还需要提供user_id."""
        try:
            doc_uuid = uuid.UUID(doc_id)
            user_uuid = uuid.UUID(user_id) if user_id else None
        except (TypeError, ValueError):
            return False

        async with get_session_context() as session:
            stmt = delete(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.id == doc_uuid
            )
            if user_uuid:
                stmt = stmt.where(KnowledgeDocumentModel.user_id == user_uuid)
            
            result = await session.execute(stmt)
            deleted = result.rowcount > 0  
            
        if deleted:
            logger.info("Deleted document id=%s", doc_id)
            # 更新元数据缓存
            if user_id:
                await DocumentRepository._update_cache_on_delete(
                    user_id=user_id,
                )
            
        return deleted
    
    @staticmethod
    async def delete_by_data_source(data_source: str) -> int:
        """根据data_source删除所有文档。用于重新摄取数据时使用。"""
        async with get_session_context() as session:
            stmt = delete(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.data_source == data_source
            )
            result = await session.execute(stmt)
            count = result.rowcount 
            logger.info("根据data_source删除了 %d 个文档，data_source=%s", count, data_source)
            return count

    @staticmethod
    async def list_by_user(
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[KnowledgeDocumentModel]:
        """根据user_id查询个人文档。"""
        if limit < 0:
            raise ValueError("limit 必须为非负数")
        if offset < 0:
            raise ValueError("offset 必须为非负数")

        try:
            user_uuid = uuid.UUID(user_id)
        except (TypeError, ValueError):
            return []

        async with get_session_context() as session:
            stmt = (
                select(KnowledgeDocumentModel)
                .where(KnowledgeDocumentModel.user_id == user_uuid)
                .order_by(KnowledgeDocumentModel.updated_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        
    @staticmethod
    async def count_by_data_source(data_source: str) -> int:
        """根据data_source查询文档数量"""
        async with get_session_context() as session:
            stmt = select(func.count()).where(
                KnowledgeDocumentModel.data_source == data_source
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
        

# 创建全局单例实例
document_repository = DocumentRepository()