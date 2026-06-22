import json
import uuid
from types import SimpleNamespace

import pytest

from app.agent.service import AgentService
from app.agent.types import (
    AgentChunk,
    AgentChunkType,
    AgentContext,
    ToolCallInfo,
    ToolResultInfo,
    TraceStep,
)


class FakeRepository:
    def __init__(self):
        self.session_id = uuid.uuid4()
        self.saved_messages = []

    async def get_or_create_session(self, session_id, user_id):
        return SimpleNamespace(id=self.session_id, title=None)

    async def save_message(self, session_id, role, content, **kwargs):
        message = {
            "session_id": session_id,
            "role": role,
            "content": content,
            **kwargs,
        }
        self.saved_messages.append(message)
        return SimpleNamespace(**message)


class FakeContextBuilder:
    async def build(self, *args, **kwargs):
        return AgentContext(
            system_prompt="test",
            current_message="call tools",
            available_tools=[{"function": {"name": "tool_a"}}],
        )


class FakeAgent:
    async def run(self, invoker, context):
        yield AgentChunk(
            AgentChunkType.TOOL_CALL,
            ToolCallInfo(id="call_a", name="tool_a", arguments={"x": 1}),
        )
        yield AgentChunk(
            AgentChunkType.TOOL_RESULT,
            ToolResultInfo(
                tool_call_id="call_a",
                name="tool_a",
                success=True,
                result={"value": "a"},
            ),
        )
        yield AgentChunk(
            AgentChunkType.TOOL_CALL,
            ToolCallInfo(id="call_b", name="tool_b", arguments={"y": 2}),
        )
        yield AgentChunk(
            AgentChunkType.TOOL_RESULT,
            ToolResultInfo(
                tool_call_id="call_b",
                name="tool_b",
                success=True,
                result={"value": "b"},
            ),
        )
        yield AgentChunk(
            AgentChunkType.TRACE,
            TraceStep(
                iteration=0,
                action="tool_call",
                tool_calls=[
                    {"name": "tool_a", "arguments": {"x": 1}},
                    {"name": "tool_b", "arguments": {"y": 2}},
                ],
            ),
        )
        yield AgentChunk(AgentChunkType.DONE, {"iterations": 1})


class FakeProvider:
    def __init__(self, config):
        pass

    def create_invoker(self, **kwargs):
        return object()


@pytest.mark.asyncio
async def test_chat_saves_same_llm_tool_calls_in_one_assistant_message(monkeypatch):
    monkeypatch.setattr("app.llm.provider.LLMProvider", FakeProvider)
    monkeypatch.setattr(
        "app.agent.service.AgentHub.get_agent",
        staticmethod(lambda agent_name: FakeAgent()),
    )

    repository = FakeRepository()
    service = AgentService(repository=repository)
    service.context_builder = FakeContextBuilder()
    service.context_compressor = SimpleNamespace(
        maybe_compress=lambda *args, **kwargs: _noop()
    )

    async for _ in service.chat(
        session_id=None,
        user_id="user-1",
        message="call tools",
        streaming=False,
    ):
        pass

    saved = repository.saved_messages
    assert [message["role"] for message in saved] == [
        "user",
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]

    tool_call_message = saved[1]
    assert tool_call_message["content"] == ""
    assert [tc["id"] for tc in tool_call_message["tool_calls"]] == ["call_a", "call_b"]
    assert [
        json.loads(tc["function"]["arguments"])
        for tc in tool_call_message["tool_calls"]
    ] == [{"x": 1}, {"y": 2}]
    assert saved[2]["tool_call_id"] == "call_a"
    assert saved[3]["tool_call_id"] == "call_b"


async def _noop():
    return None
