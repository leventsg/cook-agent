# app/diet/tools/__init__.py
"""
饮食模块 Agent 工具

提供饮食计划和记录的 CRUD 工具，用于 Agent 对话式操作。
"""

from app.diet.tools.diet_plan_tool import DietPlanTool
from app.diet.tools.diet_log_tool import DietLogTool
from app.diet.tools.diet_analysis_tool import DietAnalysisTool
from app.agent.registry import AgentHub


def register_diet_tools():
    """注册所有饮食相关工具到 AgentHub。"""
    AgentHub.register_tool(DietPlanTool(), provider="local")
    AgentHub.register_tool(DietLogTool(), provider="local")
    AgentHub.register_tool(DietAnalysisTool(), provider="local")


__all__ = [
    "DietPlanTool",
    "DietLogTool",
    "DietAnalysisTool",
    "register_diet_tools",
]
