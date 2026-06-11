"""
LLM 使用统计 API 接口
提供 Token 使用情况、模型分布以及模块级统计指标等数据访问能力
"""
from fastapi import APIRouter
import logging
logger = logging.getLogger(__name__)
router = APIRouter()