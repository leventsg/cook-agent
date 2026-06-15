"""
HowToCook 数据加载器，用于数据导入流程
负责解析本地 Markdown 文件，并将其转换为可存储到数据库中的文档数据
该模块仅在数据导入阶段使用，不参与运行时请求处理
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

logger = logging.getLogger(__name__)

# 用于生成确定性文档 ID 的命名空间
DOC_NAMESPACE = uuid.UUID('7a7de5f8-7435-4354-9b1b-d50a09848520')

@dataclass
class ParsedDocument:
    """
    解析后的文档数据结构
    """
    doc_id: str
    dish_name: str
    category: str
    difficulty: str
    data_source: str  # "recipes"
    source_type: str  # "recipes" or "tips"
    source: str  # file path
    is_dish_index: bool
    content: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "data_source": self.data_source,
            "source_type": self.source_type,
            "source": self.source,
            "is_dish_index": self.is_dish_index,
            "content": self.content,
            "user_id": None,  # Global/public documents
        }

    def to_metadata(self) -> Dict[str, Any]:
        """转换为用于向量存储 Chunk 的元数据字典"""
        return {
            "source": self.source,
            "parent_id": None,  # Will be set when creating chunks
            "dish_name": self.dish_name,
            "category": self.category,
            "difficulty": self.difficulty,
            "is_dish_index": self.is_dish_index,
            "data_source": self.data_source,
            "user_id": "GLOBAL",
            "source_type": self.source_type,
        }
    
class HowToCookDataLoader:
    """
    HowToCook 数据加载器，负责从本地 Markdown 文件解析文档数据
    """

    CATEGORY_MAPPING = {
        'meat_dish': '荤菜',
        'vegetable_dish': '素菜',
        'soup': '汤品',
        'dessert': '甜品',
        'breakfast': '早餐',
        'staple': '主食',
        'aquatic': '水产',
        'condiment': '调料',
        'drink': '饮品',
        'semi-finished': '半成品',
    }

    def __init__(
        self,
        data_path: str,
        tips_path: str | None = None,
        headers_to_split_on: List[tuple] | None = None,
    ):
        self.data_path = Path(data_path)
        self.tips_path = Path(tips_path) if tips_path else None
        self.headers_to_split_on = headers_to_split_on or [
            ("#", "header_1"),
            ("##", "header_2"),
        ]
        self._splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=self.headers_to_split_on,
            strip_headers=False, # 保留标题
        )

    def load_documents(self) -> List[ParsedDocument]:
        """
        加载 HowToCook 仓库中的所有文档
        返回可直接用于数据库入库的 ParsedDocument 对象
        """
        documents: List[ParsedDocument] = []
        dishes_by_category: Dict[str, List[str]] = {}
        dishes_by_difficulty: Dict[str, List[str]] = {}

        # 加载菜谱文档
        logger.info("Loading recipes from %s", self.data_path)
        for md_file in self.data_path.rglob("*.md"):
            try:
                doc = self._parse_recipe_file(md_file, source_type="recipes")
                if doc:
                    documents.append(doc)
                    dishes_by_category.setdefault(doc.category, []).append(doc.dish_name)
                    dishes_by_difficulty.setdefault(doc.difficulty, []).append(doc.dish_name)
            except Exception as e:
                logger.warning("Failed to read file %s: %s", md_file, e)

        # 加载烹饪技巧文档
        if self.tips_path and self.tips_path.exists():
            logger.info("Loading tips from %s", self.tips_path)
            for md_file in self.tips_path.rglob("*.md"):
                try:
                    doc = self._parse_tips_file(md_file)
                    if doc:
                        documents.append(doc)
                        dishes_by_category.setdefault(doc.category, []).append(doc.dish_name)
                        dishes_by_difficulty.setdefault(doc.difficulty, []).append(doc.dish_name)
                except Exception as e:
                    logger.warning("Failed to read tip file %s: %s", md_file, e)

        # 创建索引文档
        index_docs = self._create_index_documents(dishes_by_category, dishes_by_difficulty)
        documents.extend(index_docs)

        logger.info(
            "Loaded %d documents (%d recipes + tips, %d index docs)",
            len(documents),
            len(documents) - len(index_docs),
            len(index_docs),
        )
        return documents
    
    def create_chunks(self, documents: List[ParsedDocument]) -> List[Document]:
        """
        根据解析后的文档创建向量存储 Chunk
        返回可直接用于向量索引构建的 LangChain Document 对象
        """
        all_chunks: List[Document] = []

        for doc in documents:
            metadata = doc.to_metadata()
            
            if doc.is_dish_index:
                # 为索引文档创建一个整体 Chunk，不进行进一步切分
                chunk_content = self._create_index_chunk_content(metadata)
                chunk_metadata = metadata.copy()
                chunk_metadata["parent_id"] = doc.doc_id
                all_chunks.append(Document(
                    id=str(uuid.uuid4()),
                    page_content=chunk_content,
                    metadata=chunk_metadata,
                ))
            else:
                # 创建多个 Chunk
                md_chunks = self._splitter.split_text(doc.content)
                for chunk_doc in md_chunks:
                    chunk_metadata = metadata.copy()
                    chunk_metadata["parent_id"] = doc.doc_id
                    all_chunks.append(Document(
                        id=str(uuid.uuid4()),
                        page_content=chunk_doc.page_content,
                        metadata=chunk_metadata,
                    ))

        logger.info("Created %d chunks from %d documents", len(all_chunks), len(documents))
        return all_chunks
    
    def _parse_recipe_file(self, file_path: Path, source_type: str) -> ParsedDocument | None:
        """解析菜谱 Markdown 文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.strip():
            return None

        doc_id = str(uuid.uuid5(DOC_NAMESPACE, str(file_path)))
        dish_name, category, difficulty = self._extract_recipe_metadata(file_path, content)

        return ParsedDocument(
            doc_id=doc_id,
            dish_name=dish_name,
            category=category,
            difficulty=difficulty,
            data_source="recipes",
            source_type=source_type,
            source=str(file_path),
            is_dish_index=False,
            content=content,
        )
    
    def _parse_tips_file(self, file_path: Path) -> ParsedDocument | None:
        """解析烹饪技巧 Markdown 文件"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if not content.strip():
            return None

        doc_id = str(uuid.uuid5(DOC_NAMESPACE, str(file_path)))

        return ParsedDocument(
            doc_id=doc_id,
            dish_name=file_path.stem,
            category="技巧",
            difficulty="简单",
            data_source="recipes",
            source_type="tips",
            source=str(file_path),
            is_dish_index=False,
            content=content,
        )
    
    def _extract_recipe_metadata(
        self, file_path: Path, content: str
    ) -> Tuple[str, str, str]:
        """从菜谱文件路径和内容中提取元数据"""
        category = '其他'
        for key, value in self.CATEGORY_MAPPING.items():
            if key in file_path.parts:
                category = value
                break

        dish_name = file_path.stem

        if '★★★★★' in content:
            difficulty = '非常困难'
        elif '★★★★' in content:
            difficulty = '困难'
        elif '★★★' in content:
            difficulty = '中等'
        elif '★★' in content:
            difficulty = '简单'
        elif '★' in content:
            difficulty = '非常简单'
        else:
            difficulty = '未知'

        return dish_name, category, difficulty
    
    def _create_index_documents(
        self,
        dishes_by_category: Dict[str, List[str]],
        dishes_by_difficulty: Dict[str, List[str]],
    ) -> List[ParsedDocument]:
        """创建索引文档"""
        index_docs: List[ParsedDocument] = []

        # 全局索引文档
        overall = self._create_overall_index(dishes_by_category, dishes_by_difficulty)
        if overall:
            index_docs.append(overall)

        # 分类索引文档
        for category, names in dishes_by_category.items():
            doc = self._create_category_index(category, sorted(set(names)))
            if doc:
                index_docs.append(doc)

        # 难度索引文档
        for difficulty, names in dishes_by_difficulty.items():
            doc = self._create_difficulty_index(difficulty, sorted(set(names)))
            if doc:
                index_docs.append(doc)

        logger.info("Created %d index documents", len(index_docs))
        return index_docs
    
    def _create_overall_index(
        self,
        dishes_by_category: Dict[str, List[str]],
        dishes_by_difficulty: Dict[str, List[str]],
    ) -> ParsedDocument | None:
        """创建全局菜谱索引文档."""
        if not dishes_by_category and not dishes_by_difficulty:
            return None

        content_parts = ["# 菜谱索引\n\n"]
        content_parts.append("本索引包含所有可用的菜谱名称，按多种元数据组织（类别、菜名、难度）。\n\n")

        # By category
        content_parts.append("## 按类别分类\n\n")
        for category in sorted(dishes_by_category.keys()):
            dishes = sorted(set(dishes_by_category[category]))
            content_parts.append(f"### {category}\n\n")
            content_parts.append("菜谱列表：")
            content_parts.append("、".join(dishes))
            content_parts.append("\n\n")

        # By difficulty
        content_parts.append("## 按难度分类\n\n")
        for diff in sorted(dishes_by_difficulty.keys()):
            dishes = sorted(set(dishes_by_difficulty[diff]))
            content_parts.append(f"### {diff}\n\n")
            content_parts.append("菜谱列表：")
            content_parts.append("、".join(dishes))
            content_parts.append("\n\n")

        # All dishes
        content_parts.append("## 所有菜谱\n\n")
        all_dishes = []
        for dishes in dishes_by_category.values():
            all_dishes.extend(dishes)
        unique_all = sorted(set(all_dishes))
        content_parts.append("推荐菜，菜谱列表，所有菜谱：")
        content_parts.append("、".join(unique_all))
        content_parts.append("\n")

        return ParsedDocument(
            doc_id=str(uuid.uuid5(DOC_NAMESPACE, "dish_index")),
            dish_name="菜谱索引",
            category="索引",
            difficulty="未知",
            data_source="recipes",
            source_type="recipes",
            source="dish_index::all",
            is_dish_index=True,
            content="".join(content_parts),
        )
    
    def _create_category_index(
        self, category: str, dish_list: List[str]
    ) -> ParsedDocument | None:
        """创建特定类别的索引文档."""
        if not dish_list:
            return None

        content = f"菜谱索引 - {category}\n\n" + "、".join(dish_list)

        return ParsedDocument(
            doc_id=str(uuid.uuid5(DOC_NAMESPACE, f"dish_index::category::{category}")),
            dish_name="菜谱索引",
            category=category,
            difficulty="未知",
            data_source="recipes",
            source_type="recipes",
            source=f"dish_index::category::{category}",
            is_dish_index=True,
            content=content,
        )
    
    def _create_difficulty_index(
        self, difficulty: str, dish_list: List[str]
    ) -> ParsedDocument | None:
        """创建特定难度的索引文档."""
        if not dish_list:
            return None

        content = f"菜谱索引 - {difficulty}\n\n" + "、".join(dish_list)

        return ParsedDocument(
            doc_id=str(uuid.uuid5(DOC_NAMESPACE, f"dish_index::difficulty::{difficulty}")),
            dish_name="菜谱索引",
            category="索引",
            difficulty=difficulty,
            data_source="recipes",
            source_type="recipes",
            source=f"dish_index::difficulty::{difficulty}",
            is_dish_index=True,
            content=content,
        )
    
    def _create_index_chunk_content(self, index_metadata: Dict[str, Any]) -> str:
        """创建索引文档的向量存储 Chunk 内容."""
        content_parts = ["推荐菜,菜谱列表,菜品,食谱,有哪些菜品推荐"]
        
        source = index_metadata.get("source", "")
        category = index_metadata.get("category", "")
        difficulty = index_metadata.get("difficulty", "")

        if "category" in source and category and category != "索引":
            content_parts.append(f"{category}推荐，")
        elif "difficulty" in source and difficulty and difficulty != "未知":
            content_parts.append(f"{difficulty}难度推荐，")

        content_parts.append("欢迎根据口味挑选合适的菜谱")
        return "".join(content_parts)