"""In-process fake Ollama-compatible HTTP server, used to integration-test
OllamaProvider against real HTTP/1.1 chunked streaming rather than mocking the
client library. Implements just enough raw HTTP to serve NDJSON chat streams,
/api/tags, and /api/show.
"""

from __future__ import annotations

import asyncio
import json


class FakeOllamaServer:
    def __init__(
        self, host: str, port: int, server: asyncio.base_events.Server, requests_received: list[dict]
    ) -> None:
        self.host = host
        self.port = port
        self.requests_received = requests_received
        self._server = server

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def close(self) -> None:
        self._server.close()
        await self._server.wait_closed()


async def start_fake_ollama_server(
    chat_turns: list[list[dict]],
    chunk_delay: float = 0.0,
    show_response: dict | None = None,
) -> FakeOllamaServer:
    """`chat_turns` is popped (in order) once per POST /api/chat request; each
    turn is a list of raw dict chunks streamed as NDJSON lines, one write per
    chunk with `chunk_delay` between them, to prove the parser handles
    genuinely separate TCP writes rather than assuming one write == one line.
    `show_response` overrides the default /api/show payload (used to test the
    "model doesn't support tools" capability-warning path).
    """
    turns = list(chat_turns)
    requests_received: list[dict] = []
    show_payload = show_response if show_response is not None else {"capabilities": ["tools", "completion"]}

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            method, path, _ = request_line.decode().split(" ", 2)

            headers: dict[str, str] = {}
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b""):
                    break
                name, _, value = line.decode().partition(":")
                headers[name.strip().lower()] = value.strip()

            body = b""
            length = int(headers.get("content-length", "0"))
            if length:
                body = await reader.readexactly(length)

            if path == "/api/chat" and method == "POST":
                requests_received.append(json.loads(body))
                await _write_chat_response(writer, turns.pop(0) if turns else [], chunk_delay)
            elif path == "/api/tags" and method == "GET":
                await _write_json_response(writer, {"models": [{"name": "qwen3:8b"}]})
            elif path == "/api/show" and method == "POST":
                await _write_json_response(writer, show_payload)
            else:
                await _write_json_response(writer, {"error": "not found"}, status=404)
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return FakeOllamaServer("127.0.0.1", port, server, requests_received)


async def _write_chat_response(writer: asyncio.StreamWriter, chunks: list[dict], delay: float) -> None:
    writer.write(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/x-ndjson\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n"
    )
    for chunk in chunks:
        line = (json.dumps(chunk) + "\n").encode()
        writer.write(f"{len(line):x}\r\n".encode() + line + b"\r\n")
        await writer.drain()
        if delay:
            await asyncio.sleep(delay)
    writer.write(b"0\r\n\r\n")
    await writer.drain()


async def _write_json_response(writer: asyncio.StreamWriter, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode()
    reason = "OK" if status == 200 else "Not Found"
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\n".encode()
        + b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    await writer.drain()
