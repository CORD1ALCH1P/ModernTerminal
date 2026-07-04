import pytest

from app.ai.base import ChatMessage, Done, ProviderUnavailable, TextDelta, ToolCallRequested, ToolSpec
from app.ai.ollama_provider import OllamaProvider
from app.tests.fake_ollama_server import start_fake_ollama_server


async def test_plain_text_turn_accumulates_incremental_deltas():
    server = await start_fake_ollama_server(
        chat_turns=[
            [
                {"message": {"role": "assistant", "content": "Hello"}, "done": False},
                {"message": {"role": "assistant", "content": ", world"}, "done": False},
                {"message": {"role": "assistant", "content": "!"}, "done": False},
                {"done": True, "done_reason": "stop"},
            ]
        ],
        chunk_delay=0.01,  # force genuinely separate TCP writes, not one coalesced blob
    )
    try:
        provider = OllamaProvider(server.base_url, model="qwen3:8b")
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


async def test_tool_call_turn_parses_arguments_as_dict():
    server = await start_fake_ollama_server(
        chat_turns=[
            [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "read_terminal_scrollback",
                                    "arguments": {"max_bytes": 500},
                                }
                            }
                        ],
                    },
                    "done": False,
                },
                {"done": True, "done_reason": "stop"},
            ]
        ]
    )
    try:
        provider = OllamaProvider(server.base_url, model="qwen3:8b")
        tools = [ToolSpec(name="read_terminal_scrollback", description="...", parameters={})]
        events = [
            event
            async for event in provider.stream_chat([ChatMessage(role="user", content="hi")], tools)
        ]

        tool_events = [e for e in events if isinstance(e, ToolCallRequested)]
        assert len(tool_events) == 1
        call = tool_events[0].calls[0]
        assert call.name == "read_terminal_scrollback"
        assert call.arguments == {"max_bytes": 500}  # already a dict, no json.loads needed
        assert isinstance(call.id, str) and call.id

        sent_tools = server.requests_received[0]["tools"]
        assert sent_tools[0]["function"]["name"] == "read_terminal_scrollback"
    finally:
        await server.close()


async def test_unreachable_server_raises_provider_unavailable():
    provider = OllamaProvider("http://127.0.0.1:1", model="qwen3:8b", timeout=2.0)

    with pytest.raises(ProviderUnavailable):
        async for _ in provider.stream_chat([ChatMessage(role="user", content="hi")], []):
            pass


async def test_list_models_and_supports_tools():
    server = await start_fake_ollama_server(chat_turns=[])
    try:
        provider = OllamaProvider(server.base_url, model="qwen3:8b")
        assert await provider.list_models() == ["qwen3:8b"]
        assert await provider.supports_tools("qwen3:8b") is True
    finally:
        await server.close()
