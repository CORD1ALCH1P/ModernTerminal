from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt_secret, encrypt_secret
from app.models import Folder, Host
from app.schemas import FolderCreate, FolderMove, FolderRename, HostCreate, HostMove, HostOut, HostUpdate

SORT_STEP = 1024


# --- generic ordered-sibling helpers (shared by folders and hosts) --------


async def _siblings(
    db: AsyncSession, model: type[Folder] | type[Host], parent_attr: str, parent_value: int | None
) -> list:
    column = getattr(model, parent_attr)
    condition = column.is_(None) if parent_value is None else column == parent_value
    result = await db.execute(select(model).where(condition).order_by(model.sort_order))
    return list(result.scalars())


async def _renumber(db: AsyncSession, siblings: list) -> None:
    for i, item in enumerate(siblings):
        item.sort_order = (i + 1) * SORT_STEP
    await db.flush()


async def next_sort_order(db: AsyncSession, model, parent_attr: str, parent_value: int | None) -> int:
    siblings = await _siblings(db, model, parent_attr, parent_value)
    return (siblings[-1].sort_order + SORT_STEP) if siblings else SORT_STEP


async def sort_order_for_index(
    db: AsyncSession,
    model,
    parent_attr: str,
    parent_value: int | None,
    index: int,
    exclude_id: int | None = None,
) -> int:
    siblings = await _siblings(db, model, parent_attr, parent_value)
    if exclude_id is not None:
        siblings = [s for s in siblings if s.id != exclude_id]

    n = len(siblings)
    index = max(0, min(index, n))

    if n == 0:
        return SORT_STEP
    if index == 0:
        return siblings[0].sort_order - SORT_STEP
    if index == n:
        return siblings[-1].sort_order + SORT_STEP

    before, after = siblings[index - 1], siblings[index]
    if after.sort_order - before.sort_order > 1:
        return (before.sort_order + after.sort_order) // 2

    await _renumber(db, siblings)
    before, after = siblings[index - 1], siblings[index]
    return (before.sort_order + after.sort_order) // 2


# --- folders -----------------------------------------------------------


async def list_folders(db: AsyncSession) -> list[Folder]:
    result = await db.execute(select(Folder).order_by(Folder.sort_order))
    return list(result.scalars())


async def get_folder_or_404(db: AsyncSession, folder_id: int) -> Folder:
    folder = await db.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Folder {folder_id} not found")
    return folder


async def _assert_folder_exists(db: AsyncSession, folder_id: int | None) -> None:
    if folder_id is not None:
        await get_folder_or_404(db, folder_id)


async def create_folder(db: AsyncSession, payload: FolderCreate) -> Folder:
    await _assert_folder_exists(db, payload.parent_id)
    order = await next_sort_order(db, Folder, "parent_id", payload.parent_id)
    folder = Folder(name=payload.name, parent_id=payload.parent_id, sort_order=order)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def rename_folder(db: AsyncSession, folder_id: int, payload: FolderRename) -> Folder:
    folder = await get_folder_or_404(db, folder_id)
    folder.name = payload.name
    await db.commit()
    await db.refresh(folder)
    return folder


async def _assert_no_cycle(db: AsyncSession, folder_id: int, new_parent_id: int | None) -> None:
    if new_parent_id is None:
        return
    if new_parent_id == folder_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A folder cannot be moved into itself")
    result = await db.execute(select(Folder.id, Folder.parent_id))
    parent_map = dict(result.all())
    current: int | None = new_parent_id
    while current is not None:
        if current == folder_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Cannot move a folder into one of its own descendants"
            )
        current = parent_map.get(current)


async def move_folder(db: AsyncSession, folder_id: int, payload: FolderMove) -> Folder:
    folder = await get_folder_or_404(db, folder_id)
    await _assert_folder_exists(db, payload.parent_id)
    await _assert_no_cycle(db, folder_id, payload.parent_id)

    order = await sort_order_for_index(
        db, Folder, "parent_id", payload.parent_id, payload.index, exclude_id=folder_id
    )
    folder.parent_id = payload.parent_id
    folder.sort_order = order
    await db.commit()
    await db.refresh(folder)
    return folder


