from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.ai.base import (
    AIProvider,
    ChatMessage,
    Done,
    ProviderUnavailable,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallRequested,
    ToolSpec,
)


def _to_ollama_message(message: ChatMessage) -> dict:
    payload: dict = {"role": message.role, "content": message.content}
    if message.tool_name is not None:
        payload["tool_name"] = message.tool_name
    return payload


def _to_ollama_tool(tool: ToolSpec) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


class OllamaProvider(AIProvider):
    """Client for a local/self-hosted Ollama server's /api/chat endpoint.

    Wire format (verified against Ollama's docs/source, not assumed):
    NDJSON stream, one object per line, shaped like
    {"message": {"role","content","tool_calls"?}, "done": bool, ...}.
    `message.content` deltas are incremental (concatenate, don't replace).
    `message.tool_calls[].function.arguments` arrives already parsed as a
    dict, not a JSON string, and is emitted whole in one chunk (no
    incremental argument streaming the way OpenAI/Anthropic do it) -- that
    chunk carries content="" and done=false; the stream then closes with a
    separate stats-only done=true chunk.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
        max_response_tokens: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._client = client or httpx.AsyncClient()
        self._max_response_tokens = max_response_tokens

    @property
    def model(self) -> str:
        return self._model

    async def stream_chat(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[StreamEvent]:
        payload: dict = {
            "model": self._model,
            "messages": [_to_ollama_message(m) for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = [_to_ollama_tool(t) for t in tools]
        if self._max_response_tokens is not None:
            payload["options"] = {"num_predict": self._max_response_tokens}

        try:
            async with self._client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload, timeout=self._timeout
            ) as response:
                response.raise_for_status()
                tool_calls_seen = False
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    message = chunk.get("message") or {}
                    if message.get("content"):
                        yield TextDelta(message["content"])
                    raw_calls = message.get("tool_calls")
                    if raw_calls and not tool_calls_seen:
                        tool_calls_seen = True
                        yield ToolCallRequested(
                            [
                                ToolCall(
                                    name=call["function"]["name"],
                                    arguments=call["function"].get("arguments") or {},
                                )
                                for call in raw_calls
                            ]
                        )
                    if chunk.get("done"):
                        yield Done(chunk.get("done_reason") or "stop")
                        return
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            raise ProviderUnavailable(str(exc)) from exc

    async def list_models(self) -> list[str]:
        try:
            response = await self._client.get(f"{self._base_url}/api/tags", timeout=self._timeout)
            response.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            raise ProviderUnavailable(str(exc)) from exc
        return [entry["name"] for entry in response.json().get("models", [])]

    async def supports_tools(self, model: str) -> bool | None:
        """Best-effort capability check via /api/show. Returns None (rather
        than guessing) if the endpoint or response shape isn't as expected."""
        try:
            response = await self._client.post(
                f"{self._base_url}/api/show", json={"model": model}, timeout=self._timeout
            )
            response.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return None
        capabilities = response.json().get("capabilities")
        if not isinstance(capabilities, list):
            return None
        return "tools" in capabilities
