"""
饮食管理 API 接口
提供饮食计划、餐食记录、饮食日志以及饮食分析等 RESTful API
"""
import base64
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, field_validator

from app.diet.service import diet_service
from app.diet.database.models import MealType, DayOfWeek, DataSource

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_IMAGE_SIZE_MB = 10.0
SUPPORTED_IMAGE_FORMATS = ["image/jpeg", "image/png", "image/gif", "image/webp"]


# ==================== Request/Response Models ====================


class DishSchema(BaseModel):
    """Schema for a dish in a meal."""

    name: str = Field(..., description="菜品名称")
    weight_g: Optional[float] = Field(None, description="重量(克)")
    unit: Optional[str] = Field(None, description="单位（份/个/碗等）")
    calories: Optional[int] = Field(None, description="卡路里")
    protein: Optional[float] = Field(None, description="蛋白质(克)")
    fat: Optional[float] = Field(None, description="脂肪(克)")
    carbs: Optional[float] = Field(None, description="碳水化合物(克)")


class AddMealRequest(BaseModel):
    """Request for adding a meal to a weekly plan."""

    plan_date: date = Field(..., description="计划日期 (YYYY-MM-DD)")
    meal_type: str = Field(..., description="餐次类型: breakfast/lunch/dinner/snack")
    dishes: Optional[List[DishSchema]] = Field(None, description="菜品列表")
    notes: Optional[str] = Field(None, description="备注")


class UpdateMealRequest(BaseModel):
    """Request for updating a meal."""

    dishes: Optional[List[DishSchema]] = None
    notes: Optional[str] = None


class CopyMealRequest(BaseModel):
    """Request for copying a meal."""

    target_date: date = Field(..., description="目标日期 (YYYY-MM-DD)")
    target_meal_type: Optional[str] = Field(None, description="目标餐次类型")


class FoodItemSchema(BaseModel):
    """Schema for a food item in a log."""

    food_name: str = Field(..., description="食物名称")
    weight_g: Optional[float] = Field(None, description="重量(克)")
    unit: Optional[str] = Field(None, description="单位")
    calories: Optional[int] = Field(None, description="卡路里")
    protein: Optional[float] = Field(None, description="蛋白质(克)")
    fat: Optional[float] = Field(None, description="脂肪(克)")
    carbs: Optional[float] = Field(None, description="碳水化合物(克)")
    source: Optional[str] = Field(None, description="数据来源")


class CreateLogRequest(BaseModel):
    """Request for creating a diet log."""

    log_date: date = Field(..., description="记录日期")
    meal_type: str = Field(..., description="餐次类型")
    items: Optional[List[FoodItemSchema]] = Field(None, description="食物列表")
    plan_meal_id: Optional[str] = Field(None, description="关联的计划餐次ID")
    notes: Optional[str] = Field(None, description="备注")


class ImageData(BaseModel):
    """Image data for multimodal diet logging."""

    data: str
    mime_type: str = "image/jpeg"

    @field_validator("mime_type")
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        if v not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(
                f"不支持的图片格式: {v}。支持的格式: {SUPPORTED_IMAGE_FORMATS}"
            )
        return v

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: str) -> str:
        try:
            decoded_size = len(base64.b64decode(v))
            max_size = MAX_IMAGE_SIZE_MB * 1024 * 1024
            if decoded_size > max_size:
                raise ValueError(f"图片大小超过限制 ({MAX_IMAGE_SIZE_MB}MB)")
        except Exception as e:
            if "图片大小超过限制" in str(e):
                raise
            raise ValueError("无效的 base64 图片数据")
        return v


class LogFromTextRequest(BaseModel):
    """Request for creating a log from text description."""

    text: str = Field(..., min_length=1, max_length=1000, description="饮食描述文字")
    images: Optional[List[ImageData]] = Field(default=None, max_length=4)
    log_date: Optional[date] = Field(None, description="记录日期（默认今天）")
    meal_type: Optional[str] = Field(None, description="餐次类型（可自动推断）")


class UpdateLogRequest(BaseModel):
    """Request for updating a diet log."""

    log_date: Optional[date] = Field(None, description="记录日期")
    meal_type: Optional[str] = Field(None, description="餐次类型")
    items: Optional[List[FoodItemSchema]] = Field(None, description="食物列表")
    notes: Optional[str] = Field(None, description="备注")


class AddItemToLogRequest(BaseModel):
    """Request for adding an item to a log."""

    food_name: str = Field(..., description="食物名称")
    weight_g: Optional[float] = None
    unit: Optional[str] = None
    calories: Optional[int] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    carbs: Optional[float] = None
    source: Optional[str] = None


class MarkMealEatenRequest(BaseModel):
    """Request for marking a plan meal as eaten."""

    log_date: Optional[date] = Field(None, description="记录日期（默认今天）")


