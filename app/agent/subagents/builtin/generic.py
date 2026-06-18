# app/agent/subagents/builtin/generic.py
"""
GenericSubagent - 通用 Subagent 实现

用于用户自定义的 Subagent，使用通用的执行逻辑。
"""

import logging
from typing import Awaitable, Callable, Optional

from app.agent.subagents.base import BaseSubagent
from app.agent.types import TraceStep
from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


class GenericSubagent(BaseSubagent):
    """
    通用 Subagent 实现。

    使用 BaseSubagent 提供的通用 run_with_tools 方法执行任务。
    适用于用户自定义的 Subagent。
    """

    async def execute(
        self,
        task: str,
        user_id: Optional[str] = None,
        background: Optional[str] = None,
        event_handler: Optional[Callable[[TraceStep], Awaitable[None]]] = None,
    ) -> ToolResult:
        """
        执行任务。

        Args:
            task: 任务描述
            user_id: 用户 ID
            background: 额外背景信息

        Returns:
            ToolResult: 执行结果
        """
        # 获取用户信息作为背景
        enriched_background = background or ""

        if user_id:
            try:
                from app.services.user_service import user_service

                user_data = await user_service.get_user_by_id(user_id)
                if user_data:
                    if user_data.profile:
                        profile_block = f"## 用户信息\n{user_data.profile}"
                        enriched_background = (
                            f"{enriched_background}\n\n{profile_block}"
                            if enriched_background
                            else profile_block
                        )
            except Exception as e:
                logger.warning(f"Failed to get user profile: {e}")

        return await self.run_with_tools(
            task=task,
            user_id=user_id,
            background=enriched_background or None,
            event_handler=event_handler,
        )


__all__ = ["GenericSubagent"]
