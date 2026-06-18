"""
日期时间 Tool

获取当前日期时间或进行日期计算。
"""

import logging

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult

logger = logging.getLogger(__name__)


class DateTimeTool(BaseTool):
    """
    日期时间 Tool。

    获取当前日期时间信息。
    """

    name = "datetime"
    description = "获取当前日期时间信息，支持指定时区与格式化输出。"
    parameters = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "日期时间格式（strftime），例如 '%Y-%m-%d %H:%M:%S'",
                "default": "%Y-%m-%d %H:%M:%S",
            },
            "timezone": {
                "type": "string",
                "description": "时区名称（IANA），例如 'Asia/Shanghai'，默认 UTC",
                "default": "UTC",
            },
        },
        "required": [],
    }

    async def execute(
        self, format: str = "%Y-%m-%d %H:%M:%S", timezone: str = "UTC", **kwargs
    ) -> ToolResult:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            # 1. 解析时区
            try:
                tz = ZoneInfo(timezone)
            except Exception:
                return ToolResult(success=False, error=f"Invalid timezone: {timezone}")

            # 2. 获取带时区的当前时间
            now = datetime.now(tz=tz)

            # 3. 格式化
            formatted = now.strftime(format)

            return ToolResult(
                success=True,
                data={
                    "datetime": formatted,
                    "timestamp": now.timestamp(),
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "weekday": now.strftime("%A"),
                    "timezone": timezone,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to get datetime: {str(e)}")


__all__ = ["DateTimeTool"]
