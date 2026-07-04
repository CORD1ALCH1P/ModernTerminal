from __future__ import annotations

import asyncio

import telnetlib3
from telnetlib3.telopt import NAWS

from app.connectors.base import ClosedCallback, ConnectionFailed, OutputCallback, TerminalConnector

READ_CHUNK = 65536


class TelnetConnector(TerminalConnector):
    """Raw byte passthrough over Telnet. Unlike SSH, login happens
    interactively inside the stream itself (like a raw MobaXterm telnet
    session) -- there is no credential auto-injection here, matching the
    Host schema's "telnet auth is metadata only" decision.
    """

    def __init__(
        self,
        on_output: OutputCallback,
        on_closed: ClosedCallback,
        *,
        hostname: str,
        port: int,
        cols: int,
        rows: int,
    ) -> None:
        super().__init__(on_output, on_closed)
        self._hostname = hostname
        self._port = port
        self._cols = cols
        self._rows = rows

        self._reader: telnetlib3.TelnetReader | None = None
        self._writer: telnetlib3.TelnetWriter | None = None
        self._read_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await telnetlib3.open_connection(
                host=self._hostname,
                port=self._port,
                encoding=False,  # raw bytes, same contract as SSHConnector
                term="xterm-256color",
                cols=self._cols,
                rows=self._rows,
            )
        except OSError as exc:
            raise ConnectionFailed(str(exc)) from exc

        # Lets a later resize() push a live update (see resize() below) rather
        # than only ever answering the server's initial size query.
        self._writer.set_ext_send_callback(NAWS, lambda: (self._rows, self._cols))

        self._read_task = asyncio.create_task(self._pump_output())

    async def _pump_output(self) -> None:
        reason = "remote_closed"
        try:
            assert self._reader is not None
            while True:
                data = await self._reader.read(READ_CHUNK)
                if not data:
                    break
                await self._on_output(data)
        except asyncio.CancelledError:
            return  # closed locally -- close() already handles on_closed if needed
        except OSError:
            reason = "connection_error"
        await self._on_closed(reason)

    async def write(self, data: bytes) -> None:
        assert self._writer is not None
        self._writer.write(data)

    def resize(self, cols: int, rows: int) -> None:
        self._cols, self._rows = cols, rows
        if self._writer is None:
            return
        # telnetlib3 has no public "push a resize" API; this mirrors what its
        # own reference client shell does on SIGWINCH (telnetlib3/client_shell.py):
        # call the private _send_naws() directly, once the NAWS option has
        # actually been negotiated with the server.
        if self._writer.local_option.enabled(NAWS):
            self._writer._send_naws()  # noqa: SLF001

    async def close(self) -> None:
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        self._reader = None
