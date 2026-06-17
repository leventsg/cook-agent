"""
CookAgent Web Search 工具

提供两个核心方法：
1. decide_search()
   判断是否需要执行网络搜索，并生成搜索参数

2. execute_search()
   使用 Tavily API 执行实际的网络搜索

采用 Tavily 官方 Python 客户端实现可靠的网络搜索能力
使用 LLM Tool Calling 获取结构化输出
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

from app.config import settings, LLMType
from app.llm import LLMProvider, get_usage_callbacks, llm_context

logger = logging.getLogger(__name__)

THRESHOLD_CONFIDENCE = 6  # 置信度阈值，用于判断是否需要执行网络搜索


class SearchDecisionInput(BaseModel):
    """搜索决策输入模式"""

    confidence: int = Field(
        description="Confidence score from 0-10, higher means more likely to need web search. 0-5: No web search needed, 6-10: Web search recommended",
        ge=0,
        le=10,
    )
    search_query: str = Field(
        description="Optimized search keywords (concise and precise) suitable for web search. The number of words should be kept minimal and focused.",
    )
    reason: str = Field(
        description="Brief explanation of why web search is or isn't needed"
    )


@dataclass
class WebSearchParams:
    """执行网络搜索的参数."""

    query: str
    max_results: int = 5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "max_results": self.max_results,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebSearchParams":
        return cls(
            query=data.get("query", ""),
            max_results=data.get("max_results", 5),
        )


@dataclass
class WebSearchDecision:
    """网络搜索决策结果"""

    confidence: int  # 0-10, 分数越高表示越需要执行网络搜索
    search_params: Optional[WebSearchParams] = None
    reason: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def should_search(self) -> bool:
        """判断是否需要执行网络搜索"""
        return self.confidence >= THRESHOLD_CONFIDENCE


@dataclass
class WebSearchResult:
    """单个网络搜索结果."""

    title: str
    snippet: str  # 摘要或关键信息
    source: str  # 网站名称或标识符
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "snippet": self.snippet,
            "source": self.source,
            "url": self.url,
        }


# 网络搜索的system prompt
WEB_SEARCH_DECISION_PROMPT_TEMPLATE = """
你是 CookAgent 的「Web 搜索决策模块」，专门判断当前用户问题是否需要进行互联网搜索来补充回答。

【决策原则】

需要 Web 搜索（confidence 应该较高，6-10）的情况：
1. **时效性信息**
   - 询问最近的美食新闻、餐厅推荐、食材价格趋势
   - 涉及季节性食材的当前市场情况
2. **本地知识库可能不足的内容**
   - 非常规或小众菜系的详细做法
   - 特定品牌产品的使用方法
   - 需要最新研究支持的营养健康信息
3. **用户明确要求搜索网络**
   - 用户提到"搜索一下"、"网上查查"等
4. **需要对比多来源信息**
   - 用户要求比较不同做法或观点

不需要 Web 搜索（confidence 应该较低，0-5）的情况：
1. **常规烹饪问题**
   - 经典菜谱、基础烹饪技巧
   - 常见食材处理方法
2. **对话延续**
   - 闲聊、确认、追问细节
   - 基于上下文的后续问题
3. **本地知识库足以回答**
   - 标准家常菜做法
   - 基础烹饪原理

【本地知识库已有的信息】
{document_summary}

