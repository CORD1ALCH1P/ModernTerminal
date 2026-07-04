"""Drives app.routers.agent_ws.agent_ws directly (same FakeWebSocket approach
as test_terminal_ws.py), alongside a real terminal_ws session (real SSH test
server) and a scripted FakeProvider, to exercise the full WS protocol: status,
history, user_message -> assistant_delta/tool_call/tool_result/assistant_done,
confirm_command, set_mode, the "no session yet" rejection, and a second
connection kicking out the first.
"""

import asyncio

from app.ai import session_registry
from app.ai.base import Done, TextDelta, ToolCall, ToolCallRequested
from app.ai.ollama_provider import OllamaProvider
from app.tests.fake_ai_provider import FakeProvider
from app.tests.fake_ollama_server import start_fake_ollama_server
from app.tests.fake_websocket import FakeWebSocket
from app.tests.ssh_test_server import start_ssh_test_server


async def _start_registered_terminal(client, server, session_id: str):
    host = (
        await client.post(
            "/api/hosts",
            json={
                "label": "agent-ws-test",
                "protocol": "ssh",
                "hostname": server.host,
                "port": server.port,
                "username": "tester",
                "auth_method": "password",
                "secret": server.password,
            },
        )
    ).json()

    from app.db import AsyncSessionLocal
    from app.routers.terminal_ws import terminal_ws as terminal_ws_endpoint

    term_ws = FakeWebSocket()
    db_cm = AsyncSessionLocal()
    db = await db_cm.__aenter__()
    task = asyncio.create_task(
        terminal_ws_endpoint(
            term_ws, host_id=host["id"], cols=80, rows=24, session_id=session_id, db=db
        )
    )
    await term_ws.next_message()  # connecting
    await term_ws.next_message()  # connected
    return term_ws, task, db_cm


async def test_agent_ws_rejects_when_no_terminal_session_registered():
    from app.routers.agent_ws import agent_ws as agent_ws_endpoint

    ws = FakeWebSocket()
    await agent_ws_endpoint(ws, session_id="never-registered")

    kind, payload = await ws.next_message()
    assert kind == "json"
    assert payload["type"] == "error"
    assert payload["fatal"] is True


async def test_agent_ws_full_protocol_happy_path(client, monkeypatch):
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "agent-ws-happy-path"
    try:
        term_ws, term_task, db_cm = await _start_registered_terminal(client, server, session_id)

        import app.routers.agent_ws as agent_ws_module

        provider = FakeProvider([[TextDelta("Hello "), TextDelta("engineer!"), Done("stop")]])
        monkeypatch.setattr(agent_ws_module, "get_provider", lambda: provider)

        agent_fake_ws = FakeWebSocket()
        agent_task = asyncio.create_task(
            agent_ws_module.agent_ws(agent_fake_ws, session_id=session_id)
        )

        kind, payload = await agent_fake_ws.next_message()
        assert (kind, payload) == ("json", {"type": "status", "state": "ready", "mode": "confirm"})

        await agent_fake_ws.from_client.put(
            {"type": "websocket.receive", "text": '{"type":"user_message","text":"hi"}'}
        )

        deltas = []
        while True:
            kind, payload = await agent_fake_ws.next_message()
            assert kind == "json"
            if payload["type"] == "assistant_delta":
                deltas.append(payload["text"])
            elif payload["type"] == "assistant_done":
                break
            else:
                raise AssertionError(f"unexpected message: {payload}")

        assert "".join(deltas) == "Hello engineer!"

        await agent_fake_ws.close()
        await asyncio.wait_for(agent_task, timeout=5)

        await term_ws.client_send_bytes(b"__close__")
        await term_ws.next_message()  # closed
        await asyncio.wait_for(term_task, timeout=5)
        await db_cm.__aexit__(None, None, None)
    finally:
        session_registry.unregister(session_id)
        await server.close()


