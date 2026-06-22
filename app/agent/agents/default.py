"""
DefaultAgent - 通用助手 Agent

默认的 Agent 实现，无特殊逻辑。
"""

from app.agent.agents.base import BaseAgent


class DefaultAgent(BaseAgent):
    """
    默认 Agent 实现。

    通用对话 Agent，无特殊逻辑。
    """

    pass


__all__ = ["DefaultAgent"]
