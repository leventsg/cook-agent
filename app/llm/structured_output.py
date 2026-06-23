"""结构化 LLM JSON 输出的辅助函数。"""
from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from app.utils.structured_json import extract_first_valid_json

ModelT = TypeVar("ModelT", bound=BaseModel)


class StructuredOutputError(Exception):
    """当结构化的 LLM 输出解析失败或数据校验失败时抛出该异常。"""

    def __init__(
        self,
        *,
        schema_name: str,
        raw_content: str,
        parsing_error: Exception | None,
        degraded: bool,
    ):
        self.schema_name = schema_name
        self.raw_content = raw_content
        self.parsing_error = parsing_error
        self.degraded = degraded
        super().__init__(
            f"Failed to parse structured output for {schema_name}"
            f" (degraded={degraded}): {parsing_error}"
        )


def raw_content_from_message(raw: object) -> str:
    """从 LangChain 消息类对象提取文本内容。"""
    content = getattr(raw, "content", raw)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def validate_structured_output(
    schema: Type[ModelT],
    parsed: object | None,
    raw_content: str,
) -> ModelT:
    """验证解析结果；若无法直接通过校验，则尝试从原始文本中提取 JSON 并重新解析"""
    if parsed is not None:
        if isinstance(parsed, schema):
            return parsed
        return schema.model_validate(parsed)

    extracted = extract_first_valid_json(raw_content)
    return schema.model_validate(extracted)
