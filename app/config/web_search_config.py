# app/config/web_search_config.py
"""
CookAgent 的 Web 搜索配置。
使用 Tavily API 执行 Web 搜索。
"""

from typing import Optional
from pydantic import BaseModel


class WebSearchConfig(BaseModel):
    """
    web 搜索 Tavily 配置 
    """

    enabled: bool = True
    api_key: Optional[str] = None  # Loaded from .env (WEB_SEARCH_API_KEY)
    max_results: int = 5
