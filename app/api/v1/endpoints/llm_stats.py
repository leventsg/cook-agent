"""
LLM 使用统计 API 接口
提供 Token 使用情况、模型分布以及模块级统计指标等数据访问能力
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.database.llm_usage_repository import llm_usage_repository

router = APIRouter(prefix="/llm-stats", tags=["LLM Statistics"])


@router.get("/summary")
async def get_llm_stats_summary(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    conversation_id: Optional[str] = Query(None, description="Filter by conversation ID"),
):
    """
    获取 LLM 使用情况汇总统计。

    返回内容包括：
    - API 调用总次数
    - Token 使用总量（输入 Token、输出 Token、总 Token）
    - 平均每次调用消耗的 Token 数
    - 平均响应耗时

    查询参数：
        start_date:
            按开始日期过滤（ISO 格式，例如："2024-01-01"）

        end_date:
            按结束日期过滤（ISO 格式，例如："2024-01-31"）

        conversation_id:
            按指定会话进行过滤
    """
    user_id = getattr(request.state, "user_id", None)

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    summary = await llm_usage_repository.get_summary(
        user_id=user_id,
        start_date=start_dt,
        end_date=end_dt,
        conversation_id=conversation_id,
    )

    return summary


@router.get("/time-series")
async def get_llm_stats_time_series(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    granularity: str = Query("day", regex="^(day|hour)$", description="Grouping granularity"),
    module_name: Optional[str] = Query(None, description="Filter by module name"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
):
    """
    获取 LLM 使用趋势数据。

    返回 LLM 使用指标的时间序列数据，按天或小时进行分组。

    查询参数：
        days:
            查看的天数（1-90天）
        granularity:
            分组粒度（"day" 或 "hour"）
        module_name:
            按指定模块进行过滤
        model_name:
            按指定模型进行过滤
    """
    user_id = getattr(request.state, "user_id", None)

    time_series = await llm_usage_repository.get_time_series(
        days=days,
        granularity=granularity,
        user_id=user_id,
        module_name=module_name,
        model_name=model_name,
    )

    return {
        "period_days": days,
        "granularity": granularity,
        "data_points": len(time_series),
        "time_series": time_series,
    }


@router.get("/distribution/by-module")
async def get_distribution_by_module(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
):
    """
    获取 LLM 使用按模块分布的数据。

    返回每个模块的 API 调用次数和 Token 使用量。

    查询参数：
        start_date:
            按开始日期过滤（ISO 格式，例如："2024-01-01"）
        end_date:
            按结束日期过滤（ISO 格式，例如："2024-01-31"）
    """
    user_id = getattr(request.state, "user_id", None)

    # Parse dates
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    distribution = await llm_usage_repository.get_distribution_by_module(
        user_id=user_id,
        start_date=start_dt,
        end_date=end_dt,
    )

    return {
        "distribution": distribution,
        "count": len(distribution),
    }


@router.get("/distribution/by-model")
async def get_distribution_by_model(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
):
    """
    获取 LLM 使用按模型分布的数据。

    返回每个模型的 API 调用次数和 Token 使用量。

    查询参数：
        start_date:
            按开始日期过滤（ISO 格式，例如："2024-01-01"）
        end_date:
            按结束日期过滤（ISO 格式，例如："2024-01-31"）
    """
    user_id = getattr(request.state, "user_id", None)

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    distribution = await llm_usage_repository.get_distribution_by_model(
        user_id=user_id,
        start_date=start_dt,
        end_date=end_dt,
    )

    return {
        "distribution": distribution,
        "count": len(distribution),
    }


@router.get("/conversation/{conversation_id}")
async def get_conversation_llm_stats(
    request: Request,
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    """
    获取特定会话的 LLM 使用详情。

    返回该会话对应的 LLM 使用记录列表，包括 token 数量、使用的模型和时间信息。
    """
    logs = await llm_usage_repository.get_by_conversation(
        conversation_id=conversation_id,
        limit=limit,
    )

    total_input_tokens = sum(log.get("input_tokens") or 0 for log in logs)
    total_output_tokens = sum(log.get("output_tokens") or 0 for log in logs)
    total_tokens = sum(log.get("total_tokens") or 0 for log in logs)

    return {
        "conversation_id": conversation_id,
        "count": len(logs),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "logs": logs,
    }


@router.get("/modules")
async def get_available_modules():
    """
    获取已记录 LLM 使用情况的可用模块名称列表。

    返回使用日志中唯一的模块名称列表。
    """
    modules = await llm_usage_repository.get_distinct_modules()

    return {
        "modules": modules,
        "count": len(modules),
    }


@router.get("/models")
async def get_available_models():
    """
    获取已使用的可用模型名称列表。

    返回使用日志中唯一的模型名称列表。
    """
    models = await llm_usage_repository.get_distinct_models()

    return {
        "models": models,
        "count": len(models),
    }


@router.get("/tools")
async def get_available_tools():
    """
    获取已使用的可用工具名称列表。

    返回使用日志中唯一的工具名称列表。
    """
    tools = await llm_usage_repository.get_distinct_tools()

    return {
        "tools": tools,
        "count": len(tools),
    }


@router.get("/distribution/by-tool")
async def get_distribution_by_tool(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    module_name: Optional[str] = Query(None, description="Filter by module name"),
):
    """
    获取 LLM 使用情况按工具分布。

    返回每个工具的 API 调用次数和 Token 使用量。

    查询参数：
        start_date: 按开始日期过滤（ISO 格式，例如："2024-01-01"）
        end_date: 按结束日期过滤（ISO 格式，例如："2024-01-31"）
        model_name: 按特定模型过滤
        module_name: 按特定模块过滤
    """
    user_id = getattr(request.state, "user_id", None)

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    distribution = await llm_usage_repository.get_distribution_by_tool(
        user_id=user_id,
        start_date=start_dt,
        end_date=end_dt,
        model_name=model_name,
        module_name=module_name,
    )

    return {
        "distribution": distribution,
        "count": len(distribution),
    }


@router.get("/time-series/tools")
async def get_tool_time_series(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    granularity: str = Query("day", regex="^(day|hour)$", description="Grouping granularity"),
    model_name: Optional[str] = Query(None, description="Filter by model name"),
    module_name: Optional[str] = Query(None, description="Filter by module name"),
):
    """
    获取工具使用趋势。

    返回工具使用指标的时间序列数据，按天或小时分组。

    查询参数：
        days: 查看的天数（1-90）
        granularity: 分组粒度（"day"或"hour"）
        model_name: 按特定模型过滤
        module_name: 按特定模块过滤
    """
    user_id = getattr(request.state, "user_id", None)

    time_series = await llm_usage_repository.get_tool_time_series(
        days=days,
        granularity=granularity,
        user_id=user_id,
        model_name=model_name,
        module_name=module_name,
    )

    return {
        "period_days": days,
        "granularity": granularity,
        "data_points": len(time_series),
        "time_series": time_series,
    }
