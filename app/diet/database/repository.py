"""
饮食模块数据访问仓库

提供计划餐次、记录食品项和统计查询。
"""

import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, delete, select

from app.database.session import get_session_context
from app.diet.database.models import (
    DietLogItemModel,
    DietPlanMealModel,
    UserFoodPreferenceModel,
    DataSource,
)

class DietRepository:
    """饮食模块数据访问仓库"""

    # ==================== 计划餐次 ====================

    async def get_plan_meals_by_week(
        self, user_id: str, week_start_date: date
    ) -> List[DietPlanMealModel]:
        week_end_date = week_start_date + timedelta(days=6)
        async with get_session_context() as session:
            stmt = (
                select(DietPlanMealModel)
                .where(
                    and_(
                        DietPlanMealModel.user_id == user_id,
                        DietPlanMealModel.plan_date >= week_start_date,
                        DietPlanMealModel.plan_date <= week_end_date,
                    )
                )
                .order_by(DietPlanMealModel.plan_date, DietPlanMealModel.meal_type)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def add_meal_to_plan(
        self,
        user_id: str,
        plan_date: date,
        meal_type: str,
        dishes: Optional[list] = None,
        total_calories: Optional[float] = None,
        total_protein: Optional[float] = None,
        total_fat: Optional[float] = None,
        total_carbs: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> DietPlanMealModel:
        async with get_session_context() as session:
            meal = DietPlanMealModel(
                user_id=user_id,
                plan_date=plan_date,
                meal_type=meal_type,
                dishes=dishes,
                total_calories=total_calories,
                total_protein=total_protein,
                total_fat=total_fat,
                total_carbs=total_carbs,
                notes=notes,
            )
            session.add(meal)
            await session.flush()
            await session.refresh(meal)
            return meal

    async def get_meal(self, meal_id: str) -> Optional[DietPlanMealModel]:
        async with get_session_context() as session:
            try:
                meal_uuid = uuid.UUID(meal_id)
            except ValueError:
                return None

            stmt = select(DietPlanMealModel).where(DietPlanMealModel.id == meal_uuid)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_meal(self, meal_id: str, **kwargs) -> Optional[DietPlanMealModel]:
        async with get_session_context() as session:
            try:
                meal_uuid = uuid.UUID(meal_id)
            except ValueError:
                return None

            stmt = select(DietPlanMealModel).where(DietPlanMealModel.id == meal_uuid)
            result = await session.execute(stmt)
            meal = result.scalar_one_or_none()
            if not meal:
                return None

            for key, value in kwargs.items():
                if hasattr(meal, key):
                    setattr(meal, key, value)
            meal.updated_at = datetime.utcnow()
            await session.flush()
            await session.refresh(meal)
            return meal

    async def delete_meal(self, meal_id: str) -> bool:
        async with get_session_context() as session:
            try:
                meal_uuid = uuid.UUID(meal_id)
            except ValueError:
                return False

            stmt = delete(DietPlanMealModel).where(DietPlanMealModel.id == meal_uuid)
            await session.execute(stmt)
            return True

    async def copy_meal(
        self,
        source_meal_id: str,
        target_date: date,
        target_meal_type: Optional[str] = None,
    ) -> Optional[DietPlanMealModel]:
        async with get_session_context() as session:
            try:
                source_uuid = uuid.UUID(source_meal_id)
            except ValueError:
                return None

            stmt = select(DietPlanMealModel).where(DietPlanMealModel.id == source_uuid)
            result = await session.execute(stmt)
            meal = result.scalar_one_or_none()
            if not meal:
                return None

            new_meal = DietPlanMealModel(
                user_id=meal.user_id,
                plan_date=target_date,
                meal_type=target_meal_type or meal.meal_type,
                dishes=meal.dishes,
                total_calories=meal.total_calories,
                total_protein=meal.total_protein,
                total_fat=meal.total_fat,
                total_carbs=meal.total_carbs,
                notes=meal.notes,
            )
            session.add(new_meal)
            await session.flush()
            await session.refresh(new_meal)
            return new_meal

    # ==================== 饮食记录（食品项） ====================

    async def create_log_items(
        self,
        user_id: str,
        log_date: date,
        meal_type: str,
        items: List[dict],
        notes: Optional[str] = None,
        plan_meal_id: Optional[str] = None,
        log_id: Optional[uuid.UUID] = None,
    ) -> List[DietLogItemModel]:
        async with get_session_context() as session:
            log_uuid = log_id or uuid.uuid4()
            plan_uuid = uuid.UUID(plan_meal_id) if plan_meal_id else None
            created_items: List[DietLogItemModel] = []
            for item in items:
                log_item = DietLogItemModel(
                    log_id=log_uuid,
                    user_id=user_id,
                    log_date=log_date,
                    meal_type=meal_type,
                    plan_meal_id=plan_uuid,
                    food_name=item.get("food_name", "Unknown"),
                    weight_g=item.get("weight_g"),
                    unit=item.get("unit"),
                    calories=item.get("calories"),
                    protein=item.get("protein"),
                    fat=item.get("fat"),
                    carbs=item.get("carbs"),
                    source=item.get("source") or DataSource.MANUAL.value,
                    confidence_score=item.get("confidence_score"),
                    notes=notes,
                )
                session.add(log_item)
                created_items.append(log_item)
            await session.flush()
            for item in created_items:
                await session.refresh(item)
            return created_items

    async def get_log_items_by_log_id(self, log_id: str) -> List[DietLogItemModel]:
        async with get_session_context() as session:
            try:
                log_uuid = uuid.UUID(log_id)
            except ValueError:
                return []

            stmt = select(DietLogItemModel).where(DietLogItemModel.log_id == log_uuid)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_log_items_by_date(
        self, user_id: str, log_date: date
    ) -> List[DietLogItemModel]:
        async with get_session_context() as session:
            stmt = (
                select(DietLogItemModel)
                .where(
                    and_(
                        DietLogItemModel.user_id == user_id,
                        DietLogItemModel.log_date == log_date,
                    )
                )
                .order_by(DietLogItemModel.meal_type)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_log_items_by_date_range(
        self, user_id: str, start_date: date, end_date: date
    ) -> List[DietLogItemModel]:
        async with get_session_context() as session:
            stmt = (
                select(DietLogItemModel)
                .where(
                    and_(
                        DietLogItemModel.user_id == user_id,
                        DietLogItemModel.log_date >= start_date,
                        DietLogItemModel.log_date <= end_date,
                    )
                )
                .order_by(DietLogItemModel.log_date, DietLogItemModel.meal_type)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_log_notes(self, log_id: str, notes: Optional[str]) -> bool:
        async with get_session_context() as session:
            try:
                log_uuid = uuid.UUID(log_id)
            except ValueError:
                return False

            stmt = select(DietLogItemModel).where(DietLogItemModel.log_id == log_uuid)
            result = await session.execute(stmt)
            items = result.scalars().all()
            if not items:
                return False

            for item in items:
                item.notes = notes
            await session.flush()
            return True

    async def update_log_metadata(
        self,
        log_id: str,
        meal_type: Optional[str] = None,
        log_date: Optional[date] = None,
        notes: Optional[str] = None,
    ) -> bool:
        async with get_session_context() as session:
            try:
                log_uuid = uuid.UUID(log_id)
            except ValueError:
                return False

            stmt = select(DietLogItemModel).where(DietLogItemModel.log_id == log_uuid)
            result = await session.execute(stmt)
            items = result.scalars().all()
            if not items:
                return False

            for item in items:
                if meal_type is not None:
                    item.meal_type = meal_type
                if log_date is not None:
                    item.log_date = log_date
                if notes is not None:
                    item.notes = notes
            await session.flush()
            return True

    async def delete_log_items(self, log_id: str) -> bool:
        async with get_session_context() as session:
            try:
                log_uuid = uuid.UUID(log_id)
            except ValueError:
                return False

            stmt = delete(DietLogItemModel).where(DietLogItemModel.log_id == log_uuid)
            await session.execute(stmt)
            return True

    async def add_item_to_log(
        self,
        log_id: str,
        food_name: str,
        **kwargs,
    ) -> Optional[DietLogItemModel]:
        async with get_session_context() as session:
            try:
                log_uuid = uuid.UUID(log_id)
            except ValueError:
                return None

            stmt = select(DietLogItemModel).where(DietLogItemModel.log_id == log_uuid)
            result = await session.execute(stmt)
            items = result.scalars().all()
            if not items:
                return None

            reference = items[0]
            new_item = DietLogItemModel(
                log_id=log_uuid,
                user_id=reference.user_id,
                log_date=reference.log_date,
                meal_type=reference.meal_type,
                plan_meal_id=reference.plan_meal_id,
                notes=reference.notes,
                food_name=food_name,
                weight_g=kwargs.get("weight_g"),
                unit=kwargs.get("unit"),
                calories=kwargs.get("calories"),
                protein=kwargs.get("protein"),
                fat=kwargs.get("fat"),
                carbs=kwargs.get("carbs"),
                source=kwargs.get("source") or DataSource.MANUAL.value,
                confidence_score=kwargs.get("confidence_score"),
            )
            session.add(new_item)
            await session.flush()
            await session.refresh(new_item)
            return new_item

    # ==================== 用户偏好 ====================

    async def get_user_preference(
        self, user_id: str
    ) -> Optional[UserFoodPreferenceModel]:
        async with get_session_context() as session:
            stmt = select(UserFoodPreferenceModel).where(
                UserFoodPreferenceModel.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def upsert_user_preference(
        self,
        user_id: str,
        **kwargs,
    ) -> UserFoodPreferenceModel:
        async with get_session_context() as session:
            stmt = select(UserFoodPreferenceModel).where(
                UserFoodPreferenceModel.user_id == user_id
            )
            result = await session.execute(stmt)
            pref = result.scalar_one_or_none()

            if pref:
                for key, value in kwargs.items():
                    if hasattr(pref, key):
                        setattr(pref, key, value)
                pref.updated_at = datetime.utcnow()
            else:
                pref = UserFoodPreferenceModel(user_id=user_id, **kwargs)
                session.add(pref)

            await session.flush()
            await session.refresh(pref)
            return pref

    # ==================== 统计分析 ====================

    async def get_daily_summary(self, user_id: str, target_date: date) -> dict:
        items = await self.get_log_items_by_date(user_id, target_date)

        total_calories = sum(item.calories or 0 for item in items)
        total_protein = sum(item.protein or 0 for item in items)
        total_fat = sum(item.fat or 0 for item in items)
        total_carbs = sum(item.carbs or 0 for item in items)
        meals_logged = sorted({item.meal_type for item in items})
        log_count = len({item.log_id for item in items})

        return {
            "date": target_date.isoformat(),
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_fat": total_fat,
            "total_carbs": total_carbs,
            "meals_logged": meals_logged,
            "log_count": log_count,
        }

    async def get_weekly_summary(self, user_id: str, week_start_date: date) -> dict:
        end_date = week_start_date + timedelta(days=6)
        items = await self.get_log_items_by_date_range(user_id, week_start_date, end_date)

        daily_data = {}
        for i in range(7):
            current_date = week_start_date + timedelta(days=i)
            daily_data[current_date.isoformat()] = {
                "calories": 0,
                "protein": 0,
                "fat": 0,
                "carbs": 0,
                "meals": [],
            }

        for item in items:
            date_key = item.log_date.isoformat()
            if date_key not in daily_data:
                daily_data[date_key] = {
                    "calories": 0,
                    "protein": 0,
                    "fat": 0,
                    "carbs": 0,
                    "meals": [],
                }
            daily_data[date_key]["calories"] += item.calories or 0
            daily_data[date_key]["protein"] += item.protein or 0
            daily_data[date_key]["fat"] += item.fat or 0
            daily_data[date_key]["carbs"] += item.carbs or 0
            if item.meal_type not in daily_data[date_key]["meals"]:
                daily_data[date_key]["meals"].append(item.meal_type)

        total_calories = sum(day["calories"] for day in daily_data.values())
        total_protein = sum(day["protein"] for day in daily_data.values())
        total_fat = sum(day["fat"] for day in daily_data.values())
        total_carbs = sum(day["carbs"] for day in daily_data.values())
        avg_daily_calories = total_calories / 7 if total_calories else 0

        return {
            "week_start_date": week_start_date.isoformat(),
            "week_end_date": end_date.isoformat(),
            "daily_data": daily_data,
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_fat": total_fat,
            "total_carbs": total_carbs,
            "avg_daily_calories": avg_daily_calories,
        }

    async def calculate_plan_vs_actual_deviation(
        self, user_id: str, week_start_date: date
    ) -> dict:
        plan_meals = await self.get_plan_meals_by_week(user_id, week_start_date)
        if not plan_meals:
            return {
                "has_plan": False,
                "message": "本周暂无计划餐次",
            }

        end_date = week_start_date + timedelta(days=6)
        items = await self.get_log_items_by_date_range(user_id, week_start_date, end_date)

        plan_totals = {
            "calories": sum(m.total_calories or 0 for m in plan_meals),
            "protein": sum(m.total_protein or 0 for m in plan_meals),
            "fat": sum(m.total_fat or 0 for m in plan_meals),
            "carbs": sum(m.total_carbs or 0 for m in plan_meals),
        }
        actual_totals = {
            "calories": sum(i.calories or 0 for i in items),
            "protein": sum(i.protein or 0 for i in items),
            "fat": sum(i.fat or 0 for i in items),
            "carbs": sum(i.carbs or 0 for i in items),
        }

        actual_map = {}
        for item in items:
            key = (item.log_date.isoformat(), item.meal_type)
            if key not in actual_map:
                actual_map[key] = 0
            actual_map[key] += item.calories or 0

        meal_deviations = []
        executed_count = 0
        for meal in plan_meals:
            date_key = meal.plan_date.isoformat()
            actual = actual_map.get((date_key, meal.meal_type), 0)
            planned = meal.total_calories or 0
            deviation_value = actual - planned
            deviation_pct = (
                deviation_value / planned * 100
                if planned
                else None
            )
            if actual > 0:
                executed_count += 1
            meal_deviations.append(
                {
                    "meal_key": f"{date_key}:{meal.meal_type}",
                    "plan_calories": planned,
                    "actual_calories": actual,
                    "calories_deviation": deviation_value,
                    "calories_deviation_pct": deviation_pct,
                }
            )

        execution_rate = (
            executed_count / len(plan_meals) * 100 if plan_meals else 0
        )
        total_deviation = actual_totals["calories"] - plan_totals["calories"]
        total_deviation_pct = (
            total_deviation / plan_totals["calories"] * 100
            if plan_totals["calories"]
            else None
        )

        return {
            "has_plan": True,
            "week_start_date": week_start_date.isoformat(),
            "total_plan_calories": plan_totals["calories"],
            "total_actual_calories": actual_totals["calories"],
            "total_deviation": total_deviation,
            "total_deviation_pct": total_deviation_pct,
            "meal_deviations": meal_deviations,
            "execution_rate": execution_rate,
        }


diet_repository = DietRepository()
