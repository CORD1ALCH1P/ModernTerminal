"""
Mirrors test_terminal_ws.py's approach (drives terminal_ws directly against a
FakeWebSocket) but for TelnetConnector, against a real in-process telnetlib3
server. No auth/host-key flow to test here -- see the schema/plan decision
that telnet credentials are metadata-only and login happens interactively in
the stream itself.
"""

import asyncio

from app.tests.fake_websocket import FakeWebSocket
from app.tests.telnet_test_server import start_telnet_test_server


async def test_telnet_terminal_roundtrip_resize_and_close(client):
    server = await start_telnet_test_server()
    try:
        host = (
            await client.post(
                "/api/hosts",
                json={
                    "label": "test-telnet-echo",
                    "protocol": "telnet",
                    "hostname": server.host,
                    "port": server.port,
                },
            )
        ).json()
        assert host["port"] == server.port  # explicit port overrides the telnet default (23)

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
            assert payload == {"type": "status", "state": "connected"}  # no TOFU note for telnet

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
    finally:
        await server.close()


async def test_telnet_terminal_unreachable_host_reports_error(client):
    host = (
        await client.post(
            "/api/hosts",
            json={
                "label": "unreachable",
                "protocol": "telnet",
                "hostname": "127.0.0.1",
                "port": 1,  # nothing listens on port 1
            },
        )
    ).json()

    from app.db import AsyncSessionLocal
    from app.routers.terminal_ws import terminal_ws as terminal_ws_endpoint

    ws = FakeWebSocket()
    async with AsyncSessionLocal() as db:
        task = asyncio.create_task(terminal_ws_endpoint(ws, host_id=host["id"], cols=80, rows=24, db=db))

        assert await ws.next_message() == ("json", {"type": "status", "state": "connecting"})

        kind, payload = await ws.next_message()
        assert kind == "json"
        assert payload["type"] == "error"
        assert payload["fatal"] is True

        await asyncio.wait_for(task, timeout=5)
