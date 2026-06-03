'''
CookAgent 配置加载模块。
负责从 config.yml 加载配置，并与环境变量中的敏感信息进行合并。

环境变量加载机制：

使用 load_dotenv() 将 .env 文件中的配置加载至 os.environ
所有敏感参数均通过 os.getenv() 读取
支持配置继承机制（例如：RERANKER_API_KEY 未配置时，将自动回退使用 LLM_API_KEY）
'''
import os
import yaml

from pathlib import Path
from dotenv import load_dotenv
from typing import Any, Dict

from app.config.llm_config import LLMConfig
from app.config.database_config import (
    DatabaseConfig, PostgresConfig, RedisConfig, MilvusConfig,
)
from app.config.rag_config import RAGConfig
from app.config.web_search_config import WebSearchConfig
from app.config.vision_config import VisionConfig, ImageStorageConfig, ImageGenerationConfig
from app.config.evaluation_config import EvaluationConfig, AlertThresholds
from app.config.mcp_config import MCPConfig, MCPServerConfig

load_dotenv()

def _load_config_data() -> Dict[str, Any]:
    """将原始 YAML 配置加载为字典对象"""
    config_path = Path("config.yml")
    if not config_path.exists():
        raise FileNotFoundError("config.yml not found in the project root.")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
    
def load_llm_config() -> LLMConfig:
    '''
    加载全局 LLM 提供商配置。
    环境变量说明：
    LLM_API_KEY：普通 LLM 的 API Key
    FAST_LLM_API_KEY / LLM_FAST_API_KEY：fast LLM 的 API Key
    VISION_API_KEY：视觉 LLM 的 API Key（未配置时将回退使用 LLM_API_KEY）
    '''
    config_data = _load_config_data()
    llm_root = config_data.get("llm", {}) or {}
    llm_data = dict(llm_root)
    
    #从环境中注入 API 密钥
    normal_api_key = os.getenv("LLM_API_KEY")
    fast_api_key = os.getenv("FAST_LLM_API_KEY")
    vision_api_key = os.getenv("VISION_API_KEY")
    
    normal_data = dict(llm_data.get("normal", {}) or {})
    fast_data = dict(llm_data.get("fast", {}) or {})
    vision_data = dict(llm_data.get("vision", {}) or {})
    
    if normal_api_key:
        normal_data["api_key"] = normal_api_key

    if fast_api_key:
        fast_data["api_key"] = fast_api_key

    if vision_api_key:
        vision_data["api_key"] = vision_api_key
        
    llm_data["normal"] = normal_data
    llm_data["fast"] = fast_data
    llm_data["vision"] = vision_data
    
    return LLMConfig.model_validate(llm_data)

def load_database_config() -> DatabaseConfig:
    '''
    加载 PostgreSQL、Redis 与 Milvus 的数据库配置。
    环境变量：
    - DATABASE_PASSWORD：PostgreSQL 数据库密码
    - REDIS_PASSWORD：Redis 密码
    - MILVUS_USER：Milvus 用户名
    - MILVUS_PASSWORD：Milvus 密码
    '''
    config_data = _load_config_data()
    db_root = config_data.get("database", {}) or {}

    # PostgreSQL 配置
    pg_data = dict(db_root.get("postgres", {}) or {})
    db_password = os.getenv("DATABASE_PASSWORD")
    if db_password:
        pg_data["password"] = db_password
    postgres_config = PostgresConfig.model_validate(pg_data)

    # Redis 配置
    redis_data = dict(db_root.get("redis", {}) or {})
    redis_password = os.getenv("REDIS_PASSWORD")
    if redis_password:
        redis_data["password"] = redis_password
    redis_config = RedisConfig.model_validate(redis_data)

    # Milvus 配置
    milvus_data = dict(db_root.get("milvus", {}) or {})
    milvus_user = os.getenv("MILVUS_USER")
    milvus_password = os.getenv("MILVUS_PASSWORD")
    if milvus_user:
        milvus_data["user"] = milvus_user
    if milvus_password:
        milvus_data["password"] = milvus_password
    milvus_config = MilvusConfig.model_validate(milvus_data)

    return DatabaseConfig(
        postgres=postgres_config,
        redis=redis_config,
        milvus=milvus_config,
    )

