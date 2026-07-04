from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from app.ai.base import ToolSpec
from app.ai.safety import is_dangerous
from app.ai.session_registry import AgentSession
from app.config import get_settings

Notify = Callable[[dict], Awaitable[None]]

READ_SCROLLBACK_TOOL = ToolSpec(
    name="read_terminal_scrollback",
    description=(
        "Return the most recent terminal output (prompts, command results, errors). "
        "Call this before acting if you're unsure of the device's current state."
    ),
    parameters={
        "type": "object",
        "properties": {
            "max_bytes": {"type": "integer", "description": "Max bytes to return (default 4000)."}
        },
        "required": [],
    },
)

SEND_COMMAND_TOOL = ToolSpec(
    name="send_command",
    description=(
        "Type one command + Enter into the live terminal and report what happened. "
        "Dangerous commands, or the session being in 'confirm' mode, always pause for "
        "human approval first -- that pause is not an error, just wait for the outcome."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Exact command text, no trailing newline."}
        },
        "required": ["command"],
    },
)


async def execute_read_scrollback(session: AgentSession, arguments: dict) -> str:
    max_bytes = int(arguments.get("max_bytes") or 4000)
    return session.tail(max_bytes).decode("utf-8", errors="replace")


async def execute_send_command(session: AgentSession, arguments: dict, notify: Notify) -> str:
    command = str(arguments.get("command", "")).strip()
    if not command:
        return "Error: empty command, nothing sent."

    if session.mode == "confirm" or is_dangerous(command):
        approved = await _request_confirmation(session, command, notify)
        if not approved:
            return f"Command rejected by user, not sent: {command!r}"

    await session.connector.write((command + "\n").encode())
    output = await _wait_for_quiet(session)
    return output.decode("utf-8", errors="replace") or "(no output within the wait window)"


async def _request_confirmation(session: AgentSession, command: str, notify: Notify) -> bool:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[bool] = loop.create_future()
    session.pending_confirmation, session.pending_command = future, command
    await notify(
        {
            "type": "pending_confirmation",
            "command": command,
            "reason": "dangerous" if is_dangerous(command) else "confirm_mode",
        }
    )
    try:
        return await future
    finally:
        session.pending_confirmation, session.pending_command = None, None


async def _wait_for_quiet(session: AgentSession) -> bytes:
    """Vendor-agnostic "did the command finish" heuristic: wait for a quiet
    period with no new output, capped at a max total wait -- avoids assuming
    any particular device's prompt regex."""
    settings = get_settings()
    quiet_s = settings.ai_command_quiet_ms / 1000
    cap_s = settings.ai_command_max_wait_ms / 1000

    start = time.monotonic()
    baseline = len(session.scrollback)
    while time.monotonic() - start < cap_s:
        session.output_event.clear()
        try:
            await asyncio.wait_for(session.output_event.wait(), timeout=quiet_s)
        except TimeoutError:
            break  # no new output for a full quiet window -> consider it settled
    return b"".join(list(session.scrollback)[baseline:])
