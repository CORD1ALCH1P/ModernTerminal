from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.db import get_db
from app.schemas import FolderCreate, FolderMove, FolderOut, FolderRename

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("", response_model=list[FolderOut])
async def list_folders(db: AsyncSession = Depends(get_db)) -> list[FolderOut]:
    folders = await crud.list_folders(db)
    return [FolderOut.model_validate(f) for f in folders]


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
async def create_folder(payload: FolderCreate, db: AsyncSession = Depends(get_db)) -> FolderOut:
    folder = await crud.create_folder(db, payload)
    return FolderOut.model_validate(folder)


@router.patch("/{folder_id}", response_model=FolderOut)
async def rename_folder(
    folder_id: int, payload: FolderRename, db: AsyncSession = Depends(get_db)
) -> FolderOut:
    folder = await crud.rename_folder(db, folder_id, payload)
    return FolderOut.model_validate(folder)


@router.patch("/{folder_id}/move", response_model=FolderOut)
async def move_folder(folder_id: int, payload: FolderMove, db: AsyncSession = Depends(get_db)) -> FolderOut:
    folder = await crud.move_folder(db, folder_id, payload)
    return FolderOut.model_validate(folder)


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(folder_id: int, db: AsyncSession = Depends(get_db)) -> None:
    await crud.delete_folder(db, folder_id)
