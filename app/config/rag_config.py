"""
RAG（检索增强生成）配置模型。
这些模型用于定义 config.yml 文件的结构。

设计原则：
1. 数据库连接配置在 DatabaseConfig 中定义，并以参数形式传入
2. RAG 专属配置仅定义其自身独有的字段
3. LLM 配置使用全局 LLMConfig（分层模式：fast / normal）
"""
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict

class PathsConfig(BaseModel):
    """
    菜谱数据路径配置模型
    """
    base_data_path: str = "data/HowToCook"

class EmbeddingConfig(BaseModel):
    """
    Embedding 模型配置
    """
    model_name: str = "BAAI/bge-small-zh-v1.5"

class VectorStoreConfig(BaseModel):
    """
    向量存储配置模型
    """
    type: Literal["milvus"] = "milvus"
    collection_names: Dict[str, str] = {
        "recipes": "cook_agent_recipes",
        "personal": "cook_agent_personal_docs",
    }

class RetrievalConfig(BaseModel):
    """
    检索配置模型
    """
    top_k: int = 9
    score_threshold: float = 0.2
    ranker_type: Literal["rrf", "weighted"] = "weighted"
    ranker_weights: List[float] = [0.8, 0.2]  # [dense, sparse]

class RerankerConfig(BaseModel):
    """
    Reranker 配置
    """
    enabled: bool = True
    type: Literal["siliconflow"] = "siliconflow"
    model_name: str = "Qwen/Qwen3-Reranker-8B"
    base_url: Optional[str] = "https://api.siliconflow.cn/v1/rerank"
    api_key: Optional[str] = None  # Falls back to global LLM API key
    temperature: float = 0.0
    max_tokens: int = 8192
    score_threshold: float = 0.1

class CacheConfig(BaseModel):
    """
    RAG 检索结果缓存配置。

    缓存策略：
    - L1：精确匹配（Redis）—— 用于相同查询的高速缓存查找
    - L2：语义匹配（Milvus）—— 用于处理相似查询

    注意：
    - 连接配置位于 DatabaseConfig（redis/milvus）中
    - 仅缓存 Query -> Retrieved Documents（查询到检索文档）的结果，
    不缓存 LLM 响应内容。
    """
    enabled: bool = True
    # L1 和 L2 缓存的 TTL（单位：秒）
    ttl: int = 3600  # 1 hour
    # L2 语义缓存配置
    l2_enabled: bool = True
    similarity_threshold: float = 0.92
    vector_collection: str = "cookagent_retrieval_cache"

class HowToCookConfig(BaseModel):
    """
    HowToCook 数据源配置模型（包含提示）
    """
    path_suffix: str = "dishes"
    tips_path_suffix: str = "tips"  
    headers_to_split_on: List[List[str]] = [["#", "header_1"], ["##", "header_2"]]

class DataSourceConfig(BaseModel):
    """
    数据源配置模型
    """
    howtocook: HowToCookConfig = HowToCookConfig()

class RAGConfig(BaseModel):
    """
    主 RAG 配置模型。

    注意：
    - 数据库连接配置位于 DatabaseConfig 中，并以独立方式传入
    - LLM 配置使用全局 LLMConfig（分层模式：fast / normal）
    """
    # 模块配置
    paths: PathsConfig = PathsConfig()
    embedding: EmbeddingConfig = EmbeddingConfig()
    vector_store: VectorStoreConfig = VectorStoreConfig()
    retrieval: RetrievalConfig = RetrievalConfig()
    reranker: RerankerConfig = RerankerConfig()
    cache: CacheConfig = CacheConfig()
    data_source: DataSourceConfig = DataSourceConfig()