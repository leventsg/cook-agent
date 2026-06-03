'''
CookAgent 的数据库配置。
包含所有数据库连接相关配置：

PostgreSQL：用于会话数据与用户数据的持久化存储
Redis：作为缓存层（L1 精确匹配缓存）
Milvus：作为向量数据库，用于 Embedding 存储与语义缓存
'''
from typing import Optional
from pydantic import BaseModel

class PostgresConfig(BaseModel):
    '''
    PostgreSQL 数据库配置
    '''
    # 连接配置
    host: str = "localhost"
    port: int = 5432
    user: str = "cookagent"
    password: Optional[str] = None
    database: str = "cookagent"

    # 连接池配置
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 1800  # 30分钟后重建连接

    # 调试配置
    echo: bool = False

    @property
    def async_url(self) -> str:
        """生成异步 PostgreSQL 连接地址"""
        password_part = f":{self.password}" if self.password else ""
        return f"postgresql+asyncpg://{self.user}{password_part}@{self.host}:{self.port}/{self.database}"

    @property
    def sync_url(self) -> str:
        """生成同步 PostgreSQL 连接地址"""
        password_part = f":{self.password}" if self.password else ""
        return f"postgresql+psycopg2://{self.user}{password_part}@{self.host}:{self.port}/{self.database}"

class RedisConfig(BaseModel):
    """Redis 缓存配置"""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None


class MilvusConfig(BaseModel):
    """Milvus 向量数据库配置"""

    host: str = "localhost"
    port: int = 19530
    user: Optional[str] = None
    password: Optional[str] = None
    secure: bool = False

class DatabaseConfig(BaseModel):
    '''
    统一数据库配置容器
    包含应用程序所需的全部数据库连接配置
    '''
    postgres: PostgresConfig = PostgresConfig()
    redis: RedisConfig = RedisConfig()
    milvus: MilvusConfig = MilvusConfig()