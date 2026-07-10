from __future__ import annotations

from app.ai.base import (
    AIProvider,
    ChatMessage,
    Done,
    ModelNotFound,
    ProviderUnavailable,
    TextDelta,
    ToolCall,
    ToolCallRequested,
)
from app.ai.session_registry import AgentSession
from app.ai.tools import (
    READ_SCROLLBACK_TOOL,
    SEND_COMMAND_TOOL,
    Notify,
    execute_read_scrollback,
    execute_send_command,
)
from app.config import get_settings

MAX_TOOL_ITERATIONS = 25

SYSTEM_MESSAGE = ChatMessage(
    role="system",
    content=(
        "Ты — Savr, ассистент сетевого инженера. Специализация: коммутаторы Eltex MES "
        "(MES23xx/33xx/35xx/5324) и оборудование Cisco IOS. Помогаешь интерпретировать журналы и "
        "вывод CLI, ведёшь диагностику пошагово и сам выполняешь команды на устройствах — "
        "диагностические и исправляющие. Каждую команду показываешь инженеру перед выполнением; для "
        "действий, способных уронить связность (аплинки, транки, перезагрузки), сначала коротко "
        "подтверждаешь намерение с инженером."
    ),
)

_TOOLS = [READ_SCROLLBACK_TOOL, SEND_COMMAND_TOOL]


async def run_agent_turn(
    session: AgentSession, provider: AIProvider, user_text: str, notify: Notify
) -> None:
    session.chat_history.append(ChatMessage(role="user", content=user_text))
    _trim_history(session)

    try:
        # Set once a call comes back truncated (hit ai_max_response_tokens)
        # with nothing to act on -- the *next* iteration's text then extends
        # the same chat_history entry instead of appending a new one, so one
        # logical (if long) answer doesn't end up as several separate
        # bubbles once the frontend replays history after a reconnect.
        continuing_truncated_reply = False

        for _ in range(MAX_TOOL_ITERATIONS):
            text = ""
            calls: list[ToolCall] = []
            done_reason = "stop"
            async for event in provider.stream_chat([SYSTEM_MESSAGE, *session.chat_history], _TOOLS):
                if isinstance(event, TextDelta):
                    text += event.text
                    await notify({"type": "assistant_delta", "text": event.text})
                elif isinstance(event, ToolCallRequested):
                    calls = event.calls
                elif isinstance(event, Done):
                    done_reason = event.reason

            last = session.chat_history[-1] if session.chat_history else None
            if continuing_truncated_reply and last is not None and last.role == "assistant" and not last.tool_calls:
                last.content += text
            else:
                session.chat_history.append(ChatMessage(role="assistant", content=text, tool_calls=calls or None))

            if calls:
                continuing_truncated_reply = False
                for call in calls:
                    await notify({"type": "tool_call", "name": call.name, "arguments": call.arguments})
                    result = await _dispatch(session, call, notify)
                    await notify({"type": "tool_result", "name": call.name, "result": result})
                    session.chat_history.append(
                        ChatMessage(role="tool", content=result, tool_name=call.name, tool_call_id=call.id)
                    )
                continue

            if done_reason == "length":
                # Cut off by the per-call token cap, not because the model was
                # actually finished -- loop again so it continues rather than
                # leaving a reply trailing off mid-sentence.
                continuing_truncated_reply = True
                continue

            return
        else:
            await notify(
                {
                    "type": "error",
                    "message": "Stopped after too many tool calls in one turn",
                    "fatal": False,
                }
            )
    except ModelNotFound as exc:
        await notify({"type": "error", "message": f"Model not available: {exc}", "fatal": False})
    except ProviderUnavailable as exc:
        await notify({"type": "error", "message": f"AI request failed: {exc}", "fatal": False})
    finally:
        await notify({"type": "assistant_done"})


async def _dispatch(session: AgentSession, call: ToolCall, notify: Notify) -> str:
    if call.name == "read_terminal_scrollback":
        return await execute_read_scrollback(session, call.arguments)
    if call.name == "send_command":
        return await execute_send_command(session, call.arguments, notify)
    return f"Error: unknown tool {call.name!r}"


def _trim_history(session: AgentSession) -> None:
    """Drop oldest whole turns (a turn = one user message plus everything up
    to the next user message) once history exceeds the cap -- never split an
    assistant tool_calls message from its tool-result replies. Simple cap, no
    summarization; an explicit v1 limitation."""
    limit = get_settings().ai_max_history_messages
    while len(session.chat_history) > limit:
        cut_at = next(
            (i for i in range(1, len(session.chat_history)) if session.chat_history[i].role == "user"),
            None,
        )
        if cut_at is None:
            break  # only one turn left; nothing safe to drop
        del session.chat_history[:cut_at]
