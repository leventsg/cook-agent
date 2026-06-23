"""
个人知识文档服务层

负责管理用户拥有的知识文档，包括文档的创建、查询、更新和删除等操作。
"""
import logging
from typing import Dict, List, Optional

from app.database.document_repository import document_repository
from app.database.models import KnowledgeDocumentModel
from app.services.rag_service import rag_service_instance

logger = logging.getLogger(__name__)


class PersonalDocumentService:
    """
    管理用户私有知识文档
    所有数据库操作均通过 DocumentRepository 执行
    """
    
    ALLOWED_SOURCES = {"recipes", "tips", "personal"}

    async def create_document(
        self,
        *,
        user_id: str,
        dish_name: str,
        category: str,
        difficulty: str,
        data_source: str,
        content: str,
    ) -> KnowledgeDocumentModel:
        """创建一个新的知识文档"""
        if data_source not in self.ALLOWED_SOURCES:
            raise ValueError(f"data_source must be one of: {', '.join(self.ALLOWED_SOURCES)}")

        doc = await document_repository.create(
            user_id=user_id,
            dish_name=dish_name,
            category=category,
            difficulty=difficulty,
            data_source="personal",  # Always personal for user-created docs
            source_type=data_source,  # The type selected by user
            source=f"personal::{user_id}",
            is_dish_index=False,
            content=content,
        )

        # 将文档添加到向量存储中
        await rag_service_instance.add_personal_document(
            user_id=user_id,
            document_id=str(doc.id),
            dish_name=doc.dish_name,
            category=doc.category,
            difficulty=doc.difficulty,
            data_source=data_source,
            content=doc.content,
        )

        logger.info("Personal document created id=%s user=%s", doc.id, user_id)
        return doc

    async def get_document(self, user_id: str, document_id: str) -> Optional[dict]:
        """根据用户ID获取单个文档"""
        doc = await document_repository.get_by_id_for_user(document_id, user_id)
        return doc.to_dict() if doc else None

    async def update_document(
        self,
        *,
        user_id: str,
        document_id: str,
        dish_name: str,
        category: str,
        difficulty: str,
        data_source: str,
        content: str,
    ) -> Optional[KnowledgeDocumentModel]:
        """更新个人知识文档，先删除，然后创建"""
        if data_source not in self.ALLOWED_SOURCES:
            raise ValueError(f"data_source must be one of: {', '.join(self.ALLOWED_SOURCES)}")

        await self.delete_document(user_id, document_id)

        doc = await document_repository.create(
            doc_id=document_id,
            user_id=user_id,
            dish_name=dish_name,
            category=category,
            difficulty=difficulty,
            data_source="personal",  
            source_type=data_source, 
            source=f"personal::{user_id}",
            is_dish_index=False,
            content=content,
        )
        
        if not doc:
            return None

        # 更新向量存储中的文档
        await rag_service_instance.update_personal_document(
            user_id=user_id,
            document_id=document_id,
            dish_name=doc.dish_name,
            category=doc.category,
            difficulty=doc.difficulty,
            data_source=data_source,
            content=doc.content,
        )

        logger.info("Personal document updated id=%s user=%s", doc.id, user_id)
        return doc

    async def delete_document(self, user_id: str, document_id: str) -> bool:
        """根据用户ID删除单个文档"""
        deleted = await document_repository.delete(document_id, user_id)

        if deleted:
            # 从向量存储中删除文档
            await rag_service_instance.delete_personal_document(
                user_id=user_id,
                document_id=document_id,
            )
            logger.info("Personal document deleted id=%s user=%s", document_id, user_id)

        return deleted

    async def list_documents(self, user_id: str, limit: int = 50, offset: int = 0) -> List[dict]:
        """列出用户的知识文档"""
        docs = await document_repository.list_by_user(user_id, limit=limit, offset=offset)
        return [doc.to_dict() for doc in docs]

    def get_available_options(self, user_id: str) -> Dict[str, List[str]]:
        """获取可用的元数据选项（合并全局和用户的），读缓存"""
        return document_repository.get_metadata_options(user_id)


personal_document_service = PersonalDocumentService()
