"""
饮食模块业务服务层

提供饮食计划和记录的业务逻辑处理。
"""

import logging
from datetime import date, timedelta
from typing import List, Optional

from app.diet.database.repository import diet_repository, DietRepository
from app.diet.database.models import (
    MealType,
    DataSource,
)
from app.diet.prompts import (
    DIET_LOG_IMAGE_PROMPT_TEMPLATE,
    DIET_LOG_TEXT_PROMPT_TEMPLATE,
    DIET_LOG_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def get_week_start_date(target_date: date) -> date:
    """获取给定日期所在周的周一日期"""
    return target_date - timedelta(days=target_date.weekday())


class DietService:
    """饮食模块业务服务"""

    def __init__(self, repository: Optional[DietRepository] = None):
        self.repository = repository or diet_repository

    async def _build_plan_response(
        self,
        user_id: str,
        week_start_date: date,
        meals: Optional[List] = None,
    ) -> dict:
        if meals is None:
            meals = await self.repository.get_plan_meals_by_week(user_id, week_start_date)

        return {
            "user_id": user_id,
            "week_start_date": week_start_date.isoformat(),
            "meals": [meal.to_dict() for meal in meals],
        }

    @staticmethod
    def _group_items_by_log_id(items: List[dict]) -> dict:
        grouped: dict[str, List[dict]] = {}
        for item in items:
            log_id = item["log_id"]
            grouped.setdefault(log_id, []).append(item)
        return grouped

    @staticmethod
    def _build_log_dict(items: List[dict]) -> dict:
        if not items:
            return {}
        first = items[0]
        total_calories = sum(i.get("calories") or 0 for i in items)
        total_protein = sum(i.get("protein") or 0 for i in items)
        total_fat = sum(i.get("fat") or 0 for i in items)
        total_carbs = sum(i.get("carbs") or 0 for i in items)
        timestamps: List[str] = [
            str(value)
            for value in (i.get("created_at") for i in items)
            if value
        ]
        created_at = min(timestamps) if timestamps else None
        updated_at = max(timestamps) if timestamps else None
        return {
            "id": first["log_id"],
            "user_id": first["user_id"],
            "log_date": first["log_date"],
            "meal_type": first["meal_type"],
            "plan_meal_id": first.get("plan_meal_id"),
            "total_calories": total_calories or None,
            "total_protein": total_protein or None,
            "total_fat": total_fat or None,
            "total_carbs": total_carbs or None,
            "notes": first.get("notes"),
            "items": [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"user_id", "log_date", "meal_type", "notes", "plan_meal_id"}
                }
                for item in items
            ],
            "created_at": created_at,
            "updated_at": updated_at,
        }

    # ==================== 计划餐次 ====================

    async def get_plan_by_week(
        self, user_id: str, week_start_date: date
    ) -> Optional[dict]:
        """获取指定周的计划"""
        meals = await self.repository.get_plan_meals_by_week(user_id, week_start_date)
        if not meals:
            return None
        return await self._build_plan_response(
            user_id=user_id,
            week_start_date=week_start_date,
            meals=meals,
        )

    # ==================== 餐次管理 ====================

    async def add_meal(
        self,
        user_id: str,
        plan_date: date,
        meal_type: str,
        dishes: Optional[list] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict]:
        """添加餐次到计划"""
        # 计算总营养
        total_calories = 0
        total_protein = 0
        total_fat = 0
        total_carbs = 0

        if dishes:
            for dish in dishes:
                total_calories += dish.get("calories", 0) or 0
                total_protein += dish.get("protein", 0) or 0
                total_fat += dish.get("fat", 0) or 0
                total_carbs += dish.get("carbs", 0) or 0

        meal = await self.repository.add_meal_to_plan(
            user_id=user_id,
            plan_date=plan_date,
            meal_type=meal_type,
            dishes=dishes,
            total_calories=total_calories or None,
            total_protein=total_protein or None,
            total_fat=total_fat or None,
            total_carbs=total_carbs or None,
            notes=notes,
        )

        return meal.to_dict()

    async def update_meal(
        self,
        meal_id: str,
        user_id: str,
        **kwargs,
    ) -> Optional[dict]:
        """更新餐次"""
        # 获取餐次并验证所有权
        meal = await self.repository.get_meal(meal_id)
        if not meal:
            return None

        if meal.user_id != user_id:
            return None

        # 如果更新了 dishes，重新计算总营养
        if "dishes" in kwargs and kwargs["dishes"]:
            dishes = kwargs["dishes"]
            kwargs["total_calories"] = (
                sum(d.get("calories", 0) or 0 for d in dishes) or None
            )
            kwargs["total_protein"] = (
                sum(d.get("protein", 0) or 0 for d in dishes) or None
            )
            kwargs["total_fat"] = sum(d.get("fat", 0) or 0 for d in dishes) or None
            kwargs["total_carbs"] = sum(d.get("carbs", 0) or 0 for d in dishes) or None

        updated_meal = await self.repository.update_meal(meal_id, **kwargs)
        return updated_meal.to_dict() if updated_meal else None

    async def delete_meal(self, meal_id: str, user_id: str) -> bool:
        """删除餐次"""
        # 获取餐次并验证所有权
        meal = await self.repository.get_meal(meal_id)
        if not meal:
            return False

        if meal.user_id != user_id:
            return False

        return await self.repository.delete_meal(meal_id)

    async def copy_meal(
        self,
        source_meal_id: str,
        user_id: str,
        target_date: date,
        target_meal_type: Optional[str] = None,
    ) -> Optional[dict]:
        """复制餐次到另一天"""
        # 获取源餐次并验证所有权
        meal = await self.repository.get_meal(source_meal_id)
        if not meal:
            return None

        if meal.user_id != user_id:
            return None

        new_meal = await self.repository.copy_meal(
            source_meal_id=source_meal_id,
            target_date=target_date,
            target_meal_type=target_meal_type,
        )

        return new_meal.to_dict() if new_meal else None

    # ==================== 记录管理 ====================

    async def log_meal(
        self,
        user_id: str,
        log_date: date,
        meal_type: str,
        items: Optional[List[dict]] = None,
        plan_meal_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """记录一餐饮食"""
        normalized_items = items or [
            {
                "food_name": "未记录食物",
                "source": DataSource.MANUAL.value,
            }
        ]
        created_items = await self.repository.create_log_items(
            user_id=user_id,
            log_date=log_date,
            meal_type=meal_type,
            items=normalized_items,
            notes=notes,
            plan_meal_id=plan_meal_id,
        )

        items_dict = [
            {
                **item.to_dict(),
                "user_id": item.user_id,
                "log_date": item.log_date.isoformat(),
                "meal_type": item.meal_type,
                "notes": item.notes,
                "plan_meal_id": str(item.plan_meal_id) if item.plan_meal_id else None,
            }
            for item in created_items
        ]
        return self._build_log_dict(items_dict)

    async def log_from_text(
        self,
        user_id: str,
        text: str,
        log_date: Optional[date] = None,
        meal_type: Optional[str] = None,
        images: Optional[list] = None,
    ) -> dict:
        """从文字或图片描述记录饮食（AI 解析）

        示例输入：
        - "今天中午吃了牛肉面和一个苹果"
        - "早餐：两个鸡蛋、一杯牛奶"
        """
        import json
        from app.config import settings
        from app.llm.provider import LLMProvider

        provider = LLMProvider(settings.llm)
        invoker = provider.create_invoker(llm_type="fast")

        def parse_ai_json(content: str) -> dict:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            return json.loads(content.strip())

        parsed = None
        used_vision = False

        if images:
            try:
                from app.vision.provider import vision_provider, ImageInput

                if vision_provider.is_enabled:
                    image_inputs = [
                        ImageInput.from_base64(
                            img.get("data", ""),
                            img.get("mime_type") or "image/jpeg",
                        )
                        for img in images
                        if img.get("data")
                    ]
                    if image_inputs:
                        extra_text = f"，以及用户补充描述：{text}" if text else ""
                        vision_prompt = DIET_LOG_IMAGE_PROMPT_TEMPLATE.format(
                            extra_text=extra_text
                        )

                        response = await vision_provider.analyze(
                            text=vision_prompt,
                            images=image_inputs,
                            user_id=user_id,
                            conversation_id=None,
                        )
                        parsed = parse_ai_json(response)
                        used_vision = True
            except Exception as e:
                logger.warning(f"Failed to parse diet images: {e}")

        # AI 解析食物
        prompt = DIET_LOG_TEXT_PROMPT_TEMPLATE.format(text=text)

        try:
            if parsed is None:
                response = await invoker.ainvoke(
                    [
                        {
                            "role": "system",
                            "content": DIET_LOG_SYSTEM_PROMPT,
                        },
                        {"role": "user", "content": prompt},
                    ]
                )
                parsed = parse_ai_json(response.content)

            # 使用解析结果
            actual_meal_type = (
                meal_type or parsed.get("meal_type") or MealType.SNACK.value
            )
            items = parsed.get("items", [])

            # 标记来源为 AI 解析
            for item in items:
                item["source"] = (
                    DataSource.AI_IMAGE.value if used_vision else DataSource.AI_TEXT.value
                )

            return await self.log_meal(
                user_id=user_id,
                log_date=log_date or date.today(),
                meal_type=actual_meal_type,
                items=items,
            )

        except Exception as e:
            logger.error(f"Failed to parse diet text: {e}")
            # 降级处理：创建简单记录
            return await self.log_meal(
                user_id=user_id,
                log_date=log_date or date.today(),
                meal_type=meal_type or MealType.SNACK.value,
                items=[
                    {
                        "food_name": text[:100],  # 使用原始文本作为名称
                        "source": DataSource.AI_TEXT.value,
                    }
                ],
                notes=f"AI 解析失败，原始描述：{text}",
            )

    async def mark_plan_meal_as_eaten(
        self,
        plan_meal_id: str,
        user_id: str,
        log_date: Optional[date] = None,
    ) -> Optional[dict]:
        """将计划中的餐次标记为已吃"""
        # 获取计划餐次
        meal = await self.repository.get_meal(plan_meal_id)
        if not meal:
            return None

        if meal.user_id != user_id:
            return None

        # 确定日期
        actual_date = log_date or date.today()

        # 从计划餐次创建记录
        items = []
        if meal.dishes:
            for dish in meal.dishes:
                items.append(
                    {
                        "food_name": dish.get("name", "Unknown"),
                        "weight_g": dish.get("weight_g"),
                        "unit": dish.get("unit"),
                        "calories": dish.get("calories"),
                        "protein": dish.get("protein"),
                        "fat": dish.get("fat"),
                        "carbs": dish.get("carbs"),
                        "source": DataSource.MANUAL.value,
                    }
                )

        return await self.log_meal(
            user_id=user_id,
            log_date=actual_date,
            meal_type=meal.meal_type,
            items=items,
            plan_meal_id=plan_meal_id,
        )

    async def get_log(self, log_id: str) -> Optional[dict]:
        """获取记录详情"""
        items = await self.repository.get_log_items_by_log_id(log_id)
        if not items:
            return None
        items_dict = [
            {
                **item.to_dict(),
                "user_id": item.user_id,
                "log_date": item.log_date.isoformat(),
                "meal_type": item.meal_type,
                "notes": item.notes,
                "plan_meal_id": str(item.plan_meal_id) if item.plan_meal_id else None,
            }
            for item in items
        ]
        return self._build_log_dict(items_dict)

    async def get_logs_by_date(self, user_id: str, log_date: date) -> List[dict]:
        """获取某天的所有记录"""
        items = await self.repository.get_log_items_by_date(user_id, log_date)
        items_dict = [
            {
                **item.to_dict(),
                "user_id": item.user_id,
                "log_date": item.log_date.isoformat(),
                "meal_type": item.meal_type,
                "notes": item.notes,
                "plan_meal_id": str(item.plan_meal_id) if item.plan_meal_id else None,
            }
            for item in items
        ]
        grouped = self._group_items_by_log_id(items_dict)
        logs = [self._build_log_dict(group) for group in grouped.values()]
        return sorted(logs, key=lambda log: (log.get("meal_type"), log.get("log_date")))

    async def update_log(
        self,
        log_id: str,
        user_id: str,
        items: Optional[List[dict]] = None,
        meal_type: Optional[str] = None,
        log_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> Optional[dict]:
        """更新记录"""
        existing_items = await self.repository.get_log_items_by_log_id(log_id)
        if not existing_items or existing_items[0].user_id != user_id:
            return None

        existing = existing_items[0]
        actual_log_date = log_date or existing.log_date
        actual_meal_type = meal_type or existing.meal_type
        actual_notes = notes if notes is not None else existing.notes
        plan_meal_id = str(existing.plan_meal_id) if existing.plan_meal_id else None

        if items is not None:
            await self.repository.delete_log_items(log_id)
            await self.repository.create_log_items(
                user_id=user_id,
                log_date=actual_log_date,
                meal_type=actual_meal_type,
                items=items,
                notes=actual_notes,
                plan_meal_id=plan_meal_id,
                log_id=existing.log_id,
            )
        else:
            await self.repository.update_log_metadata(
                log_id,
                meal_type=meal_type,
                log_date=log_date,
                notes=notes,
            )

        return await self.get_log(log_id)

    async def delete_log(self, log_id: str, user_id: str) -> bool:
        """删除记录"""
        items = await self.repository.get_log_items_by_log_id(log_id)
        if not items or items[0].user_id != user_id:
            return False

        return await self.repository.delete_log_items(log_id)

    async def add_item_to_log(
        self,
        log_id: str,
        user_id: str,
        food_name: str,
        **kwargs,
    ) -> Optional[dict]:
        """添加食品项到记录"""
        items = await self.repository.get_log_items_by_log_id(log_id)
        if not items or items[0].user_id != user_id:
            return None

        item = await self.repository.add_item_to_log(
            log_id=log_id,
            food_name=food_name,
            **kwargs,
        )
        return item.to_dict() if item else None

    # ==================== 分析统计 ====================

    async def get_daily_summary(self, user_id: str, target_date: date) -> dict:
        """获取某天的饮食摘要"""
        return await self.repository.get_daily_summary(user_id, target_date)

    async def get_weekly_summary(
        self, user_id: str, week_start_date: Optional[date] = None
    ) -> dict:
        """获取某周的饮食摘要"""
        if not week_start_date:
            week_start_date = get_week_start_date(date.today())
        return await self.repository.get_weekly_summary(user_id, week_start_date)

    async def get_deviation_analysis(
        self, user_id: str, week_start_date: Optional[date] = None
    ) -> dict:
        """获取计划与实际的偏差分析"""
        if not week_start_date:
            week_start_date = get_week_start_date(date.today())
        return await self.repository.calculate_plan_vs_actual_deviation(
            user_id, week_start_date
        )

    # ==================== 用户偏好 ====================

    async def get_user_preference(self, user_id: str) -> Optional[dict]:
        """获取用户偏好"""
        pref = await self.repository.get_user_preference(user_id)
        return pref.to_dict() if pref else None

    async def update_user_preference(self, user_id: str, **kwargs) -> dict:
        """更新用户偏好"""
        update_data = dict(kwargs)
        if "disliked_foods" in update_data and "avoided_foods" not in update_data:
            update_data["avoided_foods"] = update_data.pop("disliked_foods")
        else:
            update_data.pop("disliked_foods", None)
        pref = await self.repository.upsert_user_preference(user_id, **update_data)
        return pref.to_dict()


# 单例
diet_service = DietService()
