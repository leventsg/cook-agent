"""Agent 模块提示词."""

from app.agent.prompts.default import DEFAULT_AGENT_SYSTEM_PROMPT
from app.agent.prompts.context import USER_ID_PROMPT_TEMPLATE
from app.agent.prompts.compression import (
    COMPRESS_SYSTEM_PROMPT,
    COMPRESS_USER_PROMPT_TEMPLATE,
)
from app.agent.prompts.vision import VISION_ANALYSIS_PROMPT_TEMPLATE

__all__ = [
    "DEFAULT_AGENT_SYSTEM_PROMPT",
    "USER_ID_PROMPT_TEMPLATE",
    "COMPRESS_SYSTEM_PROMPT",
    "COMPRESS_USER_PROMPT_TEMPLATE",
    "VISION_ANALYSIS_PROMPT_TEMPLATE",
]