def load_rag_config(llm_config: Any | None = None) -> RAGConfig:
    '''
    加载 RAG 配置（从 YAML 配置文件与环境变量中读取并合并）
    环境变量：
    - RERANKER_API_KEY：专用于重排序模型（Reranker）的 API Key（若未设置，则回退使用 LLM_API_KEY）
    arg:
        llm_config：全局 LLM 配置（normal 配置层），用于 API Key 回退逻辑。
    '''
    config_data = _load_config_data()

    # 创建 RAG 配置对象（不包括数据库部分）
    rag_data: Dict[str, Any] = {}

    for key in ["paths", "embedding", "retrieval", "data_source"]:
        if key in config_data:
            rag_data[key] = config_data[key]
    
    # 向量存储配置（不包含 host/port， 这些在DatabaseConfig中）
    vs_data = config_data.get("vector_store", {}) or {}
    rag_data["vector_store"] = {
        "type": vs_data.get("type", "milvus"),
        "collection_names": vs_data.get("collection_names", {}),
    }

    # 重排序模型配置
    reranker_data = config_data.get("reranker", {}) or {}

    # API key 优先级： RERANKER_API_KEY > reranker.api_key in yaml > LLM_API_KEY
    reranker_api_key = os.getenv("RERANKER_API_KEY")
    if reranker_api_key:
        reranker_data["api_key"] = reranker_api_key
    else:
        # 如果环境变量中没有 RERANKER_API_KEY，则检查 YAML 配置中的 reranker.api_key
        if "api_key" not in reranker_data or not reranker_data["api_key"]:
            # 如果 YAML 中也没有配置，则回退使用全局 LLM API Key
            normal_api_key = getattr(
                getattr(llm_config, "normal", llm_config),
                "api_key",
                None,
            )
            if normal_api_key:
                reranker_data["api_key"] = normal_api_key

    
    rag_data["reranker"] = reranker_data

    # 缓存配置 
    cache_data = config_data.get("cache", {}) or {}
    rag_data["cache"] = {
        "enabled": cache_data.get("enabled", True),
        "ttl": cache_data.get("ttl", 3600),
        "l2_enabled": cache_data.get("l2_enabled", True),
        "similarity_threshold": cache_data.get("similarity_threshold", 0.92),
        "vector_collection": cache_data.get("vector_collection", "cookagent_retrieval_cache"),
    }
    
    return RAGConfig.model_validate(rag_data)

def load_web_search_config() -> WebSearchConfig:
    """
    从 YAML 配置文件与环境变量中加载 Web 搜索配置。

    环境变量：
    - WEB_SEARCH_API_KEY：Web 搜索的 API Key
    """
    config_data = _load_config_data()
    ws_data = dict(config_data.get("web_search", {}) or {})
    
    # Load API key from env
    api_key = os.getenv("WEB_SEARCH_API_KEY")
    if api_key:
        ws_data["api_key"] = api_key
    
    return WebSearchConfig.model_validate(ws_data)

def load_vision_config() -> VisionConfig:
    """
    从 YAML 配置文件中加载视觉配置（仅包含领域关键词）
    注意：视觉模型配置由 LLMConfig.vision 统一管理
    该函数仅加载领域相关配置，例如 food_related_keywords
    """
    config_data = _load_config_data()
    vision_data = dict(config_data.get("vision", {}) or {})

    # 仅保留领域相关配置，模型配置在 LLMConfig 中
    domain_data = {}
    if "food_related_keywords" in vision_data:
        domain_data["food_related_keywords"] = vision_data["food_related_keywords"]

    return VisionConfig.model_validate(domain_data)

def load_image_storage_config() -> ImageStorageConfig:
    """
    从 YAML 配置文件与环境变量中加载图像存储配置。

    环境变量：
    - IMGBB_STORAGE_API_KEY：用于图像存储的 imgbb API Key
    """
    config_data = _load_config_data()
    is_data = dict(config_data.get("image_storage", {}) or {})

    # Load API key from environment
    api_key = os.getenv("IMGBB_STORAGE_API_KEY")
    if api_key:
        is_data["api_key"] = api_key

    return ImageStorageConfig.model_validate(is_data)

def load_image_generation_config() -> ImageGenerationConfig:
    """
    从 YAML 配置文件与环境变量中加载图像生成配置。

    环境变量：
    - OPENAI_IMAGE_API_KEY：用于 DALL·E 图像生成的 OpenAI API Key
    """
    config_data = _load_config_data()
    ig_data = dict(config_data.get("image_generation", {}) or {})

    # Load API key from environment
    api_key = os.getenv("OPENAI_IMAGE_API_KEY")
    if api_key:
        ig_data["api_key"] = api_key

    return ImageGenerationConfig.model_validate(ig_data)

def load_evaluation_config() -> EvaluationConfig:
    """
    从 YAML 配置文件与环境变量中加载评测配置。
    无需额外的环境变量配置，评测功能直接复用现有的 LLM 配置。
    """
    config_data = _load_config_data()
    eval_data = dict(config_data.get("evaluation", {}) or {})

    thresholds_data = eval_data.pop("alert_thresholds", None)
    if thresholds_data:
        eval_data["alert_thresholds"] = AlertThresholds(**thresholds_data)

    # 使用默认值构建配置对象，以兼容缺失字段的情况
    return EvaluationConfig(
        enabled=eval_data.get("enabled", True),
        async_mode=eval_data.get("async_mode", True),
        sample_rate=eval_data.get("sample_rate", 1.0),
        metrics=eval_data.get("metrics", [
            "faithfulness",
            "answer_relevancy",
        ]),
        llm_type=eval_data.get("llm_type", "fast"),
        timeout_seconds=eval_data.get("timeout_seconds", 60),
        alert_thresholds=eval_data.get("alert_thresholds", AlertThresholds()),
    )

def load_mcp_config() -> MCPConfig:
    """
    从 YAML 配置文件与环境变量中加载 MCP 配置。
    环境变量：
        - AMAP_API_KEY：高德地图 API Key
    """
    config_data = _load_config_data()
    mcp_data = dict(config_data.get("mcp", {}) or {})

    amap_api_key = os.getenv("AMAP_API_KEY")
    if amap_api_key:
        mcp_data["amap_api_key"] = amap_api_key

    # 解析mcp服务配置
    amap_data = mcp_data.pop("amap", None)
    if amap_data:
        mcp_data["amap"] = MCPServerConfig(**amap_data)

    return MCPConfig.model_validate(mcp_data)