async def delete_folder(db: AsyncSession, folder_id: int) -> None:
    folder = await get_folder_or_404(db, folder_id)
    await db.delete(folder)  # DB-level ON DELETE CASCADE removes descendants + hosts
    await db.commit()


# --- hosts -------------------------------------------------------------


def _pack_secret(secret: str | None, passphrase: str | None) -> bytes | None:
    if secret is None:
        return None
    payload = {"secret": secret}
    if passphrase:
        payload["passphrase"] = passphrase
    return encrypt_secret(json.dumps(payload))


def get_decrypted_secret(host: Host) -> dict | None:
    """Decrypt a host's stored secret. Returns {"secret": ..., "passphrase": ...} or None."""
    if host.secret_blob is None:
        return None
    return json.loads(decrypt_secret(host.secret_blob))


def host_to_out(host: Host) -> HostOut:
    return HostOut(
        id=host.id,
        folder_id=host.folder_id,
        label=host.label,
        protocol=host.protocol,
        hostname=host.hostname,
        port=host.port,
        username=host.username,
        auth_method=host.auth_method,
        has_secret=host.secret_blob is not None,
        ssh_host_key_fingerprint=host.ssh_host_key_fingerprint,
        notes=host.notes,
        sort_order=host.sort_order,
        created_at=host.created_at,
        updated_at=host.updated_at,
    )


async def list_hosts(db: AsyncSession) -> list[Host]:
    result = await db.execute(select(Host).order_by(Host.sort_order))
    return list(result.scalars())


async def get_host_or_404(db: AsyncSession, host_id: int) -> Host:
    host = await db.get(Host, host_id)
    if host is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Host {host_id} not found")
    return host


async def create_host(db: AsyncSession, payload: HostCreate) -> Host:
    await _assert_folder_exists(db, payload.folder_id)
    order = await next_sort_order(db, Host, "folder_id", payload.folder_id)
    host = Host(
        label=payload.label,
        folder_id=payload.folder_id,
        protocol=payload.protocol,
        hostname=payload.hostname,
        port=payload.port,
        username=payload.username,
        auth_method=payload.auth_method,
        secret_blob=_pack_secret(payload.secret, payload.passphrase),
        notes=payload.notes,
        sort_order=order,
    )
    db.add(host)
    await db.commit()
    await db.refresh(host)
    return host


async def update_host(db: AsyncSession, host_id: int, payload: HostUpdate) -> Host:
    host = await get_host_or_404(db, host_id)
    data = payload.model_dump(exclude_unset=True, exclude={"secret", "passphrase"})
    for field, value in data.items():
        setattr(host, field, value)

    if "secret" in payload.model_fields_set:
        host.secret_blob = _pack_secret(payload.secret, payload.passphrase)

    protocol = host.protocol
    if protocol == "ssh" and host.auth_method == "none":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "SSH hosts require a non-'none' auth_method")
    if host.auth_method in ("password", "private_key") and host.secret_blob is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"'secret' is required when auth_method={host.auth_method!r}"
        )

    await db.commit()
    await db.refresh(host)
    return host


async def move_host(db: AsyncSession, host_id: int, payload: HostMove) -> Host:
    host = await get_host_or_404(db, host_id)
    await _assert_folder_exists(db, payload.folder_id)

    order = await sort_order_for_index(
        db, Host, "folder_id", payload.folder_id, payload.index, exclude_id=host_id
    )
    host.folder_id = payload.folder_id
    host.sort_order = order
    await db.commit()
    await db.refresh(host)
    return host


async def delete_host(db: AsyncSession, host_id: int) -> None:
    host = await get_host_or_404(db, host_id)
    await db.delete(host)
    await db.commit()


async def accept_host_key(db: AsyncSession, host_id: int, fingerprint: str) -> Host:
    host = await get_host_or_404(db, host_id)
    if host.protocol != "ssh":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Host-key pinning only applies to SSH hosts")
    host.ssh_host_key_fingerprint = fingerprint
    await db.commit()
    await db.refresh(host)
    return host
