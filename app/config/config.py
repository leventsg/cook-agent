'''
CookAgent 的统一配置模块。
为整个应用程序的所有配置提供统一入口。

设计说明：
Settings：顶层配置类，包含全局配置以及各功能模块配置
所有配置均从 config.yml 与 .env 中加载
环境变量通过 config_loader 中的 load_dotenv 进行加载与管理
'''
import os
from pydantic import BaseModel
from app.config.config_loader import (
    load_llm_config, 
    load_database_config,
    load_rag_config,
    load_web_search_config,
    load_vision_config,
)
from app.config.llm_config import LLMConfig
from app.config.database_config import DatabaseConfig
from app.config.rag_config import RAGConfig
from app.config.web_search_config import WebSearchConfig
from app.config.vision_config import VisionConfig


class Settings(BaseModel):
    '''
    应用程序顶层配置
    包含：
        全局配置（如 API 前缀、项目名称等）
        全局 LLM 提供商配置
        数据库相关配置（PostgreSQL、Redis、Milvus）
        各功能模块的专属配置（如 RAG、Web Search 等）
    '''
    # ==========================================================================
    # 全局配置
    # ==========================================================================
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "CookAgent"
    DEBUG: bool = False
    
    # ==========================================================================
    # 认证/安全配置
    # 注意：环境变量已通过 config_loader 中的 load_dotenv 完成加载
    # 安全要求：在生产环境中，JWT_SECRET_KEY 必须通过环境变量进行配置
    # ==========================================================================
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    # Access token expiration (默认 60 分钟)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    # Refresh token expiration (默认 7 天)
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    
    # ==========================================================================
    # 限流配置
    # ==========================================================================
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "false").lower() == "true"
    RATE_LIMIT_LOGIN_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "5"))
    RATE_LIMIT_CONVERSATION_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_CONVERSATION_PER_MINUTE", "30"))
    RATE_LIMIT_GLOBAL_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_GLOBAL_PER_MINUTE", "100"))
    
    # ==========================================================================
    # 安全配置
    # ==========================================================================
    # 登录安全设置，失败登录尝试次数和锁定时间
    LOGIN_MAX_FAILED_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    # 输入长度限制
    MAX_MESSAGE_LENGTH: int = int(os.getenv("MAX_MESSAGE_LENGTH", "10000"))
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "5"))
    # Prompt注入安全开关
    PROMPT_GUARD_ENABLED: bool = os.getenv("PROMPT_GUARD_ENABLED", "true").lower() == "true"
    
    # ==========================================================================
    # 模块配置
    # ==========================================================================
    # 全局 LLM 配置（分层结构：fast / normal）
    llm: LLMConfig = load_llm_config()
    
    # 数据库配置 (PostgreSQL, Redis, Milvus)
    database: DatabaseConfig = load_database_config()

    # RAG 配置
    rag: RAGConfig = load_rag_config(llm.normal)

    # web search 配置
    web_search: WebSearchConfig = load_web_search_config()

    # vision 配置
    vision: VisionConfig = load_vision_config()

    