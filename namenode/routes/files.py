"""Endpoints de namespace de archivos: put, get, ls, mkdir, rm, rmdir."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from namenode.database import get_db
from namenode.models import Block, FileEntry, User
from namenode.security import get_current_user
from namenode.services.block_manager import allocate_blocks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["files"])


class PutRequest(BaseModel):
    path: str
    size_bytes: int


class MkdirRequest(BaseModel):
    path: str


@router.post("/put")
def put_file(
    body: PutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = db.query(FileEntry).filter_by(owner_id=user.id, path=body.path).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Ya existe un archivo en {body.path}")

    file_entry = FileEntry(
        path=body.path,
        owner_id=user.id,
        size_bytes=body.size_bytes,
        is_directory=False,
        committed=False,
    )
    db.add(file_entry)
    db.flush()

    try:
        blocks = allocate_blocks(db, file_entry, body.size_bytes)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc))

    logger.info("[files] PUT file path=%s size=%s user=%s blocks=%s",
                body.path, body.size_bytes, user.username, len(blocks))
    # Solo devolver block_ids al cliente (sin IPs de DataNodes)
    return {"path": body.path, "blocks": [{"block_id": b["block_id"], "block_index": b["block_index"]} for b in blocks]}


@router.post("/commit/{path:path}")
def commit_file(
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_entry = db.query(FileEntry).filter_by(owner_id=user.id, path=f"/{path}").first()
    if not file_entry:
        file_entry = db.query(FileEntry).filter_by(owner_id=user.id, path=path).first()
    if not file_entry:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    file_entry.committed = True
    db.commit()
    return {"committed": True, "path": path}


@router.get("/get/{path:path}")
def get_file(
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_entry = (
        db.query(FileEntry)
        .filter_by(owner_id=user.id, path=f"/{path}", is_directory=False)
        .first()
    )
    if not file_entry:
        file_entry = db.query(FileEntry).filter_by(owner_id=user.id, path=path, is_directory=False).first()
    if not file_entry:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    blocks = (
        db.query(Block)
        .filter_by(file_id=file_entry.id)
        .order_by(Block.block_index)
        .all()
    )
    return {
        "path": file_entry.path,
        "size_bytes": file_entry.size_bytes,
        "blocks": [{"block_id": b.block_id, "block_index": b.block_index} for b in blocks],
    }


@router.get("/ls/{path:path}")
def ls(
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    prefix = f"/{path}".rstrip("/")
    entries = db.query(FileEntry).filter(
        FileEntry.owner_id == user.id,
        FileEntry.path.like(f"{prefix}/%"),
    ).all()
    return [
        {"path": e.path, "is_directory": e.is_directory, "size_bytes": e.size_bytes}
        for e in entries
    ]


@router.post("/mkdir")
def mkdir(
    body: MkdirRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = db.query(FileEntry).filter_by(owner_id=user.id, path=body.path).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe")
    db.add(FileEntry(path=body.path, owner_id=user.id, is_directory=True, committed=True))
    db.commit()
    return {"created": body.path}


@router.delete("/rm/{path:path}")
def rm(
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_entry = db.query(FileEntry).filter_by(owner_id=user.id, path=f"/{path}", is_directory=False).first()
    if not file_entry:
        file_entry = db.query(FileEntry).filter_by(owner_id=user.id, path=path, is_directory=False).first()
    if not file_entry:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    # Recopilar (DataNode, block_id) antes de que el cascade borre los metadatos
    targets = [
        (replica.datanode.address, replica.datanode.port, block.block_id)
        for block in file_entry.blocks
        for replica in block.replicas
    ]

    deleted_path = file_entry.path
    db.delete(file_entry)
    db.commit()

    # Borrado físico de bloques en los DataNodes (best-effort, por IP privada)
    for address, port, block_id in targets:
        try:
            httpx.delete(f"http://{address}:{port}/blocks/{block_id}", timeout=5)
        except Exception as exc:
            logger.warning("[files] No se pudo borrar bloque %s en %s:%s: %s",
                           block_id, address, port, exc)

    logger.info("[files] RM file path=%s user=%s bloques=%s", deleted_path, user.username, len(targets))
    return {"deleted": deleted_path}


@router.delete("/rmdir/{path:path}")
def rmdir(
    path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    dir_entry = db.query(FileEntry).filter_by(owner_id=user.id, path=f"/{path}", is_directory=True).first()
    if not dir_entry:
        dir_entry = db.query(FileEntry).filter_by(owner_id=user.id, path=path, is_directory=True).first()
    if not dir_entry:
        raise HTTPException(status_code=404, detail="Directorio no encontrado")

    children = (
        db.query(FileEntry)
        .filter(
            FileEntry.owner_id == user.id,
            FileEntry.path.like(f"{dir_entry.path}/%"),
        )
        .count()
    )
    if children > 0:
        raise HTTPException(status_code=409, detail="El directorio no está vacío")

    deleted_path = dir_entry.path
    db.delete(dir_entry)
    db.commit()
    logger.info("[files] RMDIR path=%s user=%s", deleted_path, user.username)
    return {"deleted": deleted_path}
