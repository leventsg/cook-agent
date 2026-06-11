"""
用户信息相关接口：获取当前用户信息和更新用户信息
"""
import logging
from fastapi import APIRouter
router = APIRouter()
logger = logging.getLogger(__name__)