"""Scriptable fake AIProvider for testing app.ai.loop without a real LLM backend."""

from __future__ import annotations

from collections.abc import AsyncIterator

from app.ai.base import AIProvider, ChatMessage, StreamEvent, ToolSpec


class FakeProvider(AIProvider):
    """Replays one pre-scripted list of StreamEvents per call to stream_chat()."""

    def __init__(self, turns: list[list[StreamEvent]]) -> None:
        self._turns = list(turns)
        self.calls: list[tuple[list[ChatMessage], list[ToolSpec]]] = []

    async def stream_chat(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[StreamEvent]:
        self.calls.append((messages, tools))
        if not self._turns:
            raise AssertionError("FakeProvider.stream_chat called more times than scripted")
        for event in self._turns.pop(0):
            yield event
