from __future__ import annotations

import asyncio
import base64
import hashlib

import asyncssh
import asyncssh.encryption
import asyncssh.kex
import asyncssh.mac

from app.connectors.base import (
    AuthenticationFailed,
    ClosedCallback,
    ConnectionFailed,
    HostKeyMismatch,
    OutputCallback,
    TerminalConnector,
)

READ_CHUNK = 65536

# Algorithms modern asyncssh excludes from its default-enabled lists because
# they're weak by today's standards, but that old devices -- e.g. Cisco IOS
# 12, which predates CTR/GCM ciphers and SHA-2 key exchange entirely -- may
# only ever speak. Appended after the secure defaults (never replacing them)
# so a capable peer still negotiates a modern algorithm; these only kick in
# when nothing stronger matches.
LEGACY_KEX_ALGS = ["diffie-hellman-group-exchange-sha1", "diffie-hellman-group1-sha1"]
LEGACY_ENCRYPTION_ALGS = ["aes256-cbc", "aes192-cbc", "aes128-cbc", "3des-cbc"]
LEGACY_MAC_ALGS = ["hmac-md5"]


def fingerprint_of(key: asyncssh.SSHKey) -> str:
    digest = hashlib.sha256(key.public_data).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


class _PinnedHostKeyClient(asyncssh.SSHClient):
    """Implements TOFU host-key pinning.

    asyncssh only calls validate_host_public_key() when its own internal
    trusted-key set is non-None and doesn't already contain the key (see
    SSHClientConnection._validate_host_key in asyncssh's source) -- passing
    known_hosts=None, despite what the "validate_host_public_key" docs alone
    suggest, disables that internal check entirely (unconditional trust,
    callback never invoked). SSHConnector.connect() instead passes the
    documented all-empty 7-tuple form of `known_hosts`, which keeps the
    internal trusted-key set non-None but empty, so this callback is always
    consulted and is the sole authority, with pins kept in
    Host.ssh_host_key_fingerprint.
    """

    def __init__(self, pinned_fingerprint: str | None, holder: dict[str, str | None]) -> None:
        self._pinned = pinned_fingerprint
        self._holder = holder

    def validate_host_public_key(self, host: str, addr: str, port: int, key: asyncssh.SSHKey) -> bool:
        fp = fingerprint_of(key)
        self._holder["fingerprint"] = fp
        if self._pinned is None:
            return True  # trust-on-first-use; caller pins it after connect() succeeds
        return fp == self._pinned


class SSHConnector(TerminalConnector):
    def __init__(
        self,
        on_output: OutputCallback,
        on_closed: ClosedCallback,
        *,
        hostname: str,
        port: int,
        username: str | None,
        auth_method: str,
        secret: str | None,
        passphrase: str | None,
        pinned_fingerprint: str | None,
        cols: int,
        rows: int,
        legacy_crypto: bool = False,
    ) -> None:
        super().__init__(on_output, on_closed)
        self._hostname = hostname
        self._port = port
        self._username = username
        self._auth_method = auth_method
        self._secret = secret
        self._passphrase = passphrase
        self._pinned_fingerprint = pinned_fingerprint
        self._cols = cols
        self._rows = rows
        self._legacy_crypto = legacy_crypto

        self._conn: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess | None = None
        self._read_task: asyncio.Task[None] | None = None

        # Populated by connect(): the fingerprint asyncssh actually observed,
        # and, only on a first-use trust decision, the value the caller should
        # persist to Host.ssh_host_key_fingerprint.
        self.observed_fingerprint: str | None = None
        self.newly_trusted_fingerprint: str | None = None

    async def connect(self) -> None:
        holder: dict[str, str | None] = {"fingerprint": None}

        def client_factory() -> _PinnedHostKeyClient:
            return _PinnedHostKeyClient(self._pinned_fingerprint, holder)

        connect_kwargs: dict[str, object] = {
            "host": self._hostname,
            "port": self._port,
            # known_hosts=None disables asyncssh's OWN validation entirely
            # (unconditional trust) rather than deferring to our callback --
            # confirmed by reading asyncssh's connection.py: it only consults
            # validate_host_public_key() when self._trusted_host_keys is not
            # None. Passing the documented "pre-parsed, all-empty" 7-tuple
            # form instead keeps _trusted_host_keys as an empty (not None)
            # container, so every key falls through to our TOFU callback.
            "known_hosts": ([], [], [], [], [], [], []),
            "server_host_key_algs": "default",
            "client_factory": client_factory,
        }
        if self._username:
            connect_kwargs["username"] = self._username

        if self._auth_method == "password":
            connect_kwargs["password"] = self._secret
            connect_kwargs["client_keys"] = []
        elif self._auth_method == "private_key":
            key = asyncssh.import_private_key(self._secret or "", passphrase=self._passphrase)
            connect_kwargs["client_keys"] = [key]
            connect_kwargs["password"] = None

        if self._legacy_crypto:
            # Appended after (not instead of) the secure defaults, so a
            # capable peer still negotiates a modern algorithm -- these are
            # only reached as a fallback for devices too old to offer anything
            # else (e.g. Cisco IOS 12: diffie-hellman-group1-sha1 key
            # exchange, CBC-only ciphers, no SHA-2 MACs).
            default_kex = [a.decode() for a in asyncssh.kex.get_default_kex_algs()]
            default_enc = [a.decode() for a in asyncssh.encryption.get_default_encryption_algs()]
            default_mac = [a.decode() for a in asyncssh.mac.get_default_mac_algs()]
            connect_kwargs["kex_algs"] = default_kex + LEGACY_KEX_ALGS
            connect_kwargs["encryption_algs"] = default_enc + LEGACY_ENCRYPTION_ALGS
            connect_kwargs["mac_algs"] = default_mac + LEGACY_MAC_ALGS

        try:
            self._conn = await asyncssh.connect(**connect_kwargs)
        except asyncssh.HostKeyNotVerifiable as exc:
            raise HostKeyMismatch(holder["fingerprint"]) from exc
        except asyncssh.PermissionDenied as exc:
            raise AuthenticationFailed(str(exc)) from exc
        except asyncssh.KeyExchangeFailed as exc:
            # asyncssh's own message dumps the full raw client/server algorithm
            # lists -- meaningless to an end user and not actionable, so it's
            # dropped in favor of a plain explanation of what this means and
            # what to do about it (mirrors the ModelNotFound-style cleanup
            # elsewhere in this codebase: never surface a raw negotiation
            # dump when a clear, actionable message is possible instead).
            message = "No matching key exchange, cipher, or MAC algorithm with the remote host."
            if not self._legacy_crypto:
                message += (
                    " This is common with old devices (e.g. Cisco IOS 12) that only "
                    "support outdated algorithms -- try enabling 'Legacy crypto "
                    "compatibility' for this host."
                )
            raise ConnectionFailed(message) from exc
        except (OSError, asyncssh.Error) as exc:
            raise ConnectionFailed(str(exc)) from exc

        self.observed_fingerprint = holder["fingerprint"]
        if self._pinned_fingerprint is None:
            self.newly_trusted_fingerprint = holder["fingerprint"]

        try:
            self._process = await self._conn.create_process(
                term_type="xterm-256color",
                term_size=(self._cols, self._rows),
                encoding=None,
            )
        except (OSError, asyncssh.Error) as exc:
            raise ConnectionFailed(str(exc)) from exc

        self._read_task = asyncio.create_task(self._pump_output())

    async def _pump_output(self) -> None:
        reason = "remote_closed"
        try:
            assert self._process is not None
            while True:
                data = await self._process.stdout.read(READ_CHUNK)
                if not data:
                    break
                await self._on_output(data)
        except asyncssh.Error:
            reason = "connection_error"
        except asyncio.CancelledError:
            return  # closed locally -- close() already handles on_closed if needed
        await self._on_closed(reason)

    async def write(self, data: bytes) -> None:
        assert self._process is not None
        self._process.stdin.write(data)

    def resize(self, cols: int, rows: int) -> None:
        assert self._process is not None
        self._process.change_terminal_size(cols, rows)

    async def close(self) -> None:
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        if self._process is not None:
            self._process.close()
            self._process = None
        if self._conn is not None:
            self._conn.close()
            try:
                await self._conn.wait_closed()
            except asyncssh.Error:
                pass
            self._conn = None
