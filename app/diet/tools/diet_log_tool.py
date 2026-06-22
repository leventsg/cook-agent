# app/diet/tools/diet_log_tool.py
"""
饮食记录管理 Tool

提供饮食记录的 CRUD 操作，供 Agent 调用。
"""

import logging
from datetime import date, datetime
from typing import Optional, List

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.diet.service import diet_service

logger = logging.getLogger(__name__)


class DietLogTool(BaseTool):
    """
    饮食记录管理工具。

    支持创建、查看、更新、删除饮食记录。
    特别支持通过自然语言描述记录饮食。
    """

    name = "diet_log"
    description = """记录和管理用户的实际饮食记录。支持以下操作：
- log: 手动记录一餐（显式食物列表）
- log_from_text: 用自然语言描述并由 AI 解析
- mark_eaten: 将计划餐次标记为已吃并生成记录
- get: 获取指定记录详情
- get_by_date: 获取某天的所有记录
- update: 更新记录内容（食物列表/餐次/日期/备注）
- delete: 删除记录
- add_item: 向已有记录追加食物"""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "log",
                    "log_from_text",
                    "mark_eaten",
                    "get",
                    "get_by_date",
                    "update",
                    "delete",
                    "add_item",
                ],
                "description": "操作类型：log/log_from_text/mark_eaten/get/get_by_date/update/delete/add_item",
            },
            "user_id": {
                "type": "string",
                "description": "用户 ID，必须传入",
            },
            "log_id": {
                "type": "string",
                "description": "记录 ID（用于 get/update/delete/add_item）",
            },
            "meal_id": {
                "type": "string",
                "description": "计划餐次 ID（用于 mark_eaten）",
            },
            "log_date": {
                "type": "string",
                "description": "记录日期 YYYY-MM-DD（用于 log/get_by_date/update/mark_eaten，可不传默认今天）",
            },
            "meal_type": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snack"],
                "description": "餐次类型（用于 log/update）",
            },
            "text": {
                "type": "string",
                "description": "自然语言饮食描述（用于 log_from_text），例如：'今天中午吃了牛肉面和一个苹果'",
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "food_name": {"type": "string", "description": "食物名称（中文）"},
                        "weight_g": {"type": "number", "description": "重量(克)，可为空"},
                        "unit": {"type": "string", "description": "计量单位，例如 份/个/碗"},
                        "calories": {"type": "integer", "description": "卡路里，数字"},
                        "protein": {"type": "number", "description": "蛋白质(克)"},
                        "fat": {"type": "number", "description": "脂肪(克)"},
                        "carbs": {"type": "number", "description": "碳水(克)"},
                    },
                    "required": ["food_name"],
                },
                "description": "食物列表（用于 log/update），多种食物需拆分为多个 items",
            },
            "food_name": {
                "type": "string",
                "description": "食物名称（用于 add_item）",
            },
            "weight_g": {
                "type": "number",
                "description": "重量(克)，可为空",
            },
            "unit": {
                "type": "string",
                "description": "单位，例如 份/个/碗",
            },
            "calories": {
                "type": "integer",
                "description": "卡路里，数字",
            },
            "protein": {
                "type": "number",
                "description": "蛋白质(克)，数字",
            },
            "fat": {
                "type": "number",
                "description": "脂肪(克)，数字",
            },
            "carbs": {
                "type": "number",
                "description": "碳水(克)，数字",
            },
            "notes": {
                "type": "string",
                "description": "记录备注",
            },
        },
        "required": ["action", "user_id"],
    }

    async def execute(
        self,
        action: str = "",
        user_id: str = "",
        log_id: Optional[str] = None,
        meal_id: Optional[str] = None,
        log_date: Optional[str] = None,
        meal_type: Optional[str] = None,
        text: Optional[str] = None,
        items: Optional[List[dict]] = None,
        food_name: Optional[str] = None,
        weight_g: Optional[float] = None,
        unit: Optional[str] = None,
        calories: Optional[int] = None,
        protein: Optional[float] = None,
        fat: Optional[float] = None,
        carbs: Optional[float] = None,
        notes: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """
        执行饮食记录操作：
        - log: 手动记录一餐（显式食物列表）
        - log_from_text: 用自然语言描述并由 AI 解析
        - mark_eaten: 将计划餐次标记为已吃并生成记录
        - get: 获取指定记录详情
        - get_by_date: 获取某天的所有记录
        - update: 更新记录内容（食物列表/餐次/日期/备注）
        - delete: 删除记录
        - add_item: 向已有记录追加食物
        """
        if not action:
            return ToolResult(success=False, error="action 参数是必需的")
        if not user_id:
            return ToolResult(success=False, error="user_id 参数是必需的")

        try:
            if action == "log":
                if not log_date:
                    # 默认今天
                    actual_date = date.today()
                else:
                    actual_date = datetime.strptime(log_date, "%Y-%m-%d").date()

                if not meal_type:
                    return ToolResult(
                        success=False, error="log 操作需要 meal_type 参数"
                    )

                result = await diet_service.log_meal(
                    user_id=user_id,
                    log_date=actual_date,
                    meal_type=meal_type,
                    items=items,
                    notes=notes,
                )
                return ToolResult(
                    success=True,
                    data={"message": "记录饮食成功", "log": result},
                )

            elif action == "log_from_text":
                if not text:
                    return ToolResult(
                        success=False, error="log_from_text 操作需要 text 参数"
                    )

                actual_date = None
                if log_date:
                    actual_date = datetime.strptime(log_date, "%Y-%m-%d").date()

                result = await diet_service.log_from_text(
                    user_id=user_id,
                    text=text,
                    log_date=actual_date,
                    meal_type=meal_type,
                )
                return ToolResult(
                    success=True,
                    data={
                        "message": "AI 解析并记录饮食成功",
                        "log": result,
                    },
                )

            elif action == "mark_eaten":
                if not meal_id:
                    return ToolResult(
                        success=False, error="mark_eaten 操作需要 meal_id 参数"
                    )

                actual_date = None
                if log_date:
                    actual_date = datetime.strptime(log_date, "%Y-%m-%d").date()

                result = await diet_service.mark_plan_meal_as_eaten(
                    plan_meal_id=meal_id,
                    user_id=user_id,
                    log_date=actual_date,
                )
                if not result:
                    return ToolResult(success=False, error="餐次不存在或无权访问")
                return ToolResult(
                    success=True,
                    data={"message": "标记为已吃成功", "log": result},
                )

            elif action == "get":
                if not log_id:
                    return ToolResult(success=False, error="get 操作需要 log_id 参数")

                result = await diet_service.get_log(log_id)
                if not result:
                    return ToolResult(success=False, error="记录不存在")
                if result.get("user_id") != user_id:
                    return ToolResult(success=False, error="无权访问此记录")
                return ToolResult(
                    success=True,
                    data={"message": "获取记录成功", "log": result},
                )

            elif action == "get_by_date":
                if not log_date:
                    actual_date = date.today()
                else:
                    actual_date = datetime.strptime(log_date, "%Y-%m-%d").date()

                results = await diet_service.get_logs_by_date(user_id, actual_date)
                return ToolResult(
                    success=True,
                    data={
                        "message": f"获取 {actual_date.isoformat()} 的饮食记录成功",
                        "date": actual_date.isoformat(),
                        "logs": results,
                        "count": len(results),
                    },
                )

            elif action == "update":
                if not log_id:
                    return ToolResult(
                        success=False, error="update 操作需要 log_id 参数"
                    )

                actual_date = None
                if log_date:
                    actual_date = datetime.strptime(log_date, "%Y-%m-%d").date()

                result = await diet_service.update_log(
                    log_id,
                    user_id,
                    items=items,
                    meal_type=meal_type,
                    log_date=actual_date,
                    notes=notes,
                )
                if not result:
                    return ToolResult(success=False, error="记录不存在或无权访问")
                return ToolResult(
                    success=True,
                    data={"message": "更新记录成功", "log": result},
                )

            elif action == "delete":
                if not log_id:
                    return ToolResult(
                        success=False, error="delete 操作需要 log_id 参数"
                    )

                success = await diet_service.delete_log(log_id, user_id)
                if not success:
                    return ToolResult(success=False, error="记录不存在或无权访问")
                return ToolResult(
                    success=True,
                    data={"message": "删除记录成功"},
                )

            elif action == "add_item":
                if not log_id:
                    return ToolResult(
                        success=False, error="add_item 操作需要 log_id 参数"
                    )
                if not food_name:
                    return ToolResult(
                        success=False, error="add_item 操作需要 food_name 参数"
                    )

                result = await diet_service.add_item_to_log(
                    log_id=log_id,
                    user_id=user_id,
                    food_name=food_name,
                    weight_g=weight_g,
                    unit=unit,
                    calories=calories,
                    protein=protein,
                    fat=fat,
                    carbs=carbs,
                )
                if not result:
                    return ToolResult(success=False, error="记录不存在或无权访问")
                return ToolResult(
                    success=True,
                    data={"message": "添加食物成功", "item": result},
                )

            else:
                return ToolResult(
                    success=False,
                    error=f"未知操作: {action}",
                )

        except Exception as e:
            logger.exception(f"DietLogTool execution failed: {e}")
            return ToolResult(
                success=False,
                error=f"操作失败: {str(e)}",
            )


__all__ = ["DietLogTool"]
