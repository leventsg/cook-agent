"""
CookAgent 视觉 Agent

负责图像分析并识别与烹饪相关的用户意图

该 Agent 的主要功能：
1. 结合用户文本提示词分析上传的图像
2. 判断内容是否与烹饪或食物相关
3. 生成相应回复，或将请求交由主对话流程处理
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.vision.provider import VisionProvider, ImageInput, vision_provider

logger = logging.getLogger(__name__)

class VisionIntent(str, Enum):
    """视觉分析结果的意图分类"""

    # 食物/烹饪相关 -
    DISH_IDENTIFICATION = "dish_identification"  # 用户想识别菜品
    RECIPE_REQUEST = "recipe_request"  # 用户想获取菜品的食谱
    INGREDIENT_IDENTIFICATION = "ingredient_identification"  # 用户想识别食材
    COOKING_GUIDANCE = "cooking_guidance"  # 用户想获取烹饪技巧或流程帮助
    FOOD_QUESTION = "food_question"  # 用户的一般食物相关问题

    # 与食物无关 -直接返回响应
    GENERAL_IMAGE = "general_image"  # 非食物图像
    UNCLEAR = "unclear"  # 无法确定意图

@dataclass
class VisionAnalysisResult:
    """
    表示视觉处理的结果。

    Attributes:
        is_food_related: 判断图像是否与烹饪或食物相关
        intent: 意图分类结果
        description: 图像内容描述
        extracted_info: 提取的结构化信息（菜品名称、食材等）
        direct_response: 如果与食物无关，则为直接响应
        confidence: 置信度评分 (0-1)
        raw_response: 原始模型响应
    """

    is_food_related: bool
    intent: VisionIntent
    description: str
    extracted_info: dict
    direct_response: Optional[str]
    confidence: float
    raw_response: str

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "is_food_related": self.is_food_related,
            "intent": self.intent.value,
            "description": self.description,
            "extracted_info": self.extracted_info,
            "direct_response": self.direct_response,
            "confidence": self.confidence,
        }


class VisionAnalysisOutput(BaseModel):
    is_food_related: bool
    intent: str
    description: str
    extracted_info: Dict[str, Any] = Field(default_factory=dict)
    direct_response: Optional[str] = None
    confidence: float = 0.5


# 视觉分析提示词模版
VISION_ANALYSIS_PROMPT = """你是 CookAgent 的视觉理解模块，专门用于分析用户上传的图片并结合用户的文字提问来理解用户意图。

⚠️ 严格输出要求：
仅输出一个 JSON 对象，禁止输出任何解释、前后缀、markdown 代码块或额外文本。务必遵守字段与类型。

【你的任务】
1. 仔细观察图片内容
2. 结合用户的文字提问（如果有）
3. 判断图片是否与「菜品/食材/烹饪/饮食」相关
4. 提取关键信息并进行意图分类

【意图分类说明】
- dish_identification: 用户想识别图中的菜品是什么
- recipe_request: 用户想知道图中菜品的做法/食谱
- ingredient_identification: 用户想识别图中的食材
- cooking_guidance: 用户在烹饪过程中需要指导（如火候、步骤）
- food_question: 其他与食物相关的问题
- general_image: 图片与食物/烹饪无关
- unclear: 无法确定图片内容或意图

【判定原则】
1. 如果图片中包含：菜品、食材、厨房场景、烹饪过程、餐具摆盘等，则属于「食物相关」
2. 如果图片是：风景、人物、动物、物品、文档等非食物内容，则属于「非食物相关」
3. 结合用户的文字提问来理解完整意图，不要仅凭图片判断

【用户提问】
{user_query}

【输出格式（JSON）】
你必须严格输出以下 JSON 格式（单个对象），不要输出其他任何字符：

{{
    "is_food_related": true/false,
    "intent": "意图分类（使用上述分类之一）",
    "description": "图片内容的简要描述（1-2句话）",
    "extracted_info": {{
        "dish_name": "识别出的菜品名称（如有）",
        "ingredients": ["识别出的食材列表（如有）"],
        "cooking_stage": "烹饪阶段描述（如有）",
        "other": "其他相关信息"
    }},
    "direct_response": "如果图片与食物无关，在此提供简短回复；如果食物相关则为null",
    "confidence": 0.0-1.0之间的置信度
}}

