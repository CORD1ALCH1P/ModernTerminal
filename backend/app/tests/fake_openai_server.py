"""In-process fake OpenAI-compatible HTTP server, used to integration-test
OpenAICompatibleProvider against a real SSE stream over real HTTP/1.1 chunked
transfer-encoding rather than mocking the client library. Implements just
enough raw HTTP to serve a /chat/completions SSE stream.
"""

from __future__ import annotations

import asyncio
import json


class FakeOpenAIServer:
    def __init__(
        self, host: str, port: int, server: asyncio.base_events.Server, requests_received: list[dict]
    ) -> None:
        self.host = host
        self.port = port
        self.requests_received = requests_received
        self.headers_received: list[dict[str, str]] = []
        self._server = server

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def close(self) -> None:
        self._server.close()
        await self._server.wait_closed()


async def start_fake_openai_server(
    chat_turns: list[list[dict]],
    chunk_delay: float = 0.0,
    error_response: tuple[int, dict] | None = None,
) -> FakeOpenAIServer:
    """`chat_turns` is popped (in order) once per POST /chat/completions
    request; each turn is a list of raw SSE chunk dicts (OpenAI's streaming
    `chat.completion.chunk` shape), one write per chunk with `chunk_delay`
    between them, terminated by a literal "data: [DONE]". `error_response`,
    if set, makes every /chat/completions request return that
    (status_code, json_body) instead -- used to test the model-not-found /
    generic-error paths.
    """
    turns = list(chat_turns)
    requests_received: list[dict] = []
    headers_received: list[dict[str, str]] = []

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

            if path == "/chat/completions" and method == "POST":
                requests_received.append(json.loads(body))
                headers_received.append(headers)
                if error_response is not None:
                    status, error_body = error_response
                    await _write_json_response(writer, error_body, status=status)
                else:
                    await _write_sse_response(writer, turns.pop(0) if turns else [], chunk_delay)
            else:
                await _write_json_response(writer, {"error": {"message": "not found"}}, status=404)
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    fake = FakeOpenAIServer("127.0.0.1", port, server, requests_received)
    fake.headers_received = headers_received
    return fake


async def _write_sse_response(writer: asyncio.StreamWriter, chunks: list[dict], delay: float) -> None:
    writer.write(
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/event-stream\r\n"
        b"Transfer-Encoding: chunked\r\n"
        b"\r\n"
    )
    for chunk in chunks:
        line = f"data: {json.dumps(chunk)}\n\n".encode()
        writer.write(f"{len(line):x}\r\n".encode() + line + b"\r\n")
        await writer.drain()
        if delay:
            await asyncio.sleep(delay)
    done_line = b"data: [DONE]\n\n"
    writer.write(f"{len(done_line):x}\r\n".encode() + done_line + b"\r\n")
    writer.write(b"0\r\n\r\n")
    await writer.drain()


async def _write_json_response(writer: asyncio.StreamWriter, payload: dict, status: int) -> None:
    body = json.dumps(payload).encode()
    reason = {404: "Not Found", 401: "Unauthorized", 500: "Internal Server Error"}.get(status, "Error")
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\n".encode()
        + b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    await writer.drain()
