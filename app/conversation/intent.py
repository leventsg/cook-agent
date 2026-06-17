import json
import logging
from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context
from app.utils.structured_json import extract_first_valid_json

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """用户查询意图识别结果枚举"""

    RECIPE_SEARCH = "recipe_search"
    COOKING_TIPS = "cooking_tips"
    INGREDIENT_INFO = "ingredient_info"
    GENERAL_CHAT = "general_chat"
    RECOMMENDATION = "recommendation"


@dataclass
class IntentDetectionResult:
    """结构化的意图检测结果，包括是否需要 RAG 检索、具体意图分类、判断理由和原始输出"""

    need_rag: bool
    intent: QueryIntent
    reason: str
    raw: dict


INTENT_DETECTION_PROMPT_TEMPLATE = """
你是 CookAgent 的「用户意图识别与检索决策模块」，专门用于判断**是否需要查询烹饪知识库（RAG）**，并给出准确的意图分类。你的判断必须结合：
- 用户的【当前问题】
- 已压缩/整理后的【对话历史上下文】
你的目标不是泛化分类，而是**为“是否检索菜谱与烹饪知识”做决策**。

【核心决策原则】

只有当**当前问题需要依赖具体菜谱、做法步骤、烹饪技巧或可执行方案**时，才将 need_rag 设为 true。

如果仅是：
- 观点性、解释性、确认性
- 闲聊或情绪回应
- 与“如何做菜”无直接关系
则 need_rag 必须为 false。

【need_rag = true 的典型情况】

满足以下任一情况即可：
1. **菜谱 / 做法查询**
   - 明确询问某道菜怎么做、步骤、火候、时间
   - “X 怎么做”“做 X 需要什么”
2. **基于食材 / 条件的可执行建议**
   - “有 A、B、C 能做什么菜”
   - “减脂期间晚餐推荐做什么”
3. **烹饪技巧与操作问题**
   - 处理方法、口味调整、失败补救
   - 时间、温度、器具、流程相关问题
4. **承接式问题（需结合上下文）**
   - 使用指代或省略：“这个怎么做”“第二种呢”
   - 基于之前推荐继续追问细节

【need_rag = false 的典型情况】

1. **纯对话或流程控制**
   - 闲聊、感谢、寒暄
   - “好的”“明白了”“继续”
2. **确认 / 澄清 / 选择类问题**
   - “这个可以吗？”
   - “就用第一个方案”
3. **与烹饪无关的内容**

【intent 分类说明】

intent 用于语义标签，除了general_chat外均表示需要 RAG 支持（即 need_rag 为 true）：
- recipe_search （need_rag = true）
  查询具体菜品、完整做法、步骤流程
- cooking_tips  （need_rag = true）
  烹饪技巧、经验、火候、调味、失败处理
- ingredient_info  （need_rag = true）
  食材相关问题
- recommendation  （need_rag = true）
  菜品推荐、菜单搭配、场景化建议
- general_chat  （need_rag = false）
  闲聊、确认、情绪回应、非任务性对话

{history}

【输出格式（强约束）】

你 **必须且只能** 输出以下 JSON，对象结构固定，不得添加或省略字段，不得输出任何多余文本：

{{
    "need_rag": true/false, 
    "intent": "intent_type", 
    "reason": "简短、明确的判断理由说明为什么需要或不需要 RAG 检索"
}}
"""

INTENT_DETECTION_PROMPT = ChatPromptTemplate.from_template(
    INTENT_DETECTION_PROMPT_TEMPLATE
)


class IntentDetector:
    """
    用于检测用户意图并判断是否需要 RAG 检索的模块
    """

    MODULE_NAME = "intent_detector"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.FAST,
        provider: LLMProvider | None = None,
    ):
        """初始化意图检测器，使用全局或覆盖的 LLM 配置"""
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)
        self._llm = self._provider.create_invoker(llm_type, temperature=0.0)

    async def detect(
        self,
        history_text: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> IntentDetectionResult:
        """
        检测用户意图并判断是否需要 RAG 检索

        Args:
            history_text: 已格式化的历史上下文文本（已通过 ContextManager 连接）
            user_id: 用户 ID（可选）
            conversation_id: 对话 ID（可选）
        """
        history_str = history_text
        debugc = ""

        try:
            template = INTENT_DETECTION_PROMPT.format_prompt(
                history=history_str,
            )
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                response = await self._llm.ainvoke(list(template.messages))
            content = response.content.strip()
            debugc = content

            result = extract_first_valid_json(content)
            need_rag = result.get("need_rag", True)
            intent_str = result.get("intent", "general_chat")
            reason = result.get("reason", "")

            intent_map = {
                "recipe_search": QueryIntent.RECIPE_SEARCH,
                "cooking_tips": QueryIntent.COOKING_TIPS,
                "ingredient_info": QueryIntent.INGREDIENT_INFO,
                "recommendation": QueryIntent.RECOMMENDATION,
                "general_chat": QueryIntent.GENERAL_CHAT,
            }
            intent = intent_map.get(intent_str, QueryIntent.GENERAL_CHAT)

            return IntentDetectionResult(
                need_rag=need_rag,
                intent=intent,
                reason=reason,
                raw=result,
            )

        except Exception as exc:
            logger.warning(
                "Intent detection failed: %s. Defaulting to non-RAG mode.", exc
            )
            logger.info(debugc)
            return IntentDetectionResult(
                need_rag=False,
                intent=QueryIntent.GENERAL_CHAT,
                reason="Detection failed, using default",
                raw={},
            )
