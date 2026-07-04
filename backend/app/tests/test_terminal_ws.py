"""
Drives app.routers.terminal_ws.terminal_ws directly (bypassing FastAPI's own
ASGI/WebSocket test client) against a FakeWebSocket test double and a real,
in-process asyncssh server. This keeps everything on the single event loop
pytest-asyncio already provides for the test, avoiding cross-loop issues that
come from mixing our async DB engine with a separately-threaded WS test client,
while still exercising the real network path through SSHConnector.
"""

import asyncio

from app.tests.fake_websocket import FakeWebSocket
from app.tests.ssh_test_server import start_ssh_test_server


async def test_ssh_terminal_roundtrip_resize_and_close(client):
    server = await start_ssh_test_server(password="s3cr3t")
    try:
        host = (
            await client.post(
                "/api/hosts",
                json={
                    "label": "test-echo",
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

        ws = FakeWebSocket()
        async with AsyncSessionLocal() as db:
            task = asyncio.create_task(
                terminal_ws_endpoint(ws, host_id=host["id"], cols=80, rows=24, db=db)
            )

            assert await ws.next_message() == ("json", {"type": "status", "state": "connecting"})

            kind, payload = await ws.next_message()
            assert kind == "json"
            assert payload["type"] == "status"
            assert payload["state"] == "connected"
            assert "note" in payload  # first-use host-key trust note

            await ws.client_send_bytes(b"hello savr")
            assert await ws.next_message() == ("bytes", b"hello savr")

            await ws.client_send_resize(120, 40)  # must not raise or break the session

            await ws.client_send_bytes(b"still-alive")
            assert await ws.next_message() == ("bytes", b"still-alive")

            await ws.client_send_bytes(b"__close__")
            kind, payload = await ws.next_message()
            assert kind == "json"
            assert payload["type"] == "closed"

            await asyncio.wait_for(task, timeout=5)

        host_after = (await client.get(f"/api/hosts/{host['id']}")).json()
        assert host_after["ssh_host_key_fingerprint"] is not None
    finally:
        await server.close()


async def test_ssh_terminal_bad_password_reports_error(client):
    server = await start_ssh_test_server(password="correct-pass")
    try:
        host = (
            await client.post(
                "/api/hosts",
                json={
                    "label": "test-echo",
                    "protocol": "ssh",
                    "hostname": server.host,
                    "port": server.port,
                    "username": "tester",
                    "auth_method": "password",
                    "secret": "wrong-pass",
                },
            )
        ).json()

        from app.db import AsyncSessionLocal
        from app.routers.terminal_ws import terminal_ws as terminal_ws_endpoint

        ws = FakeWebSocket()
        async with AsyncSessionLocal() as db:
            task = asyncio.create_task(
                terminal_ws_endpoint(ws, host_id=host["id"], cols=80, rows=24, db=db)
            )

            assert await ws.next_message() == ("json", {"type": "status", "state": "connecting"})

            kind, payload = await ws.next_message()
            assert kind == "json"
            assert payload["type"] == "error"
            assert payload["fatal"] is True
            assert "auth" in payload["message"].lower()

            await asyncio.wait_for(task, timeout=5)
    finally:
        await server.close()


async def test_ssh_terminal_host_key_mismatch_after_rotation(client):
    server = await start_ssh_test_server(password="s3cr3t")
    try:
        host = (
            await client.post(
                "/api/hosts",
                json={
                    "label": "test-echo",
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

        # First connect: trust-on-first-use pins the server's host key.
        async with AsyncSessionLocal() as db:
            ws = FakeWebSocket()
            task = asyncio.create_task(
                terminal_ws_endpoint(ws, host_id=host["id"], cols=80, rows=24, db=db)
            )
            await ws.next_message()  # connecting
            await ws.next_message()  # connected (+ pin)
            await ws.client_send_bytes(b"__close__")
            await ws.next_message()  # closed
            await asyncio.wait_for(task, timeout=5)

        # Rotate the "device"'s host key by restarting the server (fresh
        # keypair) on the exact same port the host record points at -- must
        # be rejected, not silently trusted.
        old_port = server.port
        await server.close()
        server = await start_ssh_test_server(password="s3cr3t", port=old_port)

        async with AsyncSessionLocal() as db:
            ws2 = FakeWebSocket()
            task2 = asyncio.create_task(
                terminal_ws_endpoint(ws2, host_id=host["id"], cols=80, rows=24, db=db)
            )
            await ws2.next_message()  # connecting
            kind, payload = await ws2.next_message()
            assert kind == "json"
            assert payload["type"] == "error"
            assert "host key" in payload["message"].lower()
            assert payload["fingerprint"]
            await asyncio.wait_for(task2, timeout=5)
    finally:
        await server.close()
