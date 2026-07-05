from __future__ import annotations

import abc
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema, OpenAI-style function-calling shape


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex)  # local bookkeeping only


@dataclass
class ChatMessage:
    role: Role
    content: str
    tool_calls: list[ToolCall] | None = None  # only on assistant messages
    tool_name: str | None = None  # only on role="tool" messages (Ollama's convention)
    tool_call_id: str | None = None  # only on role="tool" messages (OpenAI-compatible
    # convention -- correlates back to the ToolCall.id that requested it; each provider
    # implementation reads whichever of these two fields its own wire format needs)


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCallRequested:
    calls: list[ToolCall]


@dataclass
class Done:
    reason: str


StreamEvent = TextDelta | ToolCallRequested | Done


class ProviderError(Exception):
    """Base for AI-provider failures."""


class ProviderUnavailable(ProviderError):
    """Endpoint unreachable, timed out, or returned a non-2xx status -- recoverable,
    the caller should surface this as a non-fatal error rather than crashing."""


class ModelNotFound(ProviderUnavailable):
    """The configured model isn't available on the provider (e.g. not pulled
    yet in Ollama). A subclass of ProviderUnavailable so existing callers
    that only handle that still work; callers that want to react
    specifically (e.g. surface a "pull the model" hint proactively instead
    of a generic connectivity error) can catch this distinctly."""


class AIProvider(abc.ABC):
    """One turn of a tool-calling conversation with an LLM backend.

    The multi-turn orchestration (looping while the model keeps requesting
    tools, executing them, feeding results back) deliberately lives outside
    any provider implementation (see app/ai/loop.py) -- each provider only
    needs to turn its own wire format into this same event stream, which is
    what keeps this interface swappable across very different backends (e.g.
    Ollama emits a tool call whole in one chunk, while Anthropic streams tool
    arguments incrementally as partial JSON -- both get normalized here).
    """

    @abc.abstractmethod
    def stream_chat(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[StreamEvent]:
        """One turn: yields TextDelta* then an optional ToolCallRequested, then
        a final Done. Raises ProviderUnavailable on transport failure."""
