from __future__ import annotations

import abc
from collections.abc import Awaitable, Callable

OutputCallback = Callable[[bytes], Awaitable[None]]
ClosedCallback = Callable[[str], Awaitable[None]]


class ConnectorError(Exception):
    """Base for connector failures the WS layer surfaces as a control message."""


class ConnectionFailed(ConnectorError):
    """Could not reach or establish a transport-level connection to the host."""


class AuthenticationFailed(ConnectorError):
    """The remote host rejected the supplied credentials."""


class HostKeyMismatch(ConnectorError):
    """The server's host key doesn't match the pinned fingerprint on file --
    either a MITM or a legitimately rotated key. The caller must resolve this
    via POST /api/hosts/{id}/accept-host-key before a retry can succeed."""

    def __init__(self, fingerprint: str | None) -> None:
        super().__init__(f"host key mismatch (observed: {fingerprint})")
        self.fingerprint = fingerprint


class TerminalConnector(abc.ABC):
    """One instance = one live interactive terminal session (SSH shell or
    Telnet session), bridged to a single WebSocket connection.

    Part-2 extension point: a future AI agent can wrap a connector instance
    (e.g. a decorator that tees output through an additional callback, and/or
    injects writes) without changing SSHConnector/TelnetConnector themselves.
    """

    def __init__(self, on_output: OutputCallback, on_closed: ClosedCallback) -> None:
        self._on_output = on_output
        self._on_closed = on_closed

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establish the session and start forwarding output via on_output.

        Raises a ConnectorError subclass on failure.
        """

    @abc.abstractmethod
    async def write(self, data: bytes) -> None:
        """Send bytes typed by the user (or, later, an agent) to the session."""

    @abc.abstractmethod
    def resize(self, cols: int, rows: int) -> None:
        """Adjust the remote PTY/terminal size."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Tear down the connection from our side. Must be safe to call twice."""
