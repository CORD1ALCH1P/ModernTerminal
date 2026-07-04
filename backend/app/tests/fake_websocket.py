"""Minimal WebSocket test double implementing just the subset of the
Starlette WebSocket API app.routers.terminal_ws.terminal_ws relies on, backed
by two asyncio.Queues instead of a real socket. Used to drive the endpoint
directly in-process against real SSH/Telnet test servers.
"""

from __future__ import annotations

import asyncio
import json


class FakeWebSocket:
    def __init__(self) -> None:
        self.to_client: asyncio.Queue = asyncio.Queue()
        self.from_client: asyncio.Queue = asyncio.Queue()

    async def accept(self) -> None:
        pass

    async def send_bytes(self, data: bytes) -> None:
        await self.to_client.put(("bytes", data))

    async def send_json(self, obj) -> None:
        await self.to_client.put(("json", obj))

    async def receive(self) -> dict:
        return await self.from_client.get()

    async def close(self, code: int = 1000) -> None:
        await self.from_client.put({"type": "websocket.disconnect"})

    async def client_send_bytes(self, data: bytes) -> None:
        await self.from_client.put({"type": "websocket.receive", "bytes": data})

    async def client_send_resize(self, cols: int, rows: int) -> None:
        await self.from_client.put(
            {
                "type": "websocket.receive",
                "text": json.dumps({"type": "resize", "cols": cols, "rows": rows}),
            }
        )

    async def next_message(self) -> tuple[str, object]:
        return await asyncio.wait_for(self.to_client.get(), timeout=5)
