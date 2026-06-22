"""
RAG 评测指标 API 接口
提供评测统计、趋势分析以及质量告警等数据访问能力
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.config import settings
from app.database.evaluation_repository import evaluation_repository

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])


@router.get("/statistics")
async def get_evaluation_statistics(
    request: Request,
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
):
    """
    获取聚合后的评估统计信息。

    返回内容包括：
    - 评估总数
    - 平均指标得分（如 faithfulness、answer_relevancy）
    - 关键指标的最小值与最大值
    - 等待中的评估数量
    - 失败的评估数量

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

    stats = await evaluation_repository.get_statistics(
        user_id=user_id,
        start_date=start_dt,
        end_date=end_dt,
    )

    return stats


@router.get("/conversation/{conversation_id}")
async def get_conversation_evaluations(
    request: Request,
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    """
    获取指定会话的评估详情。

    返回该会话对应的评估记录列表，
    其中包含每条已评估消息的评估指标和评估状态。
    """
    evaluations = await evaluation_repository.get_by_conversation(
        conversation_id=conversation_id,
        limit=limit,
    )

    return {
        "conversation_id": conversation_id,
        "count": len(evaluations),
        "evaluations": evaluations,
    }


@router.get("/trends")
async def get_evaluation_trends(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    granularity: str = Query("day", regex="^(day|hour)$", description="Grouping granularity"),
):
    """
    获取评估指标随时间变化的趋势数据。

    返回评估指标的时间序列统计结果，可按天或按小时进行聚合。

    查询参数：
        days:
            回溯查询的天数范围（1~90）

        granularity:
            时间聚合粒度，可选值：

            - "day"：按天统计
            - "hour"：按小时统计
    """
    user_id = getattr(request.state, "user_id", None)

    trends = await evaluation_repository.get_trends(
        days=days,
        granularity=granularity,
        user_id=user_id,
    )

    return {
        "period_days": days,
        "granularity": granularity,
        "data_points": len(trends),
        "trends": trends,
    }


@router.get("/alerts")
async def get_quality_alerts(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
):
    """
    获取触发质量告警的评估记录。

    返回所有存在指标异常的评估记录，即至少有一个评估指标低于预设质量阈值。

    质量阈值由系统配置统一管理。
    """
    user_id = getattr(request.state, "user_id", None)

    thresholds = {
        "faithfulness": settings.evaluation.alert_thresholds.faithfulness,
        "answer_relevancy": settings.evaluation.alert_thresholds.answer_relevancy,
    }

    alerts = await evaluation_repository.get_alerts(
        thresholds=thresholds,
        limit=limit,
        user_id=user_id,
    )

    return {
        "thresholds": thresholds,
        "count": len(alerts),
        "alerts": alerts,
    }


@router.get("/health")
async def evaluation_health():
    """
    检查评估系统的健康状态。

    返回内容：
    - enabled：
    是否启用评估功能

    - async_mode：
    是否启用异步评估模式

    - sample_rate：
    当前评估采样率

    - configured_metrics：
    已配置的评估指标列表
    """
    return {
        "enabled": settings.evaluation.enabled,
        "async_mode": settings.evaluation.async_mode,
        "sample_rate": settings.evaluation.sample_rate,
        "configured_metrics": settings.evaluation.metrics,
        "timeout_seconds": settings.evaluation.timeout_seconds,
        "alert_thresholds": {
            "faithfulness": settings.evaluation.alert_thresholds.faithfulness,
            "answer_relevancy": settings.evaluation.alert_thresholds.answer_relevancy,
        },
    }


@router.get("/{evaluation_id}")
async def get_evaluation_detail(
    request: Request,
    evaluation_id: str,
):
    """
    获取指定评估记录的详细信息。

    返回内容包括：
    - 用户原始查询（Query）
    - 模型生成的回答（Response）
    - 检索与生成过程中使用的上下文（Context）
    - 各项评估指标得分（Metrics）
    - 评估状态、执行时间等相关信息
    """
    evaluation = await evaluation_repository.get_by_id(evaluation_id)

    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")

    return evaluation
