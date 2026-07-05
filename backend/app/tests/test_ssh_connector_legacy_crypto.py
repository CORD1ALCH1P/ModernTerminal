"""Simulates an old device (e.g. Cisco IOS 12) that only speaks SSH
algorithms modern asyncssh excludes by default (diffie-hellman-group1-sha1,
CBC ciphers, hmac-md5): connecting without Host.legacy_crypto must fail with
a clear hint, and enabling it must let the same server connect successfully.
"""

import asyncio

from app.tests.fake_websocket import FakeWebSocket
from app.tests.ssh_test_server import start_ssh_test_server


async def test_ssh_legacy_crypto_required_for_old_device(client):
    server = await start_ssh_test_server(
        password="s3cr3t",
        kex_algs=["diffie-hellman-group1-sha1"],
        encryption_algs=["aes128-cbc"],
        mac_algs=["hmac-md5"],
    )
    try:
        host = (
            await client.post(
                "/api/hosts",
                json={
                    "label": "legacy-device",
                    "protocol": "ssh",
                    "hostname": server.host,
                    "port": server.port,
                    "username": "tester",
                    "auth_method": "password",
                    "secret": server.password,
                },
            )
        ).json()
        assert host["legacy_crypto"] is False

        from app.db import AsyncSessionLocal
        from app.routers.terminal_ws import terminal_ws as terminal_ws_endpoint

        # Without legacy_crypto: negotiation fails, with a hint pointing at the fix.
        ws = FakeWebSocket()
        async with AsyncSessionLocal() as db:
            task = asyncio.create_task(
                terminal_ws_endpoint(ws, host_id=host["id"], cols=80, rows=24, db=db)
            )
            assert await ws.next_message() == ("json", {"type": "status", "state": "connecting"})
            kind, payload = await ws.next_message()
            assert kind == "json"
            assert payload["type"] == "error"
            assert "legacy crypto" in payload["message"].lower()
            await asyncio.wait_for(task, timeout=5)

        # Enabling it lets the exact same (still legacy-only) server connect.
        patch_resp = await client.patch(f"/api/hosts/{host['id']}", json={"legacy_crypto": True})
        assert patch_resp.json()["legacy_crypto"] is True

        ws2 = FakeWebSocket()
        async with AsyncSessionLocal() as db:
            task2 = asyncio.create_task(
                terminal_ws_endpoint(ws2, host_id=host["id"], cols=80, rows=24, db=db)
            )
            assert await ws2.next_message() == ("json", {"type": "status", "state": "connecting"})
            kind, payload = await ws2.next_message()
            assert kind == "json"
            assert payload["type"] == "status"
            assert payload["state"] == "connected"

            await ws2.client_send_bytes(b"__close__")
            kind, payload = await ws2.next_message()
            assert kind == "json"
            assert payload["type"] == "closed"

            await asyncio.wait_for(task2, timeout=5)
    finally:
        await server.close()
