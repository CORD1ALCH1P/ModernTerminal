from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.ai import session_registry
from app.ai.base import AIProvider, ChatMessage
from app.ai.loop import run_agent_turn
from app.ai.ollama_provider import OllamaProvider
from app.ai.provider_factory import get_provider
from app.ai.tools import Notify

router = APIRouter(prefix="/api/ws", tags=["agent"])


def _to_wire(message: ChatMessage) -> dict:
    return {"role": message.role, "content": message.content}


async def _check_capability(provider: AIProvider, notify: Notify) -> None:
    """Best-effort, Ollama-specific capability warning -- not part of the
    general AIProvider contract, so this stays outside the abstraction and
    must never affect the session if it fails or the model is unsupported.
    Uses the provider's own configured model, not a separately re-fetched
    settings value, so it can never check a different model than the one
    actually in use."""
    if not isinstance(provider, OllamaProvider):
        return
    try:
        supports = await provider.supports_tools(provider.model)
        if supports is False:
            await notify(
                {
                    "type": "capability_warning",
                    "message": (
                        f"Model {provider.model!r} may not support tool calling -- the copilot "
                        "might not be able to read the terminal or send commands. Consider a "
                        "different OLLAMA_MODEL."
                    ),
                }
            )
    except Exception:
        pass


@router.websocket("/agent")
async def agent_ws(websocket: WebSocket, session_id: str = Query(...)) -> None:
    await websocket.accept()

    session = session_registry.get(session_id)
    if session is None:
        await websocket.send_json(
            {"type": "error", "message": "No active terminal session for this tab yet.", "fatal": True}
        )
        await websocket.close()
        return

    if session.agent_ws is not None:
        # A stale connection from another tab/window for the same session_id --
        # only one agent panel may be attached to a session at a time.
        await session.agent_ws.send_json(
            {"type": "error", "message": "Reconnected from another tab/window.", "fatal": True}
        )
        await session.agent_ws.close()
    session.agent_ws = websocket

    # ASGI doesn't guarantee safety for concurrent send()s from two different
    # tasks on one connection -- the background turn task (frequent
    # assistant_delta/tool_call notifications) and this receive loop (rare
    # mode_changed/error acks) both call websocket.send_json(), so serialize.
    send_lock = asyncio.Lock()

    async def notify(payload: dict) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    provider = get_provider()

    await notify({"type": "status", "state": "ready", "mode": session.mode})
    capability_task = asyncio.create_task(_check_capability(provider, notify))
    if session.chat_history:
        await notify({"type": "history", "messages": [_to_wire(m) for m in session.chat_history]})

    current_turn: asyncio.Task[None] | None = None
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            text = message.get("text")
            if text is None:
                continue
            try:
                control = json.loads(text)
            except ValueError:
                continue

            kind = control.get("type")
            if kind == "user_message":
                if current_turn is not None and not current_turn.done():
                    await notify(
                        {"type": "error", "message": "A turn is already in progress", "fatal": False}
                    )
                    continue
                user_text = str(control.get("text", ""))
                current_turn = asyncio.create_task(run_agent_turn(session, provider, user_text, notify))
            elif kind == "confirm_command":
                if session.pending_confirmation is not None and not session.pending_confirmation.done():
                    session.pending_confirmation.set_result(bool(control.get("approve")))
            elif kind == "set_mode" and control.get("mode") in ("confirm", "auto"):
                session.mode = control["mode"]
                await notify({"type": "mode_changed", "mode": session.mode})
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: Starlette raises this if receive() is called after the
        # connection has already been torn down concurrently.
        pass
    finally:
        capability_task.cancel()
        if current_turn is not None:
            current_turn.cancel()
        if session.pending_confirmation is not None and not session.pending_confirmation.done():
            session.pending_confirmation.cancel()
        # Only clear if we're still the registered connection -- a newer
        # connection (e.g. a fast reconnect) may have already replaced us,
        # and this teardown running late must not clobber that registration.
        if session.agent_ws is websocket:
            session.agent_ws = None
