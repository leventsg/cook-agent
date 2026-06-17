import logging, json
import re
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context
from app.utils.structured_json import extract_first_valid_json

logger = logging.getLogger(__name__)

HISTORY_REWRITE_PROMPT_TEMPLATE = """
你是 CookAgent 的「检索查询重写器」。你的任务是：**将用户的当前问题结合对话历史，重写为一条完整、独立、自然、可直接用于菜谱与烹饪知识库语义检索的一句话查询**

【重写规则（必须严格遵守）】

1. 指代消解  
- 将“它 / 这个 / 那个 / 第一个 / 上一道”等指代词，替换为对话历史中已明确出现的具体菜品、食材或对象  
- 禁止猜测或引入未出现的信息  

2. 上下文补全  
- 若当前问题无法独立理解，补充**对检索必要且直接相关**的历史信息  
- 只补充与“做什么 / 怎么做 / 推荐什么”直接相关的内容  

3. 语言要求  
- 输出必须是**一整句**通顺、自然的中文  
- 使用自然问句或陈述句  
- 禁止列表、标签、关键词堆砌  

4. 抽象偏好明确化（仅限已有语义）  
- 可将抽象描述转为等价的明确表达  
  - “清淡” → “口味清淡、不油腻”  
- 不得新增具体条件或限制  

5. 幻觉与扩展限制  
- 对话中未出现的信息一律不得添加  
- 不得擅自加入“简单 / 快速 / 健康 / 低脂 / 辣”等描述  

6. 模糊问题处理  
- 若问题本身无法确定具体对象（如“我饿了”“吃点啥”）  
- 重写为**不设限、不假设条件**的通用菜谱请求  

{history}

【输出格式（强约束）】

你 **必须且只能** 输出以下 JSON，对象结构固定，不得添加或省略字段，不得输出任何多余文本：

{{
  "query": "<重写后的一句话查询>"
}}
"""

HISTORY_REWRITE_PROMPT = ChatPromptTemplate.from_template(
    HISTORY_REWRITE_PROMPT_TEMPLATE
)


class QueryRewriter:
    """基于会话历史的查询改写，用于多轮对话检索"""

    MODULE_NAME = "query_rewriter"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.FAST,
        provider: LLMProvider | None = None,
    ):
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)
        self._llm = self._provider.create_invoker(llm_type, temperature=0.0)

    async def rewrite(
        self,
        current_query: str,
        history_text: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        # 如果历史为空或空白字符，直接返回当前查询
        if not history_text.strip():
            return current_query

        debugc = ""

        try:
            template = HISTORY_REWRITE_PROMPT.format_prompt(
                history=history_text,
            )
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                response = await self._llm.ainvoke(list(template.messages))
            content = response.content.strip()
            debugc = content

            result = extract_first_valid_json(content)
            rewritten = result.get("query", current_query).strip()

            return rewritten

        except Exception as exc:  
            logger.warning("Failed to rewrite query with history: %s", exc)
            logger.info("Rewrite debug content: %s", debugc)

        return current_query
