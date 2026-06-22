"""
饮食模块数据库模型

包含饮食计划目标、计划餐次、记录食品项和用户偏好数据模型。
"""

import uuid
from datetime import datetime, date
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base


class MealType(str, Enum):
    """餐次类型"""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class DayOfWeek(int, Enum):
    """星期几 (0=周一, 6=周日)"""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class DataSource(str, Enum):
    """数据来源"""

    MANUAL = "manual"
    AI_TEXT = "ai_text"
    AI_IMAGE = "ai_image"


class DietPlanMealModel(Base):
    """计划中的一餐"""

    __tablename__ = "diet_plan_meals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    dishes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    total_calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_diet_plan_meals_user_date", "user_id", "plan_date"),
        Index(
            "ix_diet_plan_meals_user_date_meal",
            "user_id",
            "plan_date",
            "meal_type",
        ),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "plan_date": self.plan_date.isoformat(),
            "meal_type": self.meal_type,
            "dishes": self.dishes or [],
            "total_calories": self.total_calories,
            "total_protein": self.total_protein,
            "total_fat": self.total_fat,
            "total_carbs": self.total_carbs,
            "notes": self.notes,
        }


class DietLogItemModel(Base):
    """饮食记录中的食品项"""

    __tablename__ = "diet_log_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    plan_meal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diet_plan_meals.id", ondelete="SET NULL"),
        nullable=True,
    )
    food_name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    calories: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), default=DataSource.MANUAL.value, nullable=False
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_diet_log_items_user_date", "user_id", "log_date"),
        Index("ix_diet_log_items_user_date_meal", "user_id", "log_date", "meal_type"),
        Index("ix_diet_log_items_log_id", "log_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "log_id": str(self.log_id),
            "food_name": self.food_name,
            "weight_g": self.weight_g,
            "unit": self.unit,
            "calories": self.calories,
            "protein": self.protein,
            "fat": self.fat,
            "carbs": self.carbs,
            "source": self.source,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
        }


class UserFoodPreferenceModel(Base):
    """用户饮食偏好（个性化学习结果）"""

    __tablename__ = "user_food_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    common_foods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    avoided_foods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    diet_tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    avg_daily_calories_min: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    avg_daily_calories_max: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    deviation_patterns: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "common_foods": self.common_foods or [],
            "avoided_foods": self.avoided_foods or [],
            "diet_tags": self.diet_tags or [],
            "avg_daily_calories_min": self.avg_daily_calories_min,
            "avg_daily_calories_max": self.avg_daily_calories_max,
            "deviation_patterns": self.deviation_patterns or [],
            "stats": self.stats or {},
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
