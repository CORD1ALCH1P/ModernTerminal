from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.db import get_db
from app.schemas import AcceptHostKey, HostCreate, HostMove, HostOut, HostUpdate

router = APIRouter(prefix="/api/hosts", tags=["hosts"])


@router.get("", response_model=list[HostOut])
async def list_hosts(db: AsyncSession = Depends(get_db)) -> list[HostOut]:
    hosts = await crud.list_hosts(db)
    return [crud.host_to_out(h) for h in hosts]


@router.get("/{host_id}", response_model=HostOut)
async def get_host(host_id: int, db: AsyncSession = Depends(get_db)) -> HostOut:
    host = await crud.get_host_or_404(db, host_id)
    return crud.host_to_out(host)


@router.post("", response_model=HostOut, status_code=status.HTTP_201_CREATED)
async def create_host(payload: HostCreate, db: AsyncSession = Depends(get_db)) -> HostOut:
    host = await crud.create_host(db, payload)
    return crud.host_to_out(host)


@router.patch("/{host_id}", response_model=HostOut)
async def update_host(host_id: int, payload: HostUpdate, db: AsyncSession = Depends(get_db)) -> HostOut:
    host = await crud.update_host(db, host_id, payload)
    return crud.host_to_out(host)


@router.patch("/{host_id}/move", response_model=HostOut)
async def move_host(host_id: int, payload: HostMove, db: AsyncSession = Depends(get_db)) -> HostOut:
    host = await crud.move_host(db, host_id, payload)
    return crud.host_to_out(host)


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_host(host_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await crud.delete_host(db, host_id)


@router.post("/{host_id}/accept-host-key", response_model=HostOut)
async def accept_host_key(
    host_id: int, payload: AcceptHostKey, db: AsyncSession = Depends(get_db)
) -> HostOut:
    host = await crud.accept_host_key(db, host_id, payload.fingerprint)
    return crud.host_to_out(host)
