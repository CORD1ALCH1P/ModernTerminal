import pytest

from app.ai.base import ChatMessage, Done, TextDelta, ToolCall, ToolCallRequested
from app.tests.fake_ai_provider import FakeProvider


async def test_fake_provider_replays_scripted_text_turn():
    provider = FakeProvider([[TextDelta("hi"), TextDelta(" there"), Done("stop")]])

    events = [event async for event in provider.stream_chat([ChatMessage(role="user", content="hello")], [])]

    assert events == [TextDelta("hi"), TextDelta(" there"), Done("stop")]
    assert len(provider.calls) == 1


async def test_fake_provider_replays_scripted_tool_call_turn():
    call = ToolCall(name="read_terminal_scrollback", arguments={"max_bytes": 100})
    provider = FakeProvider([[ToolCallRequested([call]), Done("tool_calls")]])

    events = [event async for event in provider.stream_chat([], [])]

    assert events[0] == ToolCallRequested([call])
    assert events[1] == Done("tool_calls")
    assert call.id  # auto-generated bookkeeping id is present


async def test_fake_provider_raises_when_script_exhausted():
    provider = FakeProvider([])
    with pytest.raises(AssertionError, match="more times than scripted"):
        async for _ in provider.stream_chat([], []):
            pass
