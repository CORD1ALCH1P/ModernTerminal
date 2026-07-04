from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.ai.base import ChatMessage
from app.config import get_settings
from app.connectors.base import TerminalConnector

if TYPE_CHECKING:
    from fastapi import WebSocket

Mode = Literal["confirm", "auto"]


@dataclass
class AgentSession:
    """One entry per open terminal tab that has an AI panel. Populated by
    terminal_ws.py on connect, looked up by agent_ws.py so the agent can read
    and write the *same* live connector the user's terminal is driving.

    In-memory only, single-process, single-threaded asyncio -- no lock is
    needed since none of these mutations ever suspend mid-operation.
    """

    session_id: str
    connector: TerminalConnector
    scrollback: deque[bytes] = field(default_factory=deque)
    scrollback_bytes: int = 0
    output_event: asyncio.Event = field(default_factory=asyncio.Event)
    mode: Mode = "confirm"  # always the default for a new session -- safety first
    chat_history: list[ChatMessage] = field(default_factory=list)
    pending_confirmation: asyncio.Future[bool] | None = None
    pending_command: str | None = None
    agent_ws: "WebSocket | None" = None

    def feed(self, data: bytes) -> None:
        self.scrollback.append(data)
        self.scrollback_bytes += len(data)
        cap = get_settings().ai_scrollback_max_bytes
        while self.scrollback_bytes > cap and self.scrollback:
            dropped = self.scrollback.popleft()
            self.scrollback_bytes -= len(dropped)
        self.output_event.set()

    def tail(self, max_bytes: int) -> bytes:
        joined = b"".join(self.scrollback)
        return joined[-max_bytes:] if max_bytes > 0 else joined


_sessions: dict[str, AgentSession] = {}


def register(session_id: str, connector: TerminalConnector) -> AgentSession:
    session = AgentSession(session_id=session_id, connector=connector)
    _sessions[session_id] = session
    return session


def get(session_id: str) -> AgentSession | None:
    return _sessions.get(session_id)


def unregister(session_id: str) -> None:
    session = _sessions.pop(session_id, None)
    if session and session.pending_confirmation and not session.pending_confirmation.done():
        session.pending_confirmation.cancel()
