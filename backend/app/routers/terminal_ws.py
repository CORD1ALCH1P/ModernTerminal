from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.ai import session_registry
from app.connectors.base import (
    AuthenticationFailed,
    ClosedCallback,
    ConnectionFailed,
    ConnectorError,
    HostKeyMismatch,
    OutputCallback,
    TerminalConnector,
)
from app.connectors.ssh_connector import SSHConnector
from app.connectors.telnet_connector import TelnetConnector
from app.db import get_db
from app.models import Host

router = APIRouter(prefix="/api/ws", tags=["terminal"])


def _build_connector(
    host: Host, cols: int, rows: int, on_output: OutputCallback, on_closed: ClosedCallback
) -> TerminalConnector:
    if host.protocol == "ssh":
        secret = crud.get_decrypted_secret(host) or {}
        return SSHConnector(
            on_output,
            on_closed,
            hostname=host.hostname,
            port=host.port,
            username=host.username,
            auth_method=host.auth_method,
            secret=secret.get("secret"),
            passphrase=secret.get("passphrase"),
            pinned_fingerprint=host.ssh_host_key_fingerprint,
            cols=cols,
            rows=rows,
        )
    if host.protocol == "telnet":
        return TelnetConnector(
            on_output,
            on_closed,
            hostname=host.hostname,
            port=host.port,
            cols=cols,
            rows=rows,
        )
    raise NotImplementedError(f"protocol {host.protocol!r} is not supported")


@router.websocket("/terminal")
async def terminal_ws(
    websocket: WebSocket,
    host_id: int = Query(...),
    cols: int = Query(80, ge=1, le=1000),
    rows: int = Query(24, ge=1, le=1000),
    session_id: str | None = Query(None),  # AI copilot correlation id (frontend tab UUID)
    db: AsyncSession = Depends(get_db),
) -> None:
    await websocket.accept()

    host = await db.get(Host, host_id)
    if host is None:
        await websocket.send_json({"type": "error", "message": f"Host {host_id} not found", "fatal": True})
        await websocket.close()
        return

    async def on_output(data: bytes) -> None:
        await websocket.send_bytes(data)
        if session_id:
            session = session_registry.get(session_id)
            if session:
                session.feed(data)

    async def on_closed(reason: str) -> None:
        await websocket.send_json({"type": "closed", "reason": reason})
        await websocket.close()

    try:
        connector = _build_connector(host, cols, rows, on_output, on_closed)
    except NotImplementedError as exc:
        await websocket.send_json({"type": "error", "message": str(exc), "fatal": True})
        await websocket.close()
        return

    await websocket.send_json({"type": "status", "state": "connecting"})

    try:
        await connector.connect()
    except HostKeyMismatch as exc:
        await websocket.send_json(
            {
                "type": "error",
                "message": (
                    f"Host key changed (observed {exc.fingerprint}). If this is expected "
                    "(e.g. the device was replaced/reimaged), accept the new key, then retry."
                ),
                "fatal": True,
                "fingerprint": exc.fingerprint,
            }
        )
        await websocket.close()
        return
    except AuthenticationFailed:
        await websocket.send_json({"type": "error", "message": "Authentication failed", "fatal": True})
        await websocket.close()
        return
    except (ConnectionFailed, ConnectorError) as exc:
        await websocket.send_json({"type": "error", "message": str(exc), "fatal": True})
        await websocket.close()
        return

    if session_id:
        session_registry.register(session_id, connector)

    if isinstance(connector, SSHConnector) and connector.newly_trusted_fingerprint:
        host.ssh_host_key_fingerprint = connector.newly_trusted_fingerprint
        await db.commit()
        await websocket.send_json(
            {
                "type": "status",
                "state": "connected",
                "note": f"Host key trusted on first use: {connector.newly_trusted_fingerprint}",
            }
        )
    else:
        await websocket.send_json({"type": "status", "state": "connected"})

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            data = message.get("bytes")
            if data is not None:
                await connector.write(data)
                continue

            text = message.get("text")
            if text is None:
                continue
            try:
                control = json.loads(text)
            except ValueError:
                continue
            if control.get("type") == "resize":
                new_cols, new_rows = control.get("cols"), control.get("rows")
                if isinstance(new_cols, int) and isinstance(new_rows, int):
                    connector.resize(new_cols, new_rows)
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: Starlette raises this if receive() is called after the
        # connection has already been torn down by a concurrent on_closed().
        pass
    finally:
        await connector.close()
        if session_id:
            session_registry.unregister(session_id)
