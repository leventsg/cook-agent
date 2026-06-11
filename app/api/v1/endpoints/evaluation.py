"""
RAG 评测指标 API 接口
提供评测统计、趋势分析以及质量告警等数据访问能力
"""
from fastapi import APIRouter
import logging
logger = logging.getLogger(__name__)
router = APIRouter()