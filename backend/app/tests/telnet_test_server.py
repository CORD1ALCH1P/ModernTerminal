"""In-process telnetlib3 test server used to integration-test TelnetConnector
and the terminal WebSocket bridge without depending on Docker or a real
telnet daemon.
"""

from __future__ import annotations

import telnetlib3


async def _echo_shell(reader, writer) -> None:
    try:
        while True:
            data = await reader.read(65536)
            if not data or data == b"__close__":
                break
            writer.write(data)
    finally:
        writer.close()


class TelnetTestServer:
    def __init__(self, port: int, server: telnetlib3.Server) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self._server = server

    async def close(self) -> None:
        self._server.close()
        await self._server.wait_closed()


async def start_telnet_test_server(port: int = 0) -> TelnetTestServer:
    server = await telnetlib3.create_server(
        host="127.0.0.1",
        port=port,
        shell=_echo_shell,
        encoding=False,
    )
    bound_port = server.sockets[0].getsockname()[1]
    return TelnetTestServer(bound_port, server)