class UpdatePreferenceRequest(BaseModel):
    """Request for updating user preferences."""

    dietary_restrictions: Optional[List[str]] = Field(None, description="饮食限制")
    allergies: Optional[List[str]] = Field(None, description="过敏原")
    favorite_cuisines: Optional[List[str]] = Field(None, description="喜爱的菜系")
    avoided_foods: Optional[List[str]] = Field(None, description="不喜欢的食物")
    disliked_foods: Optional[List[str]] = Field(None, description="不喜欢的食物（兼容字段）")
    preferred_foods: Optional[List[str]] = Field(None, description="偏好的食物")
    calorie_goal: Optional[int] = Field(None, description="每日卡路里目标")
    protein_goal: Optional[float] = Field(None, description="每日蛋白质目标(克)")
    fat_goal: Optional[float] = Field(None, description="每日脂肪目标(克)")
    carbs_goal: Optional[float] = Field(None, description="每日碳水目标(克)")


# ==================== Helper Functions ====================


def get_user_id(request: Request) -> str:
    """从请求中提取用户ID"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="需要登录")
    return str(user_id)


# ==================== Plan Endpoints ====================


@router.get("/diet/plans/by-week")
async def get_plan_by_week(
    request: Request,
    week_start_date: date = Query(..., description="周开始日期（周一）"),
) -> Dict[str, Any]:
    """
    根据周开始日期获取每周计划的餐次

    返回所选周的计划餐次
    """
    user_id = get_user_id(request)
    plan = await diet_service.get_plan_by_week(user_id, week_start_date)

    if not plan:
        return {"plan": None}

    return {"plan": plan}


# ==================== Meal Endpoints ====================


@router.post("/diet/plans/meals", status_code=201)
async def add_meal(payload: AddMealRequest, request: Request) -> Dict[str, Any]:
    """
    向每周计划中添加餐次
    """
    user_id = get_user_id(request)

    dishes = None
    if payload.dishes:
        dishes = [dish.model_dump() for dish in payload.dishes]

    meal = await diet_service.add_meal(
        user_id=user_id,
        plan_date=payload.plan_date,
        meal_type=payload.meal_type,
        dishes=dishes,
        notes=payload.notes,
    )

    if not meal:
        raise HTTPException(status_code=404, detail="餐次创建失败")

    return meal


@router.patch("/diet/meals/{meal_id}")
async def update_meal(
    meal_id: str, payload: UpdateMealRequest, request: Request
) -> Dict[str, Any]:
    """
    更新餐次
    """
    user_id = get_user_id(request)

    update_data = {}
    if payload.dishes is not None:
        update_data["dishes"] = [dish.model_dump() for dish in payload.dishes]
    if payload.notes is not None:
        update_data["notes"] = payload.notes

    meal = await diet_service.update_meal(meal_id, user_id, **update_data)

    if not meal:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return meal


@router.delete("/diet/meals/{meal_id}")
async def delete_meal(meal_id: str, request: Request) -> Dict[str, str]:
    """
    删除餐次
    """
    user_id = get_user_id(request)

    success = await diet_service.delete_meal(meal_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return {"message": "餐次已删除"}


@router.post("/diet/meals/{meal_id}/copy")
async def copy_meal(
    meal_id: str, payload: CopyMealRequest, request: Request
) -> Dict[str, Any]:
    """
    复制餐次到新的日期和/或餐次类型
    """
    user_id = get_user_id(request)

    meal = await diet_service.copy_meal(
        source_meal_id=meal_id,
        user_id=user_id,
        target_date=payload.target_date,
        target_meal_type=payload.target_meal_type,
    )

    if not meal:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return meal


@router.post("/diet/meals/{meal_id}/mark-eaten")
async def mark_meal_eaten(
    meal_id: str, payload: MarkMealEatenRequest, request: Request
) -> Dict[str, Any]:
    """
    将计划餐次标记为已吃。

    根据计划餐次创建日志条目。
    """
    user_id = get_user_id(request)

    log = await diet_service.mark_plan_meal_as_eaten(
        plan_meal_id=meal_id,
        user_id=user_id,
        log_date=payload.log_date,
    )

    if not log:
        raise HTTPException(status_code=404, detail="餐次不存在或无权访问")

    return log


# ==================== Log Endpoints ====================


@router.get("/diet/logs")
async def get_logs_by_date(
    request: Request,
    log_date: date = Query(..., description="查询日期"),
) -> Dict[str, Any]:
    """
    根据特定日期获取饮食记录。
    """
    user_id = get_user_id(request)
    logs = await diet_service.get_logs_by_date(user_id, log_date)
    return {"logs": logs, "date": log_date.isoformat()}


@router.post("/diet/logs", status_code=201)
async def create_log(payload: CreateLogRequest, request: Request) -> Dict[str, Any]:
    """
    创建饮食记录
    """
    user_id = get_user_id(request)

    items = None
    if payload.items:
        items = [item.model_dump() for item in payload.items]

    log = await diet_service.log_meal(
        user_id=user_id,
        log_date=payload.log_date,
        meal_type=payload.meal_type,
        items=items,
        plan_meal_id=payload.plan_meal_id,
        notes=payload.notes,
    )

    return log


@router.post("/diet/logs/from-text", status_code=201)
async def create_log_from_text(
    payload: LogFromTextRequest, request: Request
) -> Dict[str, Any]:
    """
    根据文本描述创建饮食记录。

    使用 AI 解析文本并提取食物项目及其估算的营养成分。
    """
    user_id = get_user_id(request)

    images = None
    if payload.images:
        images = [img.model_dump() for img in payload.images]

    log = await diet_service.log_from_text(
        user_id=user_id,
        text=payload.text,
        log_date=payload.log_date,
        meal_type=payload.meal_type,
        images=images,
    )

    return log


@router.get("/diet/logs/{log_id}")
async def get_log(log_id: str, request: Request) -> Dict[str, Any]:
    """
    根据 ID 获取饮食记录。
    """
    user_id = get_user_id(request)
    log = await diet_service.get_log(log_id)

    if not log:
        raise HTTPException(status_code=404, detail="记录不存在")

    if log.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="无权访问此记录")

    return log


@router.patch("/diet/logs/{log_id}")
async def update_log(
    log_id: str, payload: UpdateLogRequest, request: Request
) -> Dict[str, Any]:
    """
    更新饮食记录。
    """
    user_id = get_user_id(request)

    items = None
    if payload.items is not None:
        items = [item.model_dump() for item in payload.items]

    log = await diet_service.update_log(
        log_id,
        user_id,
        items=items,
        meal_type=payload.meal_type,
        log_date=payload.log_date,
        notes=payload.notes,
    )

    if not log:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")

    return log


@router.delete("/diet/logs/{log_id}")
async def delete_log(log_id: str, request: Request) -> Dict[str, str]:
    """
    删除饮食记录。
    """
    user_id = get_user_id(request)

    success = await diet_service.delete_log(log_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")

    return {"message": "记录已删除"}


@router.post("/diet/logs/{log_id}/items", status_code=201)
async def add_item_to_log(
    log_id: str, payload: AddItemToLogRequest, request: Request
) -> Dict[str, Any]:
    """
    向现有记录中添加食物项目
    """
    user_id = get_user_id(request)

    item = await diet_service.add_item_to_log(
        log_id=log_id,
        user_id=user_id,
        food_name=payload.food_name,
        weight_g=payload.weight_g,
        unit=payload.unit,
        calories=payload.calories,
        protein=payload.protein,
        fat=payload.fat,
        carbs=payload.carbs,
        source=payload.source,
    )

    if not item:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")

    return item


# ==================== Analysis Endpoints ====================


@router.get("/diet/analysis/daily")
async def get_daily_summary(
    request: Request,
    target_date: date = Query(..., description="目标日期"),
) -> Dict[str, Any]:
    """
    获取每日饮食总结

    返回每日的营养总和和按餐次分类的详情。
    """
    user_id = get_user_id(request)
    summary = await diet_service.get_daily_summary(user_id, target_date)
    return summary


@router.get("/diet/analysis/weekly")
async def get_weekly_summary(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
) -> Dict[str, Any]:
    """
    获取每周饮食总结

    返回一周内的营养汇总数据。
    """
    user_id = get_user_id(request)
    summary = await diet_service.get_weekly_summary(user_id, week_start_date)
    return summary


@router.get("/diet/analysis/deviation")
async def get_deviation_analysis(
    request: Request,
    week_start_date: Optional[date] = Query(None, description="周开始日期（默认本周）"),
) -> Dict[str, Any]:
    """
    获取计划与实际饮食的偏差分析

    比较计划餐次与实际饮食记录。
    """
    user_id = get_user_id(request)
    analysis = await diet_service.get_deviation_analysis(user_id, week_start_date)
    return analysis


# ==================== Preference Endpoints ====================


@router.get("/diet/preferences")
async def get_preferences(request: Request) -> Dict[str, Any]:
    """
    获取用户的饮食偏好。
    """
    user_id = get_user_id(request)
    pref = await diet_service.get_user_preference(user_id)

    if not pref:
        return {"message": "暂无偏好设置", "preference": None}

    return {"preference": pref}


@router.put("/diet/preferences")
async def update_preferences(
    payload: UpdatePreferenceRequest, request: Request
) -> Dict[str, Any]:
    """
    更新用户的饮食偏好。
    """
    user_id = get_user_id(request)

    update_data = payload.model_dump(exclude_unset=True)
    pref = await diet_service.update_user_preference(user_id, **update_data)

    return {"preference": pref}


# ==================== Enum Info Endpoints ====================


@router.get("/diet/enums")
async def get_enums() -> Dict[str, Any]:
    """
    获取餐次的可用枚举值。

    用于前端填充下拉列表。
    """
    return {
        "meal_types": [{"value": t.value, "label": t.name} for t in MealType],
        "days_of_week": [{"value": d.value, "label": d.name} for d in DayOfWeek],
        "data_sources": [{"value": s.value, "label": s.name} for s in DataSource],
    }
