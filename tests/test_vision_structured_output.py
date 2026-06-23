from types import SimpleNamespace

import pytest

from app.vision.agent import (
    VisionAgent,
    VisionAnalysisOutput,
    VisionIntent,
)
from app.vision.provider import ImageInput, VisionProvider


class FakeInvoker:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def ainvoke_json(self, messages, schema, **kwargs):
        self.calls.append((messages, schema, kwargs))
        if self.error:
            raise self.error
        return self.result


class FakeLLMProvider:
    def get_profile(self, llm_type):
        return SimpleNamespace(api_key="key", model_names=["vision-model"])


def make_vision_provider(invoker):
    provider = VisionProvider.__new__(VisionProvider)
    provider._provider = FakeLLMProvider()
    provider._invoker = invoker
    provider._callbacks = []
    return provider


@pytest.mark.asyncio
async def test_vision_provider_analyze_json_uses_invoker_schema():
    output = VisionAnalysisOutput(
        is_food_related=True,
        intent="dish_identification",
        description="一碗牛肉面",
        extracted_info={"dish_name": "牛肉面"},
        direct_response=None,
        confidence=0.9,
    )
    invoker = FakeInvoker(result=output)
    provider = make_vision_provider(invoker)

    result = await provider.analyze_json(
        text="识别图片",
        images=[ImageInput.from_url("https://example.com/a.jpg")],
        schema=VisionAnalysisOutput,
        user_id="user-1",
        conversation_id="conv-1",
    )

    assert result is output
    assert invoker.calls[0][1] is VisionAnalysisOutput


class FakeVisionProviderForAgent:
    is_enabled = True

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def analyze_json(self, text, images, schema, **kwargs):
        self.calls.append((text, images, schema, kwargs))
        if self.error:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_vision_agent_maps_structured_output_to_result():
    output = VisionAnalysisOutput(
        is_food_related=True,
        intent="recipe_request",
        description="图片里是番茄炒蛋",
        extracted_info={"dish_name": "番茄炒蛋"},
        direct_response=None,
        confidence=0.88,
    )
    provider = FakeVisionProviderForAgent(result=output)
    agent = VisionAgent(provider=provider)

    result = await agent.analyze(
        images=[ImageInput.from_url("https://example.com/a.jpg")],
        user_query="怎么做",
    )

    assert result.is_food_related is True
    assert result.intent is VisionIntent.RECIPE_REQUEST
    assert result.description == "图片里是番茄炒蛋"
    assert result.extracted_info == {"dish_name": "番茄炒蛋"}
    assert result.raw_response == output.model_dump_json()
    assert provider.calls[0][2] is VisionAnalysisOutput


@pytest.mark.asyncio
async def test_vision_agent_returns_error_result_when_structured_output_fails():
    agent = VisionAgent(
        provider=FakeVisionProviderForAgent(error=ValueError("bad json"))
    )

    result = await agent.analyze(
        images=[ImageInput.from_url("https://example.com/a.jpg")],
        user_query="这是什么",
    )

    assert result.is_food_related is False
    assert result.intent is VisionIntent.UNCLEAR
    assert "分析图片时遇到问题" in (result.direct_response or "")
