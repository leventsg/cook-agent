"""
Agent API 接口，用于支持工具增强对话
独立于会话接口（Conversation API），专为基于 Agent 的交互场景设计
"""
from fastapi import APIRouter
import logging
logger = logging.getLogger(__name__)
router = APIRouter()