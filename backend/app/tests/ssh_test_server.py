"""In-process asyncssh test server used to integration-test SSHConnector and
the terminal WebSocket bridge without depending on Docker or a system sshd.
"""

from __future__ import annotations

import asyncssh


class _EchoTestServer(asyncssh.SSHServer):
    def __init__(self, password: str) -> None:
        self._password = password

    def begin_auth(self, username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, username: str, password: str) -> bool:
        return password == self._password


async def _echo_process(process: asyncssh.SSHServerProcess) -> None:
    try:
        while True:
            try:
                data = await process.stdin.read(65536)
            except asyncssh.TerminalSizeChanged:
                # A real device's PTY layer absorbs window-change notifications
                # itself; asyncssh's high-level process API instead surfaces
                # them as an exception out of stdin.read(). This dumb echo
                # server doesn't care about terminal size, so just ignore it.
                continue
            if not data or data == b"__close__":
                break
            process.stdout.write(data)
    finally:
        process.exit(0)


class SSHTestServer:
    def __init__(self, port: int, password: str, acceptor: asyncssh.SSHAcceptor) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self.password = password
        self._acceptor = acceptor

    async def close(self) -> None:
        self._acceptor.close()
        await self._acceptor.wait_closed()


async def start_ssh_test_server(password: str = "test-pass", port: int = 0) -> SSHTestServer:
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    acceptor = await asyncssh.listen(
        "127.0.0.1",
        port,
        server_host_keys=[host_key],
        server_factory=lambda: _EchoTestServer(password),
        process_factory=_echo_process,
        # Raw byte passthrough: asyncssh's server-side session otherwise runs a
        # built-in line editor (canonical-mode input + local echo) whenever a
        # PTY is requested, which buffers input until a newline and would
        # never deliver our raw, non-newline-terminated test payloads.
        encoding=None,
        line_editor=False,
    )
    return SSHTestServer(acceptor.get_port(), password, acceptor)
