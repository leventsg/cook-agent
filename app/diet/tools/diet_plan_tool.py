# app/diet/tools/diet_plan_tool.py
"""
饮食计划管理 Tool

提供饮食计划的 CRUD 操作，供 Agent 调用。
"""

import logging
from datetime import datetime
from typing import Optional, List

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.service import diet_service

logger = logging.getLogger(__name__)


class DietPlanTool(BaseTool):
    """
    饮食计划餐次管理工具。

    支持按周管理计划餐次。
    """

    name = "diet_plan"
    description = """管理用户的计划餐次（按具体日期存储）。支持以下操作：
 - add_meal: 按日期添加计划餐次
 - update_meal: 更新已有餐次（菜品/备注等）
 - delete_meal: 删除餐次
 - copy_meal: 复制餐次到指定日期
 - get_by_week: 获取某周范围内的计划餐次"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "add_meal",
                    "update_meal",
                    "delete_meal",
                    "copy_meal",
                    "get_by_week",
                ],
                "description": "操作类型：add_meal/update_meal/delete_meal/copy_meal/get_by_week",
            },
            "user_id": {
                "type": "string",
                "description": "用户 ID，必须传入",
            },
            "week_start_date": {
                "type": "string",
                "description": "周开始日期 YYYY-MM-DD（周一，仅用于 get_by_week）",
            },
            "meal_id": {
                "type": "string",
                "description": "计划餐次 ID（用于 update_meal/delete_meal/copy_meal）",
            },
            "plan_date": {
                "type": "string",
                "description": "计划日期 YYYY-MM-DD（用于 add_meal）",
            },
            "meal_type": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snack"],
                "description": "餐次类型（用于 add_meal）",
            },
            "dishes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "菜品名称"},
                        "weight_g": {"type": "number", "description": "重量(克)"},
                        "calories": {"type": "integer", "description": "卡路里"},
                        "protein": {"type": "number", "description": "蛋白质(克)"},
                        "fat": {"type": "number", "description": "脂肪(克)"},
                        "carbs": {"type": "number", "description": "碳水(克)"},
                    },
                    "required": ["name"],
                },
                "description": "菜品列表（用于 add_meal/update_meal），每项必须包含 name",
            },
            "notes": {
                "type": "string",
                "description": "餐次备注",
            },
            "target_date": {
                "type": "string",
                "description": "目标日期 YYYY-MM-DD（用于 copy_meal）",
            },
            "target_meal_type": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snack"],
                "description": "目标餐次类型（用于 copy_meal，可选）",
            },
        },
        "required": ["action", "user_id"],
    }

    async def execute(
        self,
        action: str = "",
        user_id: str = "",
        week_start_date: Optional[str] = None,
        meal_id: Optional[str] = None,
        plan_date: Optional[str] = None,
        meal_type: Optional[str] = None,
        dishes: Optional[List[dict]] = None,
        notes: Optional[str] = None,
        target_date: Optional[str] = None,
        target_meal_type: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """执行饮食计划操作"""
        if not action:
            return ToolResult(success=False, error="action 参数是必需的")
        if not user_id:
            return ToolResult(success=False, error="user_id 参数是必需的")

        try:
            if action == "add_meal":
                if not plan_date:
                    return ToolResult(
                        success=False, error="add_meal 操作需要 plan_date 参数"
                    )
                if not meal_type:
                    return ToolResult(
                        success=False, error="add_meal 操作需要 meal_type 参数"
                    )

                actual_plan_date = datetime.strptime(plan_date, "%Y-%m-%d").date()
                result = await diet_service.add_meal(
                    user_id=user_id,
                    plan_date=actual_plan_date,
                    meal_type=meal_type,
                    dishes=dishes,
                    notes=notes,
                )
                return ToolResult(
                    success=True,
                    data={"message": "添加餐次成功", "meal": result},
                )

            elif action == "update_meal":
                if not meal_id:
                    return ToolResult(
                        success=False, error="update_meal 操作需要 meal_id 参数"
                    )
                update_data = {}
                if dishes is not None:
                    update_data["dishes"] = dishes
                if notes is not None:
                    update_data["notes"] = notes

                result = await diet_service.update_meal(meal_id, user_id, **update_data)
                if not result:
                    return ToolResult(success=False, error="餐次不存在或无权访问")
                return ToolResult(
                    success=True,
                    data={"message": "更新餐次成功", "meal": result},
                )

            elif action == "delete_meal":
                if not meal_id:
                    return ToolResult(
                        success=False, error="delete_meal 操作需要 meal_id 参数"
                    )
                success = await diet_service.delete_meal(meal_id, user_id)
                if not success:
                    return ToolResult(success=False, error="餐次不存在或无权访问")
                return ToolResult(
                    success=True,
                    data={"message": "删除餐次成功"},
                )

            elif action == "copy_meal":
                if not meal_id:
                    return ToolResult(
                        success=False, error="copy_meal 操作需要 meal_id 参数"
                    )
                if not target_date:
                    return ToolResult(
                        success=False,
                        error="copy_meal 操作需要 target_date 参数",
                    )

                actual_target_date = datetime.strptime(target_date, "%Y-%m-%d").date()
                result = await diet_service.copy_meal(
                    source_meal_id=meal_id,
                    user_id=user_id,
                    target_date=actual_target_date,
                    target_meal_type=target_meal_type,
                )
                if not result:
                    return ToolResult(success=False, error="餐次不存在或无权访问")
                return ToolResult(
                    success=True,
                    data={"message": "复制餐次成功", "meal": result},
                )

            elif action == "get_by_week":
                if not week_start_date:
                    return ToolResult(
                        success=False, error="get_by_week 操作需要 week_start_date 参数"
                    )
                actual_week_start = datetime.strptime(
                    week_start_date, "%Y-%m-%d"
                ).date()
                result = await diet_service.get_plan_by_week(
                    user_id=user_id,
                    week_start_date=actual_week_start,
                )
                return ToolResult(
                    success=True,
                    data={
                        "message": "获取计划餐次成功",
                        "plan": result,
                    },
                )

            else:
                return ToolResult(
                    success=False,
                    error=f"未知操作: {action}",
                )

        except Exception as e:
            logger.exception(f"DietPlanTool execution failed: {e}")
            return ToolResult(
                success=False,
                error=f"操作失败: {str(e)}",
            )


__all__ = ["DietPlanTool"]