async def test_agent_ws_confirm_command_via_receive_loop(client, monkeypatch):
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "agent-ws-confirm-flow"
    try:
        term_ws, term_task, db_cm = await _start_registered_terminal(client, server, session_id)

        import app.routers.agent_ws as agent_ws_module

        provider = FakeProvider(
            [
                [
                    ToolCallRequested([ToolCall(name="send_command", arguments={"command": "reload"})]),
                    Done("tool_calls"),
                ],
                [TextDelta("Done."), Done("stop")],
            ]
        )
        monkeypatch.setattr(agent_ws_module, "get_provider", lambda: provider)

        agent_fake_ws = FakeWebSocket()
        agent_task = asyncio.create_task(
            agent_ws_module.agent_ws(agent_fake_ws, session_id=session_id)
        )
        await agent_fake_ws.next_message()  # status ready

        await agent_fake_ws.from_client.put(
            {"type": "websocket.receive", "text": '{"type":"user_message","text":"reload it"}'}
        )

        # Drain messages until the pending_confirmation prompt appears.
        payload = None
        for _ in range(10):
            kind, payload = await agent_fake_ws.next_message()
            if payload["type"] == "pending_confirmation":
                break
        assert payload["type"] == "pending_confirmation"
        assert payload["command"] == "reload"
        assert payload["reason"] == "dangerous"

        await agent_fake_ws.from_client.put(
            {"type": "websocket.receive", "text": '{"type":"confirm_command","approve":true}'}
        )

        messages = []
        while True:
            kind, payload = await agent_fake_ws.next_message()
            messages.append(payload)
            if payload["type"] == "assistant_done":
                break

        tool_results = [m for m in messages if m["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert "reload" in tool_results[0]["result"]  # real echo from the SSH test server

        await agent_fake_ws.close()
        await asyncio.wait_for(agent_task, timeout=5)

        await term_ws.client_send_bytes(b"__close__")
        await term_ws.next_message()
        await asyncio.wait_for(term_task, timeout=5)
        await db_cm.__aexit__(None, None, None)
    finally:
        session_registry.unregister(session_id)
        await server.close()


async def test_agent_ws_set_mode_updates_session_and_acks(client, monkeypatch):
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "agent-ws-set-mode"
    try:
        term_ws, term_task, db_cm = await _start_registered_terminal(client, server, session_id)

        import app.routers.agent_ws as agent_ws_module

        monkeypatch.setattr(agent_ws_module, "get_provider", lambda: FakeProvider([]))

        agent_fake_ws = FakeWebSocket()
        agent_task = asyncio.create_task(
            agent_ws_module.agent_ws(agent_fake_ws, session_id=session_id)
        )
        await agent_fake_ws.next_message()  # status ready

        await agent_fake_ws.from_client.put(
            {"type": "websocket.receive", "text": '{"type":"set_mode","mode":"auto"}'}
        )
        kind, payload = await agent_fake_ws.next_message()
        assert (kind, payload) == ("json", {"type": "mode_changed", "mode": "auto"})
        assert session_registry.get(session_id).mode == "auto"

        await agent_fake_ws.close()
        await asyncio.wait_for(agent_task, timeout=5)

        await term_ws.client_send_bytes(b"__close__")
        await term_ws.next_message()
        await asyncio.wait_for(term_task, timeout=5)
        await db_cm.__aexit__(None, None, None)
    finally:
        session_registry.unregister(session_id)
        await server.close()


async def test_second_agent_ws_kicks_out_the_first(client, monkeypatch):
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "agent-ws-kickout"
    try:
        term_ws, term_task, db_cm = await _start_registered_terminal(client, server, session_id)

        import app.routers.agent_ws as agent_ws_module

        monkeypatch.setattr(agent_ws_module, "get_provider", lambda: FakeProvider([]))

        first_ws = FakeWebSocket()
        first_task = asyncio.create_task(agent_ws_module.agent_ws(first_ws, session_id=session_id))
        await first_ws.next_message()  # status ready

        second_ws = FakeWebSocket()
        second_task = asyncio.create_task(agent_ws_module.agent_ws(second_ws, session_id=session_id))
        await second_ws.next_message()  # status ready for the new connection

        kind, payload = await first_ws.next_message()
        assert kind == "json"
        assert payload["type"] == "error"
        assert "another tab" in payload["message"].lower()

        await asyncio.wait_for(first_task, timeout=5)

        # The first connection's belated teardown must not clobber the
        # second (surviving) connection's registration -- a real race that
        # can happen on a fast reconnect (e.g. React StrictMode's dev-only
        # double-mount opening two WebSockets in quick succession).
        assert session_registry.get(session_id).agent_ws is second_ws

        await second_ws.close()
        await asyncio.wait_for(second_task, timeout=5)

        await term_ws.client_send_bytes(b"__close__")
        await term_ws.next_message()
        await asyncio.wait_for(term_task, timeout=5)
        await db_cm.__aexit__(None, None, None)
    finally:
        session_registry.unregister(session_id)
        await server.close()


async def test_agent_ws_warns_when_model_lacks_tool_support(client, monkeypatch):
    server = await start_ssh_test_server(password="s3cr3t")
    session_id = "agent-ws-capability-warning"
    ollama_server = await start_fake_ollama_server(
        chat_turns=[], show_response={"capabilities": ["completion"]}  # no "tools"
    )
    try:
        term_ws, term_task, db_cm = await _start_registered_terminal(client, server, session_id)

        import app.routers.agent_ws as agent_ws_module

        provider = OllamaProvider(ollama_server.base_url, model="some-model")
        monkeypatch.setattr(agent_ws_module, "get_provider", lambda: provider)

        agent_fake_ws = FakeWebSocket()
        agent_task = asyncio.create_task(
            agent_ws_module.agent_ws(agent_fake_ws, session_id=session_id)
        )

        kind, payload = await agent_fake_ws.next_message()
        assert (kind, payload) == ("json", {"type": "status", "state": "ready", "mode": "confirm"})

        kind, payload = await agent_fake_ws.next_message()
        assert kind == "json"
        assert payload["type"] == "capability_warning"
        assert "some-model" in payload["message"]

        await agent_fake_ws.close()
        await asyncio.wait_for(agent_task, timeout=5)

        await term_ws.client_send_bytes(b"__close__")
        await term_ws.next_message()
        await asyncio.wait_for(term_task, timeout=5)
        await db_cm.__aexit__(None, None, None)
    finally:
        session_registry.unregister(session_id)
        await ollama_server.close()
        await server.close()
