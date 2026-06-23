from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.llm.provider import LLMInvoker
from app.llm.structured_output import StructuredOutputError


class QueryOutput(BaseModel):
    query: str


class FakeProvider:
    def pick_model(self, llm_type=None):
        return "fake-model"


class FakeStructuredRunnable:
    def __init__(self, llm):
        self.llm = llm

    async def ainvoke(self, messages, **kwargs):
        self.llm.structured_messages.append(messages)
        self.llm.structured_kwargs.append(kwargs)
        outcome = self.llm.structured_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeLLM:
    def __init__(self, *, structured_outcomes=None, plain_outcomes=None):
        self.structured_outcomes = list(structured_outcomes or [])
        self.plain_outcomes = list(plain_outcomes or [])
        self.structured_calls = []
        self.structured_messages = []
        self.structured_kwargs = []
        self.plain_messages = []
        self.plain_kwargs = []

    def bind(self, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        self.structured_calls.append((schema, kwargs))
        return FakeStructuredRunnable(self)

    async def ainvoke(self, messages, **kwargs):
        self.plain_messages.append(messages)
        self.plain_kwargs.append(kwargs)
        outcome = self.plain_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def make_invoker(llm):
    return LLMInvoker(
        provider=FakeProvider(),
        llm_type="fast",
        base_llm=llm,
        callbacks=[],
    )


@pytest.mark.asyncio
async def test_ainvoke_json_returns_parsed_pydantic_output():
    llm = FakeLLM(
        structured_outcomes=[
            {
                "raw": SimpleNamespace(content='{"query": "红烧肉怎么做"}'),
                "parsed": QueryOutput(query="红烧肉怎么做"),
                "parsing_error": None,
            }
        ]
    )
    invoker = make_invoker(llm)

    result = await invoker.ainvoke_json([{"role": "user", "content": "rewrite"}], QueryOutput)

    assert result == QueryOutput(query="红烧肉怎么做")
    assert llm.structured_calls[0] == (
        QueryOutput,
        {"method": "json_schema", "strict": True, "include_raw": True},
    )


@pytest.mark.asyncio
async def test_ainvoke_json_uses_raw_json_fallback_when_parser_fails():
    llm = FakeLLM(
        structured_outcomes=[
            {
                "raw": SimpleNamespace(content='{"query": "番茄炒蛋做法"}\n以上是解析结果'),
                "parsed": None,
                "parsing_error": ValueError("parser failed"),
            }
        ]
    )
    invoker = make_invoker(llm)

    result = await invoker.ainvoke_json([{"role": "user", "content": "rewrite"}], QueryOutput)

    assert result == QueryOutput(query="番茄炒蛋做法")


@pytest.mark.asyncio
async def test_ainvoke_json_retries_with_error_feedback_before_degrading():
    llm = FakeLLM(
        structured_outcomes=[
            {
                "raw": SimpleNamespace(content="not json"),
                "parsed": None,
                "parsing_error": ValueError("parser failed"),
            },
            {
                "raw": SimpleNamespace(content='{"query": "青椒肉丝做法"}'),
                "parsed": QueryOutput(query="青椒肉丝做法"),
                "parsing_error": None,
            },
        ]
    )
    invoker = make_invoker(llm)

    result = await invoker.ainvoke_json([{"role": "user", "content": "rewrite"}], QueryOutput)

    assert result.query == "青椒肉丝做法"
    assert len(llm.structured_messages) == 2
    retry_messages = llm.structured_messages[1]
    assert retry_messages[-1]["role"] == "user"
    assert "上一次输出无法解析" in retry_messages[-1]["content"]
    assert "QueryOutput" in retry_messages[-1]["content"]


@pytest.mark.asyncio
async def test_ainvoke_json_degrades_to_json_object_and_raises_with_context():
    llm = FakeLLM(
        structured_outcomes=[
            {
                "raw": SimpleNamespace(content="not json"),
                "parsed": None,
                "parsing_error": ValueError("parser failed"),
            }
        ],
        plain_outcomes=[SimpleNamespace(content="still not json")],
    )
    invoker = make_invoker(llm)

    with pytest.raises(StructuredOutputError) as exc_info:
        await invoker.ainvoke_json(
            [{"role": "user", "content": "rewrite"}],
            QueryOutput,
            max_retries=0,
        )

    error = exc_info.value
    assert error.schema_name == "QueryOutput"
    assert error.raw_content == "still not json"
    assert error.degraded is True
    assert llm.plain_kwargs[0]["response_format"] == {"type": "json_object"}
