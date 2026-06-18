# app/agent/tools/common/calculator.py
"""
计算器 Tool

支持基本的数学运算。
"""

import logging

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


class CalculatorTool(BaseTool):
    """
    计算器 Tool。

    支持基本的数学运算。
    """

    name = "calculator"
    description = "执行数学计算，支持常见函数与表达式。"
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "数学表达式，例如 '2 + 3 * 4' 或 'math.sqrt(16)'",
            }
        },
        "required": ["expression"],
    }

    async def execute(self, expression: str = "", **kwargs) -> ToolResult:
        """执行数学计算。"""
        if not expression:
            return ToolResult(success=False, error="Expression is required")

        try:
            # 安全的数学运算环境
            import math

            safe_dict = {
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum,
                "pow": pow,
                "math": math,
            }

            result = eval(expression, {"__builtins__": {}}, safe_dict)

            return ToolResult(
                success=True, data={"expression": expression, "result": result}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Calculation failed: {str(e)}")


__all__ = ["CalculatorTool"]
