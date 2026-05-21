"""Endpoints de bloques del DataNode — solo accesibles desde la VPC."""

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response

from datanode.services import storage
from shared import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.post("/{block_id}", status_code=status.HTTP_201_CREATED)
async def store_block(block_id: str, request: Request, next_node: str | None = None):
    """Recibe bloque binario. Si next_node está presente, lo replica en pipeline."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Cuerpo vacío")

    storage.write_block(block_id, data)
    logger.info("[datanode] Bloque almacenado block_id=%s size=%s", block_id, len(data))

    # Pipeline de replicación hacia el siguiente nodo (IP privada)
    if next_node:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"http://{next_node}/blocks/{block_id}",
                    content=data,
                    headers={"Content-Type": "application/octet-stream"},
                )
                resp.raise_for_status()
                logger.info("[datanode] Bloque replicado a next_node=%s block_id=%s", next_node, block_id)
        except Exception as exc:
            logger.error("[datanode] Fallo replicación a next_node=%s: %s", next_node, exc)
            raise HTTPException(status_code=502, detail=f"Fallo en pipeline hacia {next_node}: {exc}")

    return {"block_id": block_id, "size": len(data)}


@router.get("/{block_id}")
async def get_block(block_id: str):
    try:
        data = storage.read_block(block_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Bloque {block_id} no encontrado")
    return Response(content=data, media_type="application/octet-stream")


@router.delete("/{block_id}")
def delete_block(block_id: str):
    deleted = storage.delete_block(block_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Bloque {block_id} no encontrado")
    return {"deleted": block_id}


@router.get("")
def list_blocks():
    return {"block_ids": storage.list_blocks()}
