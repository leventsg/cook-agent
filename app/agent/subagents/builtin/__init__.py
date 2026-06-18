# app/agent/subagents/builtin/__init__.py
"""
内置 Subagent 模块

包含所有内置的 Subagent 实现。
"""

from app.agent.subagents.builtin.generic import GenericSubagent
from app.agent.subagents.builtin.diet_planner import DietPlannerSubagent

__all__ = [
    "GenericSubagent",
    "DietPlannerSubagent",
]