如果无法识别或不确定，也必须按此格式输出，给出最佳猜测并将简要描述写入 description。
"""

class VisionAgent:
    """
    用于图像分析和意图识别的视觉 Agent
    该 Agent 负责处理图像输入，并根据内容是否与食物或烹饪相关进行分类，
    随后提取相关信息
    """
    def __init__(self, provider: Optional[VisionProvider] = None):
        """
        初始化 visison agent

        Args:
            provider: Vision provider instance.
        """
        self._provider = provider or vision_provider

    @property
    def is_available(self) -> bool:
        return self._provider.is_enabled
    
    async def analyze(
        self,
        images: List[ImageInput],
        user_query: str = "",
        history_context: str = "",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> VisionAnalysisResult:
        """
        分析图像并确定与烹饪相关意图。

        Args:
            images: 图像输入列表
            user_query: 用户的文字提示或问题
            history_context: 可选的对话历史用于上下文
            user_id: 用户ID用于跟踪（可选）
            conversation_id: 对话ID用于跟踪（可选）

        Returns:
            VisionAnalysisResult
        """
        if not self.is_available:
            logger.warning("Vision analysis not available, returning default result")
            return VisionAnalysisResult(
                is_food_related=False,
                intent=VisionIntent.UNCLEAR,
                description="视觉分析功能未启用",
                extracted_info={},
                direct_response="抱歉，图片识别功能暂时不可用。请尝试用文字描述您的问题。",
                confidence=0.0,
                raw_response="",
            )

        # 构建提示词，结合用户查询和历史上下文
        prompt = VISION_ANALYSIS_PROMPT.format(
            user_query=user_query if user_query else "（用户没有提供文字说明）"
        )

        if history_context:
            prompt = f"【对话上下文】\n{history_context}\n\n{prompt}"

        try:
            # Call vision model
            output = await self._provider.analyze_json(
                text=prompt,
                images=images,
                schema=VisionAnalysisOutput,
                user_id=user_id,
                conversation_id=conversation_id,
            )

            return self._result_from_output(output)

        except Exception as e:
            logger.error(f"Vision analysis failed: {e}", exc_info=True)
            return VisionAnalysisResult(
                is_food_related=False,
                intent=VisionIntent.UNCLEAR,
                description="图片分析过程中出现错误",
                extracted_info={},
                direct_response=f"抱歉，分析图片时遇到问题：{str(e)[:100]}。请稍后重试或用文字描述您的问题。",
                confidence=0.0,
                raw_response=str(e),
            )
    
    def _result_from_output(self, output: VisionAnalysisOutput) -> VisionAnalysisResult:
        """将结构化视觉输出转换为业务结果对象。"""
        try:
            intent = VisionIntent(output.intent)
        except ValueError:
            intent = VisionIntent.UNCLEAR

        return VisionAnalysisResult(
            is_food_related=output.is_food_related,
            intent=intent,
            description=output.description,
            extracted_info=output.extracted_info,
            direct_response=output.direct_response
            if not output.is_food_related
            else None,
            confidence=float(output.confidence),
            raw_response=output.model_dump_json(),
        )

    def _check_food_keywords(self, text: str) -> bool:
        """检查文本是否包含食物关键词"""
        keywords = settings.vision.food_related_keywords
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)
    
    def build_context_for_rag(
        self, result: VisionAnalysisResult, user_query: str
    ) -> str:
        """
        构建用于 RAG 的上下文字符串，基于视觉分析结果。
        该方法用于构建结构化上下文信息，当图像内容与食物或烹饪相关时，可将该上下文注入到对话流程中

        Args:
            result: 视觉分析结果
            user_query: 原始用户查询

        Returns:
            RAG 上下文字符串
        """
        if not result.is_food_related:
            return ""

        parts = []

        if result.description:
            parts.append(f"【图片内容】{result.description}")

        info = result.extracted_info
        if info:
            if info.get("dish_name"):
                parts.append(f"【识别菜品】{info['dish_name']}")
            if info.get("ingredients"):
                ingredients = (
                    ", ".join(info["ingredients"])
                    if isinstance(info["ingredients"], list)
                    else info["ingredients"]
                )
                parts.append(f"【识别食材】{ingredients}")
            if info.get("cooking_stage"):
                parts.append(f"【烹饪阶段】{info['cooking_stage']}")
            if info.get("other"):
                parts.append(f"【其他信息】{info['other']}")

        intent_map = {
            VisionIntent.DISH_IDENTIFICATION: "用户想知道图中的菜品是什么",
            VisionIntent.RECIPE_REQUEST: "用户想获取图中菜品的做法",
            VisionIntent.INGREDIENT_IDENTIFICATION: "用户想识别图中的食材",
            VisionIntent.COOKING_GUIDANCE: "用户在烹饪过程中需要指导",
            VisionIntent.FOOD_QUESTION: "用户对图中的食物有疑问",
        }
        if result.intent in intent_map:
            parts.append(f"【用户意图】{intent_map[result.intent]}")

        return "\n".join(parts)


vision_agent = VisionAgent()
