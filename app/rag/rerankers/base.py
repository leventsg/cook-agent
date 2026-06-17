from abc import ABC, abstractmethod
from typing import List
from langchain_core.documents import Document

class BaseReranker(ABC):
    """
    Reranker 接口
    """
    
    @abstractmethod
    async def rerank(self, query: str, documents: List[Document]) -> List[Document]:
        """
        对文档列表进行重新排序或过滤，根据用户查询。

        Args:
            query: 用户查询文本
            documents: 待重新排序的文档列表

        Returns:
            重新排序后的文档列表
        """
        pass
