# app/diet/tools/diet_analysis_tool.py
"""
饮食分析 Tool

提供饮食数据的分析和统计功能，供 Agent 调用。
"""

import logging
from datetime import date, datetime
from typing import Optional

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.service import diet_service

logger = logging.getLogger(__name__)


class DietAnalysisTool(BaseTool):
    """
    饮食分析工具。

    提供每日摘要、每周摘要、计划与实际偏差分析等功能。
    """

    name = "diet_analysis"
    description = """分析用户的饮食数据。支持以下操作：
- daily_summary: 获取某天饮食摘要
- weekly_summary: 获取某周饮食摘要
- deviation: 计划 vs 实际偏差分析
- preferences: 获取饮食偏好
- update_preferences: 更新饮食偏好"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "daily_summary",
                    "weekly_summary",
                    "deviation",
                    "preferences",
                    "update_preferences",
                ],
                "description": "操作类型：daily_summary/weekly_summary/deviation/preferences/update_preferences",
            },
            "user_id": {
                "type": "string",
                "description": "用户 ID，必须传入",
            },
            "target_date": {
                "type": "string",
                "description": "目标日期 YYYY-MM-DD（用于 daily_summary，可不传默认今天）",
            },
            "week_start_date": {
                "type": "string",
                "description": "周开始日期 YYYY-MM-DD（周一，用于 weekly_summary/deviation，可不传默认本周）",
            },
            "dietary_restrictions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "饮食限制，如 ['vegetarian', 'gluten-free']",
            },
            "allergies": {
                "type": "array",
                "items": {"type": "string"},
                "description": "过敏原，如 ['peanuts', 'shellfish']",
            },
            "favorite_cuisines": {
                "type": "array",
                "items": {"type": "string"},
                "description": "喜爱的菜系，如 ['chinese', 'italian']",
            },
            "avoided_foods": {
                "type": "array",
                "items": {"type": "string"},
                "description": "不喜欢的食物",
            },
            "disliked_foods": {
                "type": "array",
                "items": {"type": "string"},
                "description": "不喜欢的食物（兼容字段）",
            },
            "preferred_foods": {
                "type": "array",
                "items": {"type": "string"},
                "description": "偏好的食物",
            },
            "calorie_goal": {
                "type": "integer",
                "description": "每日卡路里目标",
            },
            "protein_goal": {
                "type": "number",
                "description": "每日蛋白质目标(克)",
            },
            "fat_goal": {
                "type": "number",
                "description": "每日脂肪目标(克)",
            },
            "carbs_goal": {
                "type": "number",
                "description": "每日碳水目标(克)",
            },
        },
        "required": ["action", "user_id"],
    }

    async def execute(
        self,
        action: str = "",
        user_id: str = "",
        target_date: Optional[str] = None,
        week_start_date: Optional[str] = None,
        dietary_restrictions: Optional[list] = None,
        allergies: Optional[list] = None,
        favorite_cuisines: Optional[list] = None,
        avoided_foods: Optional[list] = None,
        disliked_foods: Optional[list] = None,
        preferred_foods: Optional[list] = None,
        calorie_goal: Optional[int] = None,
        protein_goal: Optional[float] = None,
        fat_goal: Optional[float] = None,
        carbs_goal: Optional[float] = None,
        **kwargs,
    ) -> ToolResult:
        """执行饮食分析操作"""
        if not action:
            return ToolResult(success=False, error="action 参数是必需的")
        if not user_id:
            return ToolResult(success=False, error="user_id 参数是必需的")

        try:
            if action == "daily_summary":
                if not target_date:
                    actual_date = date.today()
                else:
                    actual_date = datetime.strptime(target_date, "%Y-%m-%d").date()

                result = await diet_service.get_daily_summary(user_id, actual_date)
                return ToolResult(
                    success=True,
                    data={
                        "message": f"获取 {actual_date.isoformat()} 的饮食摘要成功",
                        "date": actual_date.isoformat(),
                        "summary": result,
                    },
                )

            elif action == "weekly_summary":
                actual_week_start = None
                if week_start_date:
                    actual_week_start = datetime.strptime(
                        week_start_date, "%Y-%m-%d"
                    ).date()

                result = await diet_service.get_weekly_summary(
                    user_id, actual_week_start
                )
                return ToolResult(
                    success=True,
                    data={
                        "message": "获取每周饮食摘要成功",
                        "summary": result,
                    },
                )

            elif action == "deviation":
                actual_week_start = None
                if week_start_date:
                    actual_week_start = datetime.strptime(
                        week_start_date, "%Y-%m-%d"
                    ).date()

                result = await diet_service.get_deviation_analysis(
                    user_id, actual_week_start
                )
                return ToolResult(
                    success=True,
                    data={
                        "message": "获取偏差分析成功",
                        "analysis": result,
                    },
                )

            elif action == "preferences":
                result = await diet_service.get_user_preference(user_id)
                if not result:
                    return ToolResult(
                        success=True,
                        data={
                            "message": "用户暂无饮食偏好设置",
                            "preference": None,
                        },
                    )
                return ToolResult(
                    success=True,
                    data={
                        "message": "获取用户偏好成功",
                        "preference": result,
                    },
                )

            elif action == "update_preferences":
                update_data = {}
                if dietary_restrictions is not None:
                    update_data["dietary_restrictions"] = dietary_restrictions
                if allergies is not None:
                    update_data["allergies"] = allergies
                if favorite_cuisines is not None:
                    update_data["favorite_cuisines"] = favorite_cuisines
                actual_avoided = avoided_foods if avoided_foods is not None else disliked_foods
                if actual_avoided is not None:
                    update_data["avoided_foods"] = actual_avoided
                if preferred_foods is not None:
                    update_data["preferred_foods"] = preferred_foods
                if calorie_goal is not None:
                    update_data["calorie_goal"] = calorie_goal
                if protein_goal is not None:
                    update_data["protein_goal"] = protein_goal
                if fat_goal is not None:
                    update_data["fat_goal"] = fat_goal
                if carbs_goal is not None:
                    update_data["carbs_goal"] = carbs_goal

                if not update_data:
                    return ToolResult(
                        success=False,
                        error="update_preferences 操作需要至少一个偏好参数",
                    )

                result = await diet_service.update_user_preference(
                    user_id, **update_data
                )
                return ToolResult(
                    success=True,
                    data={
                        "message": "更新用户偏好成功",
                        "preference": result,
                    },
                )

            else:
                return ToolResult(
                    success=False,
                    error=f"未知操作: {action}",
                )

        except Exception as e:
            logger.exception(f"DietAnalysisTool execution failed: {e}")
            return ToolResult(
                success=False,
                error=f"操作失败: {str(e)}",
            )


__all__ = ["DietAnalysisTool"]
