"""Exercises app.ai.loop.run_agent_turn end-to-end against a real in-process
SSH echo server (via SSHConnector) and a scripted FakeProvider -- proving the
tool-calling loop, the confirmation-pause flow, and the safety denylist all
work together, not just in isolation.
"""

import asyncio

from app.ai import session_registry
from app.ai.base import Done, TextDelta, ToolCall, ToolCallRequested
from app.ai.loop import run_agent_turn
from app.ai.session_registry import AgentSession
from app.connectors.ssh_connector import SSHConnector
from app.tests.fake_ai_provider import FakeProvider
from app.tests.ssh_test_server import start_ssh_test_server


async def _connected_session(server, session_id: str) -> AgentSession:
    async def on_output(data: bytes) -> None:
        session = session_registry.get(session_id)
        if session:
            session.feed(data)

    async def on_closed(reason: str) -> None:
        pass

    connector = SSHConnector(
        on_output,
        on_closed,
        hostname=server.host,
        port=server.port,
        username="tester",
        auth_method="password",
        secret=server.password,
        passphrase=None,
        pinned_fingerprint=None,
        cols=80,
        rows=24,
    )
    await connector.connect()
    return session_registry.register(session_id, connector)


class Recorder:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def notify(self, payload: dict) -> None:
        self.messages.append(payload)

    def of_type(self, type_: str) -> list[dict]:
        return [m for m in self.messages if m["type"] == type_]


async def test_read_scrollback_tool_requires_no_confirmation():
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "test-read-scrollback"
    try:
        session = await _connected_session(server, session_id)
        await session.connector.write(b"seed-output")
        await asyncio.sleep(0.3)  # let the echo arrive and land in scrollback

        provider = FakeProvider(
            [
                [ToolCallRequested([ToolCall(name="read_terminal_scrollback", arguments={})]), Done("tool_calls")],
                [TextDelta("The device looks fine."), Done("stop")],
            ]
        )
        recorder = Recorder()

        await run_agent_turn(session, provider, "what's on screen?", recorder.notify)

        assert recorder.of_type("pending_confirmation") == []
        tool_results = recorder.of_type("tool_result")
        assert len(tool_results) == 1
        assert "seed-output" in tool_results[0]["result"]
        assert recorder.of_type("assistant_done")
    finally:
        await session.connector.close()
        session_registry.unregister(session_id)
        await server.close()


async def test_dangerous_command_pauses_even_in_auto_mode_then_executes_on_approval():
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "test-dangerous-auto"
    try:
        session = await _connected_session(server, session_id)
        session.mode = "auto"  # dangerous commands must still pause regardless

        provider = FakeProvider(
            [
                [
                    ToolCallRequested([ToolCall(name="send_command", arguments={"command": "reload"})]),
                    Done("tool_calls"),
                ],
                [TextDelta("Done."), Done("stop")],
            ]
        )
        recorder = Recorder()

        async def notify(payload: dict) -> None:
            await recorder.notify(payload)
            if payload["type"] == "pending_confirmation":
                assert payload["reason"] == "dangerous"
                assert session.pending_confirmation is not None
                session.pending_confirmation.set_result(True)  # simulate user clicking Approve

        await run_agent_turn(session, provider, "reload it", notify)

        assert len(recorder.of_type("pending_confirmation")) == 1
        tool_results = recorder.of_type("tool_result")
        assert len(tool_results) == 1
        assert "reload" in tool_results[0]["result"]  # real echo from the SSH test server
    finally:
        await session.connector.close()
        session_registry.unregister(session_id)
        await server.close()


async def test_rejected_command_never_reaches_the_connector():
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "test-rejected-command"
    try:
        session = await _connected_session(server, session_id)
        session.mode = "confirm"

        provider = FakeProvider(
            [
                [
                    ToolCallRequested(
                        [ToolCall(name="send_command", arguments={"command": "configure terminal"})]
                    ),
                    Done("tool_calls"),
                ],
                [TextDelta("Understood, not applied."), Done("stop")],
            ]
        )
        recorder = Recorder()

        async def notify(payload: dict) -> None:
            await recorder.notify(payload)
            if payload["type"] == "pending_confirmation":
                session.pending_confirmation.set_result(False)  # simulate user clicking Reject

        await run_agent_turn(session, provider, "enter config mode", notify)

        tool_results = recorder.of_type("tool_result")
        assert "rejected" in tool_results[0]["result"].lower()
        await asyncio.sleep(0.2)
        assert b"configure terminal" not in session.tail(10_000)
    finally:
        await session.connector.close()
        session_registry.unregister(session_id)
        await server.close()


async def test_safe_command_in_auto_mode_executes_without_pausing():
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "test-safe-auto"
    try:
        session = await _connected_session(server, session_id)
        session.mode = "auto"

        provider = FakeProvider(
            [
                [
                    ToolCallRequested([ToolCall(name="send_command", arguments={"command": "show version"})]),
                    Done("tool_calls"),
                ],
                [TextDelta("Here's the version info."), Done("stop")],
            ]
        )
        recorder = Recorder()

        await run_agent_turn(session, provider, "show me the version", recorder.notify)

        assert recorder.of_type("pending_confirmation") == []
        tool_results = recorder.of_type("tool_result")
        assert "show version" in tool_results[0]["result"]
    finally:
        await session.connector.close()
        session_registry.unregister(session_id)
        await server.close()


async def test_history_records_full_conversation():
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "test-history"
    try:
        session = await _connected_session(server, session_id)
        provider = FakeProvider([[TextDelta("Hi there."), Done("stop")]])

        await run_agent_turn(session, provider, "hello", Recorder().notify)

        roles = [m.role for m in session.chat_history]
        assert roles == ["user", "assistant"]
        assert session.chat_history[-1].content == "Hi there."
    finally:
        await session.connector.close()
        session_registry.unregister(session_id)
        await server.close()


async def test_truncated_reply_is_automatically_continued_and_merged():
    """A response cut off by the per-call token cap (done_reason="length")
    must not read as the agent simply trailing off mid-sentence -- the loop
    should call the model again and stitch the continuation onto the same
    logical reply rather than leaving two disjointed chat_history entries."""
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "test-truncated-continue"
    try:
        session = await _connected_session(server, session_id)
        provider = FakeProvider(
            [
                [TextDelta("This is a very long explanation that gets cut"), Done("length")],
                [TextDelta(" off and then continues seamlessly."), Done("stop")],
            ]
        )
        recorder = Recorder()

        await run_agent_turn(session, provider, "explain everything", recorder.notify)

        # The model was called twice (once truncated, once to continue)...
        assert len(provider.calls) == 2
        # ...but the frontend only ever sees one assistant_done for the whole turn.
        assert len(recorder.of_type("assistant_done")) == 1
        deltas = "".join(m["text"] for m in recorder.of_type("assistant_delta"))
        assert deltas == "This is a very long explanation that gets cut off and then continues seamlessly."

        # And chat_history has ONE merged assistant message, not two.
        roles = [m.role for m in session.chat_history]
        assert roles == ["user", "assistant"]
        assert (
            session.chat_history[-1].content
            == "This is a very long explanation that gets cut off and then continues seamlessly."
        )
    finally:
        await session.connector.close()
        session_registry.unregister(session_id)
        await server.close()
