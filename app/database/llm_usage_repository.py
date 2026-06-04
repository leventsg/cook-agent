"""
RAG 评测数据访问层。
提供 RAG 评测记录的创建、更新和查询等操作方法。
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, and_

from app.database.models import LLMUsageLogModel
from app.database.session import get_session_context

logger = logging.getLogger(__name__)


class LLMUsageRepository:
    """
    LLM 使用统计数据访问层。
    提供 LLM 调用日志的记录、存储以及聚合统计查询功能。
    """

    # ==================== Create Log ====================

    async def create_log(
        self,
        request_id: str,
        module_name: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        model_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> LLMUsageLogModel:
        """
        创建新的 LLM 使用统计数据条目。

        Args:
            request_id: 唯一请求标识符
            module_name: 调用 LLM 调用的模块名称
            user_id: 用户 ID
            conversation_id: 对话 ID
            model_name: 使用的 LLM 模型名称
            tool_name: 使用的工具名称
            input_tokens: 输入token数
            output_tokens: 输出token数
            total_tokens: 总token数
            duration_ms: 调用持续时间（毫秒）

        Returns:
            创建的 LLMUsageLogModel 实例
        """
        async with get_session_context() as session:
            log = LLMUsageLogModel(
                id=uuid.uuid4(),
                request_id=request_id,
                module_name=module_name,
                user_id=user_id,
                conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
                model_name=model_name,
                tool_name=tool_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
            )
            session.add(log)
            await session.commit()

            logger.debug(
                "创建LLM使用统计数据条目: module=%s, model=%s, tool=%s, tokens=%s",
                module_name,
                model_name,
                tool_name,
                total_tokens,
            )
            return log

    # ==================== Summary Statistics ====================

    async def get_summary(
        self,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        获取 LLM 使用的聚合摘要统计信息。

        Args:
            user_id: 用户id
            conversation_id: 会话id
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含统计信息的字典
        """
        async with get_session_context() as session:
            conditions = self._build_conditions(
                user_id=user_id,
                conversation_id=conversation_id,
                start_date=start_date,
                end_date=end_date,
            )

            stmt = select(
                func.count(LLMUsageLogModel.id).label("total_calls"),
                func.sum(LLMUsageLogModel.input_tokens).label("total_input_tokens"),
                func.sum(LLMUsageLogModel.output_tokens).label("total_output_tokens"),
                func.sum(LLMUsageLogModel.total_tokens).label("total_tokens"),
                func.avg(LLMUsageLogModel.total_tokens).label("avg_tokens_per_call"),
                func.avg(LLMUsageLogModel.duration_ms).label("avg_duration_ms"),
                func.min(LLMUsageLogModel.created_at).label("first_call"),
                func.max(LLMUsageLogModel.created_at).label("last_call"),
            )

            if conditions:
                stmt = stmt.where(and_(*conditions))

            result = await session.execute(stmt)
            row = result.one()

            return {
                "total_calls": row.total_calls or 0,
                "total_input_tokens": row.total_input_tokens or 0,
                "total_output_tokens": row.total_output_tokens or 0,
                "total_tokens": row.total_tokens or 0,
                "avg_tokens_per_call": float(row.avg_tokens_per_call) if row.avg_tokens_per_call else 0,
                "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0,
                "period": {
                    "start": start_date.isoformat() if start_date else (
                        row.first_call.isoformat() if row.first_call else None
                    ),
                    "end": end_date.isoformat() if end_date else (
                        row.last_call.isoformat() if row.last_call else None
                    ),
                },
            }

    # ==================== Time Series Data ====================

    async def get_time_series(
        self,
        days: int = 7,
        granularity: str = "hour",
        user_id: Optional[str] = None,
        module_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取 LLM 使用的时间序列数据。

        Args:
            days: 查看的天数
            granularity: 时间分组（"hour" 或 "day"）
            user_id: 用户id
            module_name: 模块名称
            model_name: 模型名称

        Returns:
            时间序列数据点列表
        """
        async with get_session_context() as session:
            start_date = datetime.utcnow() - timedelta(days=days)

            conditions = [LLMUsageLogModel.created_at >= start_date]
            if user_id:
                conditions.append(LLMUsageLogModel.user_id == user_id)
            if module_name:
                conditions.append(LLMUsageLogModel.module_name == module_name)
            if model_name:
                conditions.append(LLMUsageLogModel.model_name == model_name)

            # 时间分组
            if granularity == "day":
                date_trunc = func.date_trunc("day", LLMUsageLogModel.created_at)
            else:
                date_trunc = func.date_trunc("hour", LLMUsageLogModel.created_at)

            stmt = (
                select(
                    date_trunc.label("period"),
                    func.count(LLMUsageLogModel.id).label("call_count"),
                    func.sum(LLMUsageLogModel.input_tokens).label("input_tokens"),
                    func.sum(LLMUsageLogModel.output_tokens).label("output_tokens"),
                    func.sum(LLMUsageLogModel.total_tokens).label("total_tokens"),
                    func.avg(LLMUsageLogModel.duration_ms).label("avg_duration_ms"),
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
                    "call_count": row.call_count,
                    "input_tokens": row.input_tokens or 0,
                    "output_tokens": row.output_tokens or 0,
                    "total_tokens": row.total_tokens or 0,
                    "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0,
                }
                for row in rows
            ]

    # ==================== Distribution Statistics ====================

    async def get_distribution_by_module(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取按模块分组的使用分布。

        Returns:
            模块统计信息列表
        """
        async with get_session_context() as session:
            conditions = self._build_conditions(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )

            stmt = select(
                LLMUsageLogModel.module_name,
                func.count(LLMUsageLogModel.id).label("call_count"),
                func.sum(LLMUsageLogModel.total_tokens).label("total_tokens"),
                func.avg(LLMUsageLogModel.total_tokens).label("avg_tokens"),
                func.avg(LLMUsageLogModel.duration_ms).label("avg_duration_ms"),
            )

            if conditions:
                stmt = stmt.where(and_(*conditions))

            stmt = stmt.group_by(LLMUsageLogModel.module_name).order_by(
                func.sum(LLMUsageLogModel.total_tokens).desc()
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                {
                    "module_name": row.module_name,
                    "call_count": row.call_count,
                    "total_tokens": row.total_tokens or 0,
                    "avg_tokens": float(row.avg_tokens) if row.avg_tokens else 0,
                    "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0,
                }
                for row in rows
            ]

    async def get_distribution_by_model(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取按模型分组的使用分布。

        Returns:
            模型统计信息列表
        """
        async with get_session_context() as session:
            conditions = self._build_conditions(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )

            stmt = select(
                LLMUsageLogModel.model_name,
                func.count(LLMUsageLogModel.id).label("call_count"),
                func.sum(LLMUsageLogModel.total_tokens).label("total_tokens"),
                func.avg(LLMUsageLogModel.total_tokens).label("avg_tokens"),
                func.avg(LLMUsageLogModel.duration_ms).label("avg_duration_ms"),
            )

            if conditions:
                stmt = stmt.where(and_(*conditions))

            stmt = stmt.group_by(LLMUsageLogModel.model_name).order_by(
                func.sum(LLMUsageLogModel.total_tokens).desc()
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                {
                    "model_name": row.model_name or "unknown",
                    "call_count": row.call_count,
                    "total_tokens": row.total_tokens or 0,
                    "avg_tokens": float(row.avg_tokens) if row.avg_tokens else 0,
                    "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0,
                }
                for row in rows
            ]

    # ==================== Conversation Level Stats ====================

    async def get_by_conversation(
        self,
        conversation_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取特定对话的 LLM 使用日志。

        Returns:
            使用日志条目列表
        """
        async with get_session_context() as session:
            stmt = (
                select(LLMUsageLogModel)
                .where(LLMUsageLogModel.conversation_id == uuid.UUID(conversation_id))
                .order_by(LLMUsageLogModel.created_at.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            logs = result.scalars().all()

            return [self._log_to_dict(log) for log in logs]

    # ==================== Distinct Values ====================

    async def get_distinct_modules(self) -> List[str]:
        """
        获取所有已记录 LLM 使用的唯一模块名称列表。

        Returns:
            唯一模块名称列表
        """
        async with get_session_context() as session:
            stmt = (
                select(LLMUsageLogModel.module_name)
                .distinct()
                .where(LLMUsageLogModel.module_name.isnot(None))
                .order_by(LLMUsageLogModel.module_name)
            )

            result = await session.execute(stmt)
            rows = result.scalars().all()

            return list(rows)

    async def get_distinct_models(self) -> List[str]:
        """
        获取所有已使用的唯一模型名称列表。

        Returns:
            唯一模型名称列表
        """
        async with get_session_context() as session:
            stmt = (
                select(LLMUsageLogModel.model_name)
                .distinct()
                .where(LLMUsageLogModel.model_name.isnot(None))
                .order_by(LLMUsageLogModel.model_name)
            )

            result = await session.execute(stmt)
            rows = result.scalars().all()

            return list(rows) # type: ignore

    async def get_distinct_tools(self) -> List[str]:
        """
        获取所有已使用的唯一工具名称列表。

        Returns:
            唯一工具名称列表
        """
        async with get_session_context() as session:
            stmt = (
                select(LLMUsageLogModel.tool_name)
                .distinct()
                .where(LLMUsageLogModel.tool_name.isnot(None))
                .order_by(LLMUsageLogModel.tool_name)
            )

            result = await session.execute(stmt)
            rows = result.scalars().all()

            return list(rows) # type: ignore

    async def get_distribution_by_tool(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        model_name: Optional[str] = None,
        module_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取工具使用分布。

        Args:
            user_id: 用户id
            start_date: 开始日期
            end_date: 结束日期
            model_name: 模型名称
            module_name: 模块名称

        Returns:
            工具统计信息列表
        """
        async with get_session_context() as session:
            conditions = self._build_conditions(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )

            if model_name:
                conditions.append(LLMUsageLogModel.model_name == model_name)
            if module_name:
                conditions.append(LLMUsageLogModel.module_name == module_name)

            stmt = select(
                LLMUsageLogModel.tool_name,
                func.count(LLMUsageLogModel.id).label("call_count"),
                func.sum(LLMUsageLogModel.input_tokens).label("input_tokens"),
                func.sum(LLMUsageLogModel.output_tokens).label("output_tokens"),
                func.sum(LLMUsageLogModel.total_tokens).label("total_tokens"),
                func.avg(LLMUsageLogModel.total_tokens).label("avg_tokens"),
                func.avg(LLMUsageLogModel.duration_ms).label("avg_duration_ms"),
            )

            if conditions:
                stmt = stmt.where(and_(*conditions))

            stmt = stmt.group_by(LLMUsageLogModel.tool_name).order_by(
                func.sum(LLMUsageLogModel.total_tokens).desc()
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                {
                    "tool_name": row.tool_name or "no_tool",
                    "call_count": row.call_count,
                    "input_tokens": row.input_tokens or 0,
                    "output_tokens": row.output_tokens or 0,
                    "total_tokens": row.total_tokens or 0,
                    "avg_tokens": float(row.avg_tokens) if row.avg_tokens else 0,
                    "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0,
                }
                for row in rows
            ]

    async def get_tool_time_series(
        self,
        days: int = 7,
        granularity: str = "hour",
        user_id: Optional[str] = None,
        model_name: Optional[str] = None,
        module_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取工具使用时间序列数据。

        Args:
            days: 查看的天数，默认7天
            granularity: 时间分组，"hour"或"day"
            user_id: 用户id
            model_name: 模型名称
            module_name: 模块名称

        Returns:
            时间序列数据点列表
        """
        async with get_session_context() as session:
            start_date = datetime.utcnow() - timedelta(days=days)

            conditions = [LLMUsageLogModel.created_at >= start_date]
            if user_id:
                conditions.append(LLMUsageLogModel.user_id == user_id)
            if model_name:
                conditions.append(LLMUsageLogModel.model_name == model_name)
            if module_name:
                conditions.append(LLMUsageLogModel.module_name == module_name)

            # 时间分组
            if granularity == "day":
                date_trunc = func.date_trunc("day", LLMUsageLogModel.created_at)
            else:
                date_trunc = func.date_trunc("hour", LLMUsageLogModel.created_at)

            stmt = (
                select(
                    date_trunc.label("period"),
                    LLMUsageLogModel.tool_name,
                    func.count(LLMUsageLogModel.id).label("call_count"),
                    func.sum(LLMUsageLogModel.input_tokens).label("input_tokens"),
                    func.sum(LLMUsageLogModel.output_tokens).label("output_tokens"),
                    func.sum(LLMUsageLogModel.total_tokens).label("total_tokens"),
                    func.avg(LLMUsageLogModel.duration_ms).label("avg_duration_ms"),
                )
                .where(and_(*conditions))
                .group_by(date_trunc, LLMUsageLogModel.tool_name)
                .order_by(date_trunc, LLMUsageLogModel.tool_name)
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                {
                    "period": row.period.isoformat() if row.period else None,
                    "tool_name": row.tool_name or "no_tool",
                    "call_count": row.call_count,
                    "input_tokens": row.input_tokens or 0,
                    "output_tokens": row.output_tokens or 0,
                    "total_tokens": row.total_tokens or 0,
                    "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms else 0,
                }
                for row in rows
            ]

    # ==================== Helper Methods ====================

    def _log_to_dict(self, log: LLMUsageLogModel) -> Dict[str, Any]:
        """将 LLMUsageLogModel 转换为字典。"""
        return {
            "id": str(log.id),
            "request_id": log.request_id,
            "module_name": log.module_name,
            "user_id": log.user_id,
            "conversation_id": str(log.conversation_id) if log.conversation_id else None,
            "model_name": log.model_name,
            "tool_name": log.tool_name,
            "input_tokens": log.input_tokens,
            "output_tokens": log.output_tokens,
            "total_tokens": log.total_tokens,
            "duration_ms": log.duration_ms,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }

    def _build_conditions(
        self,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List:
        """构建查询条件。"""
        conditions = []

        if user_id:
            conditions.append(LLMUsageLogModel.user_id == user_id)
        if conversation_id:
            conditions.append(
                LLMUsageLogModel.conversation_id == uuid.UUID(conversation_id)
            )
        if start_date:
            conditions.append(LLMUsageLogModel.created_at >= start_date)
        if end_date:
            conditions.append(LLMUsageLogModel.created_at <= end_date)

        return conditions


# 单例
llm_usage_repository = LLMUsageRepository()