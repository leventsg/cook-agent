import pytest

from app.conversation.intent import (
    IntentDetectionOutput,
    IntentDetector,
    QueryIntent,
)


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


class FakeProvider:
    invoker = None

    def create_invoker(self, *args, **kwargs):
        return self.__class__.invoker


@pytest.mark.asyncio
async def test_intent_detector_uses_structured_output():
    invoker = FakeInvoker(
        result=IntentDetectionOutput(
            need_rag=True,
            intent="recipe_search",
            reason="用户询问具体做法",
        )
    )
    FakeProvider.invoker = invoker

    detector = IntentDetector(provider=FakeProvider())
    result = await detector.detect(history_text="用户：红烧肉怎么做")

    assert result.need_rag is True
    assert result.intent is QueryIntent.RECIPE_SEARCH
    assert result.reason == "用户询问具体做法"
    assert result.raw == {
        "need_rag": True,
        "intent": "recipe_search",
        "reason": "用户询问具体做法",
    }
    assert invoker.calls[0][1] is IntentDetectionOutput


@pytest.mark.asyncio
async def test_intent_detector_defaults_to_non_rag_when_structured_output_fails():
    FakeProvider.invoker = FakeInvoker(error=ValueError("bad json"))

    detector = IntentDetector(provider=FakeProvider())
    result = await detector.detect(history_text="用户：红烧肉怎么做")

    assert result.need_rag is False
    assert result.intent is QueryIntent.GENERAL_CHAT
    assert result.reason == "Detection failed, using default"
    assert result.raw == {}
