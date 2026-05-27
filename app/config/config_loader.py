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
from app.config.database_config import DatabaseConfig, PostgresConfig, RedisConfig, MilvusConfig

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

    
    