{history}
"""

WEB_SEARCH_DECISION_PROMPT = ChatPromptTemplate.from_template(
    WEB_SEARCH_DECISION_PROMPT_TEMPLATE
)


class WebSearchTool:
    """
    网络搜索工具，提供决策和执行方法。

    使用 Tavily 官方 Python 客户端执行网络搜索。
    """

    MODULE_NAME = "web_search"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.FAST,
        api_key: Optional[str] = None,
        max_results: Optional[int] = None,
        provider: LLMProvider | None = None,
    ):
        """
        初始化网络搜索工具。

        Args:
            llm_type: LLM 类型（fast/normal）
            api_key: Tavily API 密钥（可选，也可以通过环境变量或配置文件设置）
            max_results: 最大搜索结果数量
        """
        web_search_config = settings.web_search

        self.api_key = (
            api_key or web_search_config.api_key or os.getenv("WEB_SEARCH_API_KEY", "")
        )
        self.max_results = max_results or web_search_config.max_results
        self.enabled = web_search_config.enabled

        # 初始化 Tavily client
        self._tavily_client: Optional[TavilyClient] = None

        # 初始化 LLM
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)

        # 创建决策工具
        self._decision_tool = self._create_decision_tool()

        # 设置 LLM 工具调用的回调函数以记录使用统计
        self._callbacks = get_usage_callbacks()
        base_llm = self._provider.create_llm(llm_type, temperature=0.3)
        self._llm = base_llm.bind_tools(
            [self._decision_tool], tool_choice="make_search_decision"
        )

    def _create_decision_tool(self):
        """创建搜索决策工具。"""

        @tool(args_schema=SearchDecisionInput)
        def make_search_decision(
            confidence: int,
            search_query: str,
            reason: str,
        ) -> dict:
            """
            做出是否需要网络搜索的决策。

            Args:
                confidence: 置信度分数，范围 0-10，越高表示越可能需要网络搜索
                search_query: 优化后的搜索关键词（简洁且精确）
                reason: 简要解释为什么需要或不需要网络搜索

            Returns:
                包含决策详情的字典，包括置信度分数、搜索关键词和解释
            """
            return {
                "confidence": confidence,
                "search_query": search_query,
                "reason": reason,
            }

        return make_search_decision

    @property
    def tavily_client(self) -> Optional[TavilyClient]:
        """获取 Tavily 客户端实例"""
        if self._tavily_client is None and self.api_key:
            try:
                self._tavily_client = TavilyClient(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Tavily client: {e}")
        return self._tavily_client

    async def decide_search(
        self,
        query: str,
        document_summary: Dict[str, List[str]],
        history_text: str = "",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> WebSearchDecision:
        """
        决定是否需要网络搜索并生成搜索参数。

        Args:
            query: 当前用户查询
            document_summary: 本地知识库中文档的摘要
            history_text: 格式化的对话历史
            user_id: 用户 ID（可选）
            conversation_id: 对话 ID（可选）

        Returns:
            WebSearchDecision 实例，包含置信度分数、搜索参数和解释
        """
        try:
            # 格式化文档摘要为字符串
            document_summary_str = ""
            if document_summary:
                dishes = document_summary.get("dish_name", [])
                document_summary_str = "已知菜品名称: " + ", ".join(dishes) + "\n"

            # 格式化prompt
            prompt = WEB_SEARCH_DECISION_PROMPT.format_prompt(
                history=history_text,
                document_summary=document_summary_str,
            )
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                response = await self._llm.with_config(
                    callbacks=self._callbacks
                ).ainvoke(prompt.messages)

            # 解析工具调用结果
            if not response.tool_calls:
                logger.warning("No tool call in response, returning low confidence")
                return WebSearchDecision(
                    confidence=0,
                    search_params=None,
                    reason="LLM未调用决策工具",
                    raw={},
                )

            # 获取第一个工具调用结果（目前只有一个工具调用）
            tool_call = response.tool_calls[0]
            args = tool_call["args"]

            confidence = int(args.get("confidence", 0))
            confidence = max(0, min(10, confidence))  # Clamp to 0-10

            search_query = args.get("search_query", query)
            reason = args.get("reason", "")

            # 创建搜索参数
            search_params = WebSearchParams(
                query=search_query,
                max_results=self.max_results,
            )

            return WebSearchDecision(
                confidence=confidence,
                search_params=search_params,
                reason=reason,
                raw=args,
            )

        except Exception as e:
            logger.error(f"Web search decision failed: {e}", exc_info=True)
            # 返回低置信度结果
            return WebSearchDecision(
                confidence=0,
                search_params=None,
                reason=f"Decision failed: {str(e)[:50]}",
                raw={},
            )

    async def execute_search(
        self,
        search_params: WebSearchParams,
    ) -> List[WebSearchResult]:
        """
        使用 Tavily API 执行网络搜索。

        Args:
            search_params: 搜索参数

        Returns:
            List[WebSearchResult]
        """
        if not self.tavily_client:
            logger.warning("Tavily client not initialized, returning empty results")
            return []

        try:
            # 使用 Tavily 搜索方法
            response = self.tavily_client.search(
                query=search_params.query,
                topic="general",
                search_depth="basic",
                max_results=search_params.max_results,
                include_answer=False,
                include_images=False,
                include_raw_content=True,
            )

            results = []
            for item in response.get("results", [])[: search_params.max_results]:
                results.append(
                    WebSearchResult(
                        title=item.get("title", ""),
                        snippet=item.get("content", ""),
                        source=self._extract_domain(item.get("url", "")),
                        url=item.get("url"),
                    )
                )

            logger.info(
                f"Tavily search completed: query='{search_params.query}', results={len(results)}"
            )
            return results

        except Exception as e:
            logger.error(f"Tavily search failed: {e}", exc_info=True)
            return []

    def _extract_domain(self, url: str) -> str:
        """从 URL 中提取域名，用于来源识别。"""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc
            # 移除 www. 前缀
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return "web"

    def format_results_for_context(
        self,
        results: List[WebSearchResult],
        max_length: int = 2000,
    ) -> str:
        """
        格式化搜索结果以包含在 LLM 上下文中。

        Args:
            results: 搜索结果列表
            max_length: 最大总字符长度

        Returns:
            格式化后的上下文字符串，用于 LLM 调用
        """
        if not results:
            return ""

        lines = []
        current_length = 0

        for i, result in enumerate(results, 1):
            entry = f"[{i}] {result.title}\n来源: {result.source}\n{result.snippet}"
            if result.url:
                entry += f"\n链接: {result.url}"
            entry += "\n"

            if current_length + len(entry) > max_length:
                break

            lines.append(entry)
            current_length += len(entry)

        return "\n".join(lines)


web_search_tool = WebSearchTool()
