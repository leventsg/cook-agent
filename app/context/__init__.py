"""
CookAgent 上下文模块

提供统一的会话上下文管理能力，包括：

- 上下文构建与组装（Manager）
- 上下文压缩与摘要生成（Compress）
"""

from app.context.manager import ContextManager
from app.context.compress import ContextCompressor

__all__ = [
    "ContextManager",
    "ContextCompressor",
]
