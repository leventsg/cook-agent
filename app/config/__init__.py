"""
cookagent 配置模块。

提供对所有配置项的统一访问入口。

使用示例：
    from app.config import settings, DefaultRAGConfig, LLMType

    # 访问全局配置
    print(settings.PROJECT_NAME)

    # 访问全局 LLM 配置（分层模式：fast / normal）
    print(settings.llm.fast.model_names)
    print(settings.llm.normal.model_names)

    # 访问数据库配置
    print(settings.database.postgres.host)
    print(settings.database.redis.host)
    print(settings.database.milvus.host)

    # 访问 RAG 配置
    print(settings.rag.vector_store.collection_names)

    # 或使用兼容旧版本的别名
    print(DefaultRAGConfig.vector_store.collection_names)

    # 访问 MCP 配置
    print(settings.mcp.amap_api_key)

    # 访问图像生成配置
    print(settings.image_generation.model)
"""
from app.config.config import settings, Settings, DefaultRAGConfig
from app.config.database_config import (
    DatabaseConfig,
    PostgresConfig,
    RedisConfig,
    MilvusConfig,
)
from app.config.llm_config import LLMConfig, LLMType, LLMProfileConfig, VisionLLMConfig
from app.config.rag_config import (
    RAGConfig,
    PathsConfig,
    VectorStoreConfig,
    EmbeddingConfig,
    RetrievalConfig,
    RerankerConfig,
    CacheConfig,
    DataSourceConfig,
    HowToCookConfig,
)
from app.config.web_search_config import WebSearchConfig
from app.config.vision_config import VisionConfig, ImageGenerationConfig, ImageStorageConfig
from app.config.mcp_config import MCPConfig, MCPServerConfig

__all__ = [
    # Main settings
    "settings",
    "Settings",
    "DefaultRAGConfig",
    # Database configuration classes
    "DatabaseConfig",
    "PostgresConfig",
    "RedisConfig",
    "MilvusConfig",
    # LLM configuration
    "LLMConfig",
    "LLMType",
    "LLMProfileConfig",
    "VisionLLMConfig",
    # RAG configuration classes
    "RAGConfig",
    "PathsConfig",
    "VectorStoreConfig",
    "EmbeddingConfig",
    "RetrievalConfig",
    "RerankerConfig",
    "CacheConfig",
    "DataSourceConfig",
    "HowToCookConfig",
    # Web Search configuration
    "WebSearchConfig",
    # Vision configuration
    "VisionConfig",
    # MCP configuration
    "MCPConfig",
    "MCPServerConfig",
    "ImageGenerationConfig",
    "ImageStorageConfig",
]