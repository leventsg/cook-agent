import pytest

from app.rag.pipeline.metadata_filter import (
    MetadataFilterExtractor,
    MetadataFilterOutput,
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
async def test_metadata_filter_uses_structured_output_for_expression():
    FakeProvider.invoker = FakeInvoker(
        result=MetadataFilterOutput(expr='category == "素菜"')
    )
    extractor = MetadataFilterExtractor(provider=FakeProvider())

    result = await extractor.build_filter_expression(
        query="推荐素菜",
        metadata_catalog={
            "Global Recipes": {
                "category": ["素菜"],
                "dish_name": ["皮蛋豆腐"],
                "difficulty": ["简单"],
            }
        },
    )

    assert result == 'category == "素菜"'
    assert FakeProvider.invoker.calls[0][1] is MetadataFilterOutput


@pytest.mark.asyncio
async def test_metadata_filter_returns_none_for_none_expression():
    FakeProvider.invoker = FakeInvoker(result=MetadataFilterOutput(expr="NONE"))
    extractor = MetadataFilterExtractor(provider=FakeProvider())

    result = await extractor.build_filter_expression(
        query="随便推荐",
        metadata_catalog={"Global Recipes": {"category": ["素菜"]}},
    )

    assert result is None


@pytest.mark.asyncio
async def test_metadata_filter_returns_none_when_structured_output_fails():
    FakeProvider.invoker = FakeInvoker(error=ValueError("bad json"))
    extractor = MetadataFilterExtractor(provider=FakeProvider())

    result = await extractor.build_filter_expression(
        query="推荐素菜",
        metadata_catalog={"Global Recipes": {"category": ["素菜"]}},
    )

    assert result is None
