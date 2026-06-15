# app/rag/pipeline/generation.py
"""用于查询改写与响应生成的 LLM 集成模块"""

import logging
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context


logger = logging.getLogger(__name__)

REWRITE_PROMPT_TEMPLATE = """
<|system|>
你是食谱数据库的智能搜索助手。你的任务是将用户的输入优化为一个**清晰、自然且完整**的句子，以便进行语义搜索。

**准则：**
1.  **仅限自然语言：** 不要输出关键词堆砌。重写后的查询必须是一个语法完整的句子或自然的问句（例如"我该如何制作……"或"有哪些……"）。
2.  **严禁幻觉：** 除非用户明确提及，否则不要添加具体的形容词（如"简单的"、"快速的"、"健康的"、"辣的"）。
3.  **澄清但不设限：** 如果查询很模糊（例如"我饿了"），将其重写为请求食物推荐的通用但清晰的句子，除非用户指定，否则不要假设是午餐还是晚餐。
4.  **扩展概念：** 对于推荐类查询，可以适当扩展相关概念以提高检索效果。例如"荤素搭配"可以扩展为"既有肉类又有蔬菜的菜品"。
5.  **保持语气：** 保持礼貌和对话感，与原查询的语言风格相匹配。

**示例：**

-   Original: "我想做点吃的"
    -> Rewritten: "你能推荐一些适合我做的食谱吗？"
    *（解释：将模糊的愿望转化为清晰的推荐请求，没有擅自假设是"晚餐"或"简单"的菜。）*

-   Original: "今晚吃啥？"
    -> Rewritten: "今晚晚餐有什么好的食谱推荐吗？"
    *（解释："今晚"暗示了晚餐场景，将其转化为自然的问句。）*

-   Original: "有鸡蛋和西红柿，能做什么"
    -> Rewritten: "用鸡蛋和西红柿可以做什么菜？"
    *（解释：澄清了利用特定食材烹饪的意图，保留了问句格式。）*

-   Original: "红烧肉做法"
    -> Rewritten: "如何制作红烧肉？"
    *（解释：微调语法使其成为完整的句子，意图保持不变。）*

-   Original: "来点甜的"
    -> Rewritten: "给我看一些关于甜点或甜食的食谱。"
    *（解释：将"甜的"扩展为自然的语义类别"甜点"，并组成完整句子。）*

-   Original: "有什么荤素搭配的家常菜？"
    -> Rewritten: "有哪些既有肉类又有蔬菜的家常菜？"
    *（解释：将"荤素搭配"扩展为"既有肉类又有蔬菜"，使语义更清晰，便于检索。）*

-   Original: "推荐几道清淡的菜"
    -> Rewritten: "有哪些口味清淡、不油腻的菜品？"
    *（解释：将"清淡"扩展为"口味清淡、不油腻"，提高检索准确性。）*

<|user|>
原始的查询: {query}
<|assistant|>
只输出1句重写后的查询，禁止添加前缀/后缀/解释/Markdown/项目符号/标题，禁止多行，仅返回重写后的自然语言查询:
"""
REWRITE_PROMPT = ChatPromptTemplate.from_template(REWRITE_PROMPT_TEMPLATE)


class GenerationIntegrationModule:
    """
    集成LLM，用于执行查询改写和响应生成任务
    """

    MODULE_NAME = "rag_answer_gen"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.FAST,
        provider: LLMProvider | None = None,
    ):
        """
        初始化
        """
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)
        # 使用可追踪的 Invoker 记录调用统计信息
        self._llm = self._provider.create_invoker(llm_type, temperature=0.0)

    async def rewrite_query(
        self,
        query: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        使用 LLM 将模糊查询改写为更具体的查询以获得更好的检索效果。
        """
        template = REWRITE_PROMPT.format_prompt(query=query)
        # 使用可追踪的 Invoker 记录调用统计信息
        with llm_context(self.MODULE_NAME, user_id, conversation_id):
            response = await self._llm.ainvoke(list(template.messages))
        rewritten_query = response.content.strip()

        if rewritten_query != query:
            logger.info(f"Query rewritten: '{query}' -> '{rewritten_query}'")
            # 可选：将重写后的查询与原始查询合并，方便调试
            # rewritten_query = f"Origin User Query: {query}\nAI Rewritten Query: {rewritten_query}"
        else:
            logger.info(f"Query did not require rewriting: '{query}'")

        return rewritten_query

