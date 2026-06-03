"""
知识文档 CRUD 模块。
为存储在 PostgreSQL 中的知识文档提供异步数据库访问能力。
"""

class DocumentRepository:
    """
    用于管理 PostgreSQL 中知识文档的 CRUD 操作。
    提供以下功能：
    - 根据文档 ID 获取父文档（用于 post_process_retrieval 后处理阶段）
    - 文档的增删改查（CRUD）操作
    - 数据导入场景下的批量操作
    - 基于缓存的元数据选项查询，以提升检索效率
    """