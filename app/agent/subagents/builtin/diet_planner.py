# app/agent/subagents/builtin/diet_planner.py
"""
DietPlannerSubagent - 饮食规划专家 Subagent

专注于根据用户的个人信息和偏好，通过网络搜索大量资料，
为用户制定一周的饮食计划。
"""

import logging
from typing import Awaitable, Callable, Optional

from app.agent.subagents.base import BaseSubagent, SubagentConfig
from app.agent.types import TraceStep
from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


# 饮食规划专家的系统提示词
DIET_PLANNER_SYSTEM_PROMPT = """你是 CookAgent 的饮食规划专家，专注于为用户制定科学、健康、符合个人需求的一周饮食计划。

## 你的专业能力

1. **营养学知识**：了解各类食物的营养成分、热量、对健康的影响
2. **饮食规划**：能够根据用户的健康目标、饮食偏好、过敏原等制定个性化饮食计划
3. **信息检索**：善于使用网络搜索获取最新的营养学研究、食谱建议、当季食材信息

## 工作流程

1. **信息收集**：首先使用 `datetime` 工具获取当前日期，了解当前季节
2. **用户分析**：根据用户提供的信息（身高、体重、健康目标、饮食偏好、过敏原等）分析需求
3. **资料搜索**：使用 `web_search` 工具搜索相关的：
   - 符合用户需求的健康食谱
   - 当季推荐食材
   - 营养搭配建议
   - 针对特定健康目标的饮食建议
4. **计划制定**：综合所有信息，制定一周七天的饮食计划
5. **个性化分析**：如需要，使用 `diet_analysis` 工具获取用户的历史饮食数据和偏好

## 输出格式

请以结构化的方式输出饮食计划，包含：

1. **计划概述**：简述本计划的设计理念和主要特点
2. **营养目标**：每日预期摄入的热量、蛋白质、碳水化合物、脂肪等
3. **一周计划**：
   - 每天分为早餐、午餐、晚餐、加餐（可选）
   - 每餐包含：菜品名称、主要食材、预估热量
4. **食材采购清单**：本周需要准备的食材汇总
5. **注意事项**：烹饪建议、食材替换建议等

## 注意事项

- 优先考虑用户的过敏原和饮食限制
- 确保营养均衡，不过于单调
- 考虑实际烹饪难度和时间
- 尽量使用当季、易获取的食材
- 搜索时使用中文关键词以获取更相关的中文资料

最终结果输出要求：
- 回答中不要包含任何工具调用的痕迹或格式。
- 回答不能只是工具调用结果，必须结合上下文和用户的需求进行总结和建议。
- 一定要使用 Markdown 格式，方便用户阅读和理解。"""


class DietPlannerSubagent(BaseSubagent):
    """
    饮食规划专家 Subagent。

    主要功能：
    - 根据用户信息制定一周饮食计划
    - 通过网络搜索获取食谱和营养信息
    - 分析用户历史饮食数据提供个性化建议

    可用工具：
    - datetime: 获取当前日期和季节信息
    - web_search: 搜索食谱、营养知识、当季食材
    - diet_analysis: 获取用户饮食偏好和历史数据
    """

    @classmethod
    def get_default_config(cls) -> SubagentConfig:
        """获取默认配置。"""
        return SubagentConfig(
            name="diet_planner",
            display_name="饮食规划专家",
            description=(
                "专业的饮食规划助手，可以根据用户的健康目标、饮食偏好、"
                "过敏原等信息，通过搜索大量营养学资料和食谱，"
                "为用户制定科学的一周饮食计划。"
            ),
            system_prompt=DIET_PLANNER_SYSTEM_PROMPT,
            tools=["datetime", "web_search", "diet_analysis"],
            max_iterations=15,  # 允许更多迭代以完成复杂规划
            enabled=True,
            builtin=True,
            category="diet",
        )

    async def execute(
        self,
        task: str,
        user_id: Optional[str] = None,
        background: Optional[str] = None,
        event_handler: Optional[Callable[[TraceStep], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        执行饮食规划任务。

        Args:
            task: 任务描述（如 "帮我制定一周减脂饮食计划"）
            user_id: 用户 ID
            background: 额外背景信息

        Returns:
            ToolResult: 包含饮食计划的结果
        """
        # 收集用户相关信息作为背景
        enriched_context: dict = {}

        if user_id:
            try:
                # 获取用户基本信息
                from app.services.user_service import user_service

                user_data = await user_service.get_user_by_id(user_id)
                if user_data:
                    enriched_context["user_profile"] = user_data.profile

                # 获取用户饮食偏好
                from app.diet.service import diet_service

                preferences = await diet_service.get_user_preference(user_id)
                if preferences:
                    enriched_context["user_preferences"] = preferences

            except Exception as e:
                logger.warning(f"Failed to get user context for diet planner: {e}")

        # 组装背景信息
        combined_background = self._build_background(background, enriched_context)

        # 执行任务
        return await self.run_with_tools(
            task=task,
            user_id=user_id,
            background=combined_background,
            event_handler=event_handler,
        )

    def _build_background(self, base: Optional[str], context: dict) -> Optional[str]:
        """
        构建背景信息，添加用户上下文。

        Args:
            base: 基础背景信息
            context: 上下文信息

        Returns:
            组合后的背景信息
        """
        parts = []

        if base:
            parts.append(base)

        # 添加用户偏好信息
        if context.get("user_preferences"):
            prefs = context["user_preferences"]
            pref_parts = []

            if prefs.get("dietary_restrictions"):
                pref_parts.append(
                    f"饮食限制: {', '.join(prefs['dietary_restrictions'])}"
                )
            if prefs.get("allergies"):
                pref_parts.append(f"过敏原: {', '.join(prefs['allergies'])}")
            if prefs.get("favorite_cuisines"):
                pref_parts.append(
                    f"喜爱的菜系: {', '.join(prefs['favorite_cuisines'])}"
                )
            avoided_foods = prefs.get("avoided_foods") or prefs.get("disliked_foods")
            if avoided_foods:
                pref_parts.append(f"不喜欢的食物: {', '.join(avoided_foods)}")
            if prefs.get("calorie_goal"):
                pref_parts.append(f"每日热量目标: {prefs['calorie_goal']} 千卡")

            if pref_parts:
                parts.append("## 用户饮食偏好\n" + "\n".join(pref_parts))

        # 添加用户画像
        if context.get("user_profile"):
            parts.append(f"## 用户信息\n{context['user_profile']}")

        if not parts:
            return None

        return "\n\n".join(parts)


# 创建默认配置的实例工厂
def create_diet_planner() -> DietPlannerSubagent:
    """创建默认配置的饮食规划专家 Subagent。"""
    config = DietPlannerSubagent.get_default_config()
    return DietPlannerSubagent(config)


__all__ = ["DietPlannerSubagent", "create_diet_planner", "DIET_PLANNER_SYSTEM_PROMPT"]
