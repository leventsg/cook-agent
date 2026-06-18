# app/agent/tools/common/websearch.py
"""
网络搜索 Tool

使用 Tavily API 搜索互联网获取最新信息。
"""

import asyncio
import logging
from typing import Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """
    网络搜索 Tool。

    使用 Tavily API 搜索互联网获取最新信息。
    """

    name = "web_search"
    description = "搜索互联网获取最新信息。适合需要实时数据、新闻或外部来源时使用。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词或问题"},
            "max_results": {
                "type": "integer",
                "description": "返回结果数量 (1-10)",
                "default": 5,
            },
            "search_depth": {
                "type": "string",
                "enum": ["basic", "advanced"],
                "default": "basic",
                "description": "搜索深度：basic 快速搜索，advanced 深度搜索",
            },
            "include_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "限定搜索的域名列表，例如 ['who.int', 'cdc.gov']",
            },
            "exclude_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "排除的域名列表",
            },
        },
        "required": ["query"],
    }

    async def execute(
        self,
        query: str = "",
        max_results: int = 5,
        search_depth: str = "basic",
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
        **kwargs,
    ) -> ToolResult:
        """执行网络搜索。"""
        if not query:
            return ToolResult(success=False, error="Query is required")

        try:
            from tavily import TavilyClient
            from app.config import settings

            api_key = settings.web_search.api_key
            if not api_key:
                return ToolResult(
                    success=False,
                    error="Web search API key is not configured",
                )

            client = TavilyClient(api_key=api_key)

            search_params = {
                "query": query,
                "max_results": min(max(1, max_results), 10),
                "search_depth": search_depth,
                "include_answer": True,
            }

            if include_domains:
                search_params["include_domains"] = include_domains
            if exclude_domains:
                search_params["exclude_domains"] = exclude_domains

            response = await asyncio.to_thread(client.search, **search_params)

            results = []
            for result in response.get("results", []):
                results.append(
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "content": result.get("content", ""),
                        "score": result.get("score", 0),
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": results,
                    "answer": response.get("answer"),
                },
            )

        except ImportError:
            return ToolResult(
                success=False,
                error="tavily package is not installed. Run: pip install tavily-python",
            )
        except Exception as e:
            logger.exception(f"Web search failed: {e}")
            return ToolResult(success=False, error=f"Web search failed: {str(e)}")


__all__ = ["WebSearchTool"]
