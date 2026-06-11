"""
多轮对话 API 接口，集成 RAG 功能

包含以下安全特性：
- 输入校验
- Prompt 注入攻击防护
"""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()