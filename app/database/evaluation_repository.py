"""
RAG 评测数据访问存储层。
负责 RAGEvaluationModel 的增删改查（CRUD）操作。
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_

from app.database.models import RAGEvaluationModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)

class EvaluationRepository:
    """
    RAG 评测数据访问存储层。
    提供 RAG 评测记录的创建、更新和查询等操作方法。
    """
    async def create(
        self,
        message_id: str,
        conversation_id: str,
        query: str,
        context: str,
        response: str,
        rewritten_query: Optional[str] = None,
        user_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> RAGEvaluationModel:
        """
        创建一个新的 RAG 评测记录，状态为 pending。

        Args:
            message_id: 评测对应的消息 ID
            conversation_id: 会话 ID
            query: 用户原始查询
            context: 生成上下文
            response: 生成响应内容
            rewritten_query: 重写后的查询
            user_id: 用户 ID 
            created_at: 创建时间，默认当前时间

        Returns:
            RAGEvaluationModel: 创建的 RAG RAGEvaluationModel 实例
        """
        async with get_session_context() as session:
            evaluation = RAGEvaluationModel(
                id=uuid.uuid4(),
                message_id=uuid.UUID(message_id),
                conversation_id=uuid.UUID(conversation_id),
                user_id=user_id,
                query=query,
                rewritten_query=rewritten_query,
                context=context,
                response=response,
                evaluation_status="pending",
                created_at=created_at or datetime.utcnow(),
            )
            session.add(evaluation)
            await session.commit()
            await session.refresh(evaluation)

            logger.info(
                "创建 RAG 评测记录: id=%s message_id=%s",
                evaluation.id,
                message_id,
            )
            return evaluation
        
    async def update_results(
        self,
        evaluation_id: str,
        results: Dict[str, float],
        duration_ms: int,
        status: str = "completed",
        error_message: Optional[str] = None,
        evaluated_at: Optional[datetime] = None,
    ) -> bool:
        """
        更新 RAG 评测记录的结果。

        Args:
            evaluation_id: 评测记录 ID
            results: 评测指标分数字典，包含 faithfulness 和 answer_relevancy 键
            duration_ms: 评测耗时，毫秒为单位
            status: 评测状态(completed/failed)
            evaluated_at: 评测时间，默认当前时间

        Returns:
            True: 更新成功，否则 False
        """
        async with get_session_context() as session:
            stmt = select(RAGEvaluationModel).where(
                RAGEvaluationModel.id == uuid.UUID(evaluation_id)
            )
            result = await session.execute(stmt)
            evaluation = result.scalar_one_or_none()

            if not evaluation:
                logger.warning("未找到 RAG 评测记录 ID: %s", evaluation_id)
                return False

            # Update metrics
            evaluation.faithfulness = results.get("faithfulness")
            evaluation.answer_relevancy = results.get("answer_relevancy")

            # Update metadata
            evaluation.evaluation_status = status
            evaluation.error_message = error_message
            evaluation.evaluation_duration_ms = duration_ms
            evaluation.evaluated_at = evaluated_at or datetime.utcnow()

            await session.commit()

            logger.info(
                "更新 RAG 评测记录: id=%s status=%s duration_ms=%d",
                evaluation_id,
                status,
                duration_ms,
            )
            return True
        
    async def get_by_id(self, evaluation_id: str) -> Optional[Dict[str, Any]]:
        """根据 ID 获取 RAG 评测记录。"""
        async with get_session_context() as session:
            stmt = select(RAGEvaluationModel).where(
                RAGEvaluationModel.id == uuid.UUID(evaluation_id)
            )
            result = await session.execute(stmt)
            evaluation = result.scalar_one_or_none()

            if evaluation:
                return evaluation.to_dict()
            return None
        
    async def get_by_conversation(
        self, conversation_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """根据会话 ID 获取所有 RAG 评测记录。"""
        async with get_session_context() as session:
            stmt = (
                select(RAGEvaluationModel)
                .where(RAGEvaluationModel.conversation_id == uuid.UUID(conversation_id))
                .order_by(RAGEvaluationModel.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            evaluations = result.scalars().all()

            return [e.to_dict() for e in evaluations]
        
    async def get_statistics(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        获取 RAG 评测记录的统计信息。

        Args:
            user_id: 用户 ID 
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计信息字典
        """
        async with get_session_context() as session:
            # 构建查询条件
            conditions = [RAGEvaluationModel.evaluation_status == "completed"]

            if user_id:
                conditions.append(RAGEvaluationModel.user_id == user_id)
            if start_date:
                conditions.append(RAGEvaluationModel.created_at >= start_date)
            if end_date:
                conditions.append(RAGEvaluationModel.created_at <= end_date)

            # 聚合统计信息
            stmt = select(
                func.count(RAGEvaluationModel.id).label("total"),
                func.avg(RAGEvaluationModel.faithfulness).label("avg_faithfulness"),
                func.avg(RAGEvaluationModel.answer_relevancy).label("avg_answer_relevancy"),
                func.min(RAGEvaluationModel.faithfulness).label("min_faithfulness"),
                func.max(RAGEvaluationModel.faithfulness).label("max_faithfulness"),
                func.min(RAGEvaluationModel.answer_relevancy).label("min_answer_relevancy"),
                func.max(RAGEvaluationModel.answer_relevancy).label("max_answer_relevancy"),
                func.avg(RAGEvaluationModel.evaluation_duration_ms).label("avg_duration_ms"),
            ).where(and_(*conditions))

            result = await session.execute(stmt)
            row = result.one()

            # 统计待评测和评测失败的记录数
            status_count_stmt = select(
                func.count(RAGEvaluationModel.id)
                .filter(RAGEvaluationModel.evaluation_status == "pending")
                .label("pending_count"),
                func.count(RAGEvaluationModel.id)
                .filter(RAGEvaluationModel.evaluation_status == "failed")
                .label("failed_count"),
            )
            if conditions[1:]:
                status_count_stmt = status_count_stmt.where(and_(*conditions[1:]))
            status_count_row = (await session.execute(status_count_stmt)).one()

            return {
                "total_evaluations": row.total or 0,
                "pending_count": status_count_row.pending_count or 0,
                "failed_count": status_count_row.failed_count or 0,
                "period": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None,
                },
                "metrics": {
                    "faithfulness": {
                        "mean": float(row.avg_faithfulness) if row.avg_faithfulness else None,
                        "min": float(row.min_faithfulness) if row.min_faithfulness else None,
                        "max": float(row.max_faithfulness) if row.max_faithfulness else None,
                    },
                    "answer_relevancy": {
                        "mean": float(row.avg_answer_relevancy) if row.avg_answer_relevancy else None,
                        "min": float(row.min_answer_relevancy) if row.min_answer_relevancy else None,
                        "max": float(row.max_answer_relevancy) if row.max_answer_relevancy else None,
                    },
                },
                "avg_evaluation_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else None,
            }
        
    async def get_trends(
        self,
        days: int = 7,
        granularity: str = "day",
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取 RAG 评测记录的时间趋势。

        Args:
            days: 回溯天数
            granularity: 时间粒度
            user_id: 用户 ID

        Returns:
            时间趋势数据点列表
        """
        async with get_session_context() as session:
            start_date = datetime.utcnow() - timedelta(days=days)

            conditions = [
                RAGEvaluationModel.evaluation_status == "completed",
                RAGEvaluationModel.created_at >= start_date,
            ]
            if user_id:
                conditions.append(RAGEvaluationModel.user_id == user_id)

            # Group by date
            if granularity == "hour":
                date_trunc = func.date_trunc("hour", RAGEvaluationModel.created_at)
            else:
                date_trunc = func.date_trunc("day", RAGEvaluationModel.created_at)

            stmt = (
                select(
                    date_trunc.label("period"),
                    func.count(RAGEvaluationModel.id).label("count"),
                    func.avg(RAGEvaluationModel.faithfulness).label("avg_faithfulness"),
                    func.avg(RAGEvaluationModel.answer_relevancy).label("avg_answer_relevancy"),
                )
                .where(and_(*conditions))
                .group_by(date_trunc)
                .order_by(date_trunc)
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                {
                    "period": row.period.isoformat() if row.period else None,
                    "count": row.count,
                    "metrics": {
                        "faithfulness": float(row.avg_faithfulness) if row.avg_faithfulness else None,
                        "answer_relevancy": float(row.avg_answer_relevancy) if row.avg_answer_relevancy else None,
                    },
                }
                for row in rows
            ]
        
    async def get_alerts(
        self,
        thresholds: Dict[str, float],
        limit: int = 50,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取 RAG 评测记录中，质量指标低于阈值的记录。

        Args:
            thresholds: 质量指标阈值字典
            limit: 最大返回数量
            user_id: 用户 ID

        Returns:
            警告记录列表
        """
        async with get_session_context() as session:
            conditions = [RAGEvaluationModel.evaluation_status == "completed"]

            if user_id:
                conditions.append(RAGEvaluationModel.user_id == user_id)

            # 构建阈值违反的 OR 条件
            threshold_conditions = []
            if "faithfulness" in thresholds:
                threshold_conditions.append(
                    RAGEvaluationModel.faithfulness < thresholds["faithfulness"]
                )
            if "answer_relevancy" in thresholds:
                threshold_conditions.append(
                    RAGEvaluationModel.answer_relevancy < thresholds["answer_relevancy"]
                )

            if not threshold_conditions:
                return []

            conditions.append(or_(*threshold_conditions))

            if limit <= 0:
                limit = 50

            stmt = (
                select(RAGEvaluationModel)
                .where(and_(*conditions))
                .order_by(RAGEvaluationModel.created_at.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            evaluations = result.scalars().all()

            # 添加警告信息到每个评测记录中
            alerts = []
            for e in evaluations:
                alert_data = e.to_dict()
                alert_data["violated_thresholds"] = []

                if e.faithfulness is not None and "faithfulness" in thresholds:
                    if e.faithfulness < thresholds["faithfulness"]:
                        alert_data["violated_thresholds"].append("faithfulness")

                if e.answer_relevancy is not None and "answer_relevancy" in thresholds:
                    if e.answer_relevancy < thresholds["answer_relevancy"]:
                        alert_data["violated_thresholds"].append("answer_relevancy")

                alerts.append(alert_data)

            return alerts
        
# 单例
evaluation_repository = EvaluationRepository()