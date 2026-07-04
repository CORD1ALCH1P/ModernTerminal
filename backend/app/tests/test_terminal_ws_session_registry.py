"""Verifies terminal_ws.py's additive session_registry wiring: passing a
session_id registers the live connector (and tees output into scrollback) for
app/ai to find later, and cleans it up when the WS closes. Omitting session_id
(every Part-1 test) must keep working exactly as before -- proven by the rest
of the suite staying green, not re-tested here.
"""

import asyncio

from app.ai import session_registry
from app.tests.fake_websocket import FakeWebSocket
from app.tests.ssh_test_server import start_ssh_test_server


async def test_session_registers_on_connect_and_feeds_scrollback(client):
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
        session_id = "tab-abc-123"
        async with AsyncSessionLocal() as db:
            task = asyncio.create_task(
                terminal_ws_endpoint(
                    ws, host_id=host["id"], cols=80, rows=24, session_id=session_id, db=db
                )
            )

            await ws.next_message()  # connecting
            await ws.next_message()  # connected

            assert session_registry.get(session_id) is not None

            await ws.client_send_bytes(b"hello")
            await ws.next_message()  # echoed bytes

            session = session_registry.get(session_id)
            assert session is not None
            assert b"hello" in session.tail(1000)

            await ws.client_send_bytes(b"__close__")
            await ws.next_message()  # closed
            await asyncio.wait_for(task, timeout=5)

        assert session_registry.get(session_id) is None
    finally:
        await server.close()


async def test_no_session_id_means_no_registration(client):
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
            await ws.next_message()  # connecting
            await ws.next_message()  # connected

            assert session_registry.get("some-random-id-never-passed") is None

            await ws.client_send_bytes(b"__close__")
            await ws.next_message()  # closed
            await asyncio.wait_for(task, timeout=5)
    finally:
        await server.close()
