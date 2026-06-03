"""
CookAgent 异步数据库会话管理模块。

提供数据库会话工厂（Session Factory）以及 FastAPI 依赖注入支持。
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database.models import Base

logger = logging.getLogger(__name__)

# 创建全局异步数据库引擎
_engine = create_async_engine(
    settings.database.postgres.async_url,
    pool_size=settings.database.postgres.pool_size,
    max_overflow=settings.database.postgres.max_overflow,
    pool_timeout=settings.database.postgres.pool_timeout,
    pool_recycle=settings.database.postgres.pool_recycle,
    echo=settings.database.postgres.echo,
)

# 创建全局异步会话工厂
async_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# ==================== 后台线程数据库支持 ====================
# 为后台线程提供独立的数据库引擎和会话工厂
# （例如：在不同事件循环中运行的 LLM 使用统计日志回调）

_background_engine: Optional[AsyncEngine] = None
_background_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

def get_background_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    获取或创建供后台线程使用的数据库会话工厂（Session Factory）。
    该方法会创建一个独立的数据库引擎（Database Engine），
    以便在与主 FastAPI 应用不同的事件循环（Event Loop）中安全使用。
    适用于后台线程场景，例如异步日志记录、监控统计、
    回调任务等需要独立数据库连接的操作。
    """
    global _background_engine, _background_session_factory

    if _background_session_factory is None:
        _background_engine = create_async_engine(
            settings.database.postgres.async_url,
            pool_size=2,  # 更小的连接池配置，适合后台线程使用
            max_overflow=2,
            pool_timeout=30,
            pool_recycle=settings.database.postgres.pool_recycle,
            echo=False,
        )
        _background_session_factory = async_sessionmaker(
            bind=_background_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return _background_session_factory

@asynccontextmanager
async def get_background_session_context() -> AsyncGenerator[AsyncSession, None]:
    """上下文管理器，提供后台线程使用的数据库会话（Session）"""
    factory = get_background_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def close_background_db() -> None:
    """关闭后台线程使用的数据库连接"""
    global _background_engine, _background_session_factory
    if _background_engine is not None:
        await _background_engine.dispose()
        _background_engine = None
        _background_session_factory = None
        logger.info("后台线程数据库连接已关闭")

# ==================== Main Database Functions ====================
async def init_db() -> None:
    """初始化数据库表结构（如果不存在则创建）"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构已初始化")


async def close_db() -> None:
    """关闭数据库连接"""
    await _engine.dispose()
    logger.info("数据库连接已关闭")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话（Session）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话（Session）的上下文管理器"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise