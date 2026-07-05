import pytest

from app.ai.base import (
    ChatMessage,
    Done,
    ModelNotFound,
    ProviderUnavailable,
    TextDelta,
    ToolCall,
    ToolCallRequested,
    ToolSpec,
)
from app.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.tests.fake_openai_server import start_fake_openai_server


async def test_plain_text_turn_accumulates_incremental_deltas():
    server = await start_fake_openai_server(
        chat_turns=[
            [
                {"choices": [{"index": 0, "delta": {"role": "assistant"}}]},
                {"choices": [{"index": 0, "delta": {"content": "Hello"}}]},
                {"choices": [{"index": 0, "delta": {"content": ", world"}}]},
                {"choices": [{"index": 0, "delta": {"content": "!"}, "finish_reason": "stop"}]},
            ]
        ],
        chunk_delay=0.01,  # force genuinely separate TCP writes, not one coalesced blob
    )
    try:
        provider = OpenAICompatibleProvider(server.base_url, model="gpt-4o-mini")
        events = [
            event
            async for event in provider.stream_chat([ChatMessage(role="user", content="hi")], [])
        ]

        text = "".join(e.text for e in events if isinstance(e, TextDelta))
        assert text == "Hello, world!"
        assert events[-1] == Done("stop")
        assert len(server.requests_received) == 1
        assert server.requests_received[0]["messages"] == [{"role": "user", "content": "hi"}]
    finally:
        await server.close()


async def test_tool_call_arguments_accumulate_across_fragments():
    server = await start_fake_openai_server(
        chat_turns=[
            [
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "tool_calls": [
                                    {"index": 0, "id": "call_abc123", "function": {"name": "read_terminal_scrollback", "arguments": ""}}
                                ]
                            },
                        }
                    ]
                },
                {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"max'}}]}}]},
                {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '_bytes": 500}'}}]}}]},
                {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            ]
        ],
        chunk_delay=0.01,
    )
    try:
        provider = OpenAICompatibleProvider(server.base_url, model="gpt-4o-mini")
        tools = [ToolSpec(name="read_terminal_scrollback", description="...", parameters={})]
        events = [
            event
            async for event in provider.stream_chat([ChatMessage(role="user", content="hi")], tools)
        ]

        tool_events = [e for e in events if isinstance(e, ToolCallRequested)]
        assert len(tool_events) == 1
        call = tool_events[0].calls[0]
        assert call.name == "read_terminal_scrollback"
        assert call.arguments == {"max_bytes": 500}  # accumulated fragments, parsed once complete
        assert call.id == "call_abc123"  # the API's real id, not a locally-generated one
        assert events[-1] == Done("tool_calls")

        sent_tools = server.requests_received[0]["tools"]
        assert sent_tools[0]["function"]["name"] == "read_terminal_scrollback"
    finally:
        await server.close()


async def test_tool_result_round_trip_uses_real_tool_call_id():
    server = await start_fake_openai_server(chat_turns=[[{"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]])
    try:
        provider = OpenAICompatibleProvider(server.base_url, model="gpt-4o-mini")
        history = [
            ChatMessage(role="user", content="hi"),
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(name="read_terminal_scrollback", arguments={}, id="call_abc123")],
            ),
            ChatMessage(role="tool", content="some scrollback", tool_name="read_terminal_scrollback", tool_call_id="call_abc123"),
        ]
        async for _ in provider.stream_chat(history, []):
            pass

        sent = server.requests_received[0]["messages"]
        assert sent[1]["tool_calls"][0]["id"] == "call_abc123"
        assert sent[1]["tool_calls"][0]["function"]["arguments"] == "{}"
        assert sent[2]["role"] == "tool"
        assert sent[2]["tool_call_id"] == "call_abc123"
    finally:
        await server.close()


async def test_api_key_sent_as_bearer_header_when_configured():
    server = await start_fake_openai_server(chat_turns=[[{"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]])
    try:
        provider = OpenAICompatibleProvider(server.base_url, model="gpt-4o-mini", api_key="sk-secret")
        async for _ in provider.stream_chat([ChatMessage(role="user", content="hi")], []):
            pass
        assert server.headers_received[0]["authorization"] == "Bearer sk-secret"
    finally:
        await server.close()


async def test_no_authorization_header_when_no_api_key_configured():
    server = await start_fake_openai_server(chat_turns=[[{"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}]])
    try:
        provider = OpenAICompatibleProvider(server.base_url, model="gpt-4o-mini")
        async for _ in provider.stream_chat([ChatMessage(role="user", content="hi")], []):
            pass
        assert "authorization" not in server.headers_received[0]
    finally:
        await server.close()


async def test_model_not_found_raises_distinct_exception():
    server = await start_fake_openai_server(
        chat_turns=[], error_response=(404, {"error": {"message": "The model `gpt-fake` does not exist"}})
    )
    try:
        provider = OpenAICompatibleProvider(server.base_url, model="gpt-fake")
        with pytest.raises(ModelNotFound, match="does not exist"):
            async for _ in provider.stream_chat([ChatMessage(role="user", content="hi")], []):
                pass
    finally:
        await server.close()


async def test_unreachable_server_raises_provider_unavailable():
    provider = OpenAICompatibleProvider("http://127.0.0.1:1", model="gpt-4o-mini", timeout=2.0)

    with pytest.raises(ProviderUnavailable):
        async for _ in provider.stream_chat([ChatMessage(role="user", content="hi")], []):
            pass
