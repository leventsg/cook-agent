import pytest

from app.conversation.query_rewriter import QueryRewriter, QueryRewriteOutput


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

    def __init__(self, config):
        pass

    def create_invoker(self, *args, **kwargs):
        return self.__class__.invoker


@pytest.mark.asyncio
async def test_rewrite_returns_structured_query(monkeypatch):
    invoker = FakeInvoker(result=QueryRewriteOutput(query=" 西红柿炒鸡蛋怎么做 "))
    FakeProvider.invoker = invoker
    monkeypatch.setattr("app.conversation.query_rewriter.LLMProvider", FakeProvider)

    rewriter = QueryRewriter()
    result = await rewriter.rewrite(
        current_query="它怎么做",
        history_text="用户之前问过西红柿炒鸡蛋",
        user_id="user-1",
        conversation_id="conv-1",
    )

    assert result == "西红柿炒鸡蛋怎么做"
    assert invoker.calls[0][1] is QueryRewriteOutput


@pytest.mark.asyncio
async def test_rewrite_returns_current_query_when_structured_output_fails(monkeypatch):
    invoker = FakeInvoker(error=ValueError("structured output failed"))
    FakeProvider.invoker = invoker
    monkeypatch.setattr("app.conversation.query_rewriter.LLMProvider", FakeProvider)

    rewriter = QueryRewriter()
    result = await rewriter.rewrite(
        current_query="它怎么做",
        history_text="用户之前问过西红柿炒鸡蛋",
    )

    assert result == "它怎么做"
