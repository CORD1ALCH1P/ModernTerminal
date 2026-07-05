from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import httpx

from app.ai.base import (
    AIProvider,
    ChatMessage,
    Done,
    ModelNotFound,
    ProviderUnavailable,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallRequested,
    ToolSpec,
)


def _to_openai_message(message: ChatMessage) -> dict:
    payload: dict = {"role": message.role, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    return payload


def _to_openai_tool(tool: ToolSpec) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _error_detail(body: bytes) -> str | None:
    """OpenAI-style error bodies are {"error": {"message": "...", ...}} --
    a different shape than Ollama's flat {"error": "..."}, so this doesn't
    share a helper with ollama_provider.py."""
    try:
        error = json.loads(body).get("error")
    except (ValueError, AttributeError):
        return None
    if isinstance(error, dict):
        message = error.get("message")
        return message if isinstance(message, str) else None
    return error if isinstance(error, str) else None


class OpenAICompatibleProvider(AIProvider):
    """Client for any OpenAI-compatible /chat/completions endpoint -- a cloud
    API, or a self-hosted server (vLLM, LM Studio, text-generation-webui,
    etc.) that speaks the same wire format.

    Wire format (OpenAI's documented streaming Chat Completions API): SSE,
    "data: {...}\\n\\n" per chunk, terminated by a literal "data: [DONE]\\n\\n".
    Unlike Ollama, tool-call arguments stream incrementally as raw JSON text
    fragments keyed by an index (not the eventual call id), which must be
    accumulated across chunks and parsed only once a finish_reason arrives.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
        max_response_tokens: int | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = client or httpx.AsyncClient()
        self._max_response_tokens = max_response_tokens

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict:
        # Omitted entirely (rather than sent empty) when no key is
        # configured -- some self-hosted servers reject requests carrying an
        # Authorization header they don't expect at all.
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def stream_chat(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[StreamEvent]:
        payload: dict = {
            "model": self._model,
            "messages": [_to_openai_message(m) for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = [_to_openai_tool(t) for t in tools]
        if self._max_response_tokens is not None:
            payload["max_tokens"] = self._max_response_tokens

        # Accumulated per tool-call index until the stream finishes. id/name
        # typically only arrive in the first fragment for a given index;
        # arguments arrive as a raw (partial) JSON string, concatenated here
        # and parsed only once complete.
        pending_calls: dict[int, dict] = {}

        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self._timeout,
            ) as response:
                if response.status_code >= 400:
                    detail = _error_detail(await response.aread())
                    if response.status_code == 404 and detail:
                        raise ModelNotFound(detail)
                    raise ProviderUnavailable(detail or f"HTTP {response.status_code}")

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        return
                    if not data:
                        continue
                    chunk = json.loads(data)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}

                    if delta.get("content"):
                        yield TextDelta(delta["content"])

                    for fragment in delta.get("tool_calls") or []:
                        index = fragment.get("index", 0)
                        entry = pending_calls.setdefault(index, {"id": None, "name": None, "arguments": ""})
                        if fragment.get("id"):
                            entry["id"] = fragment["id"]
                        function = fragment.get("function") or {}
                        if function.get("name"):
                            entry["name"] = function["name"]
                        if function.get("arguments"):
                            entry["arguments"] += function["arguments"]

                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        if pending_calls:
                            calls = []
                            for entry in pending_calls.values():
                                try:
                                    arguments = json.loads(entry["arguments"]) if entry["arguments"] else {}
                                except ValueError:
                                    arguments = {}
                                calls.append(
                                    ToolCall(
                                        name=entry["name"] or "",
                                        arguments=arguments,
                                        id=entry["id"] or uuid.uuid4().hex,
                                    )
                                )
                            yield ToolCallRequested(calls)
                        yield Done(finish_reason)
                        return
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderUnavailable(str(exc)) from exc
