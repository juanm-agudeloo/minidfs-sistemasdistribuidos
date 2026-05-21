"""Proxy streaming de bloques entre cliente ↔ NameNode ↔ DataNodes (por IP privada)."""

import logging

import httpx
from fastapi import HTTPException

from namenode.models import Block, BlockReplica, DataNodeStatus
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
TIMEOUT = 60


async def proxy_put(db: Session, block_id: str, data: bytes) -> None:
    """Envía bloque al DataNode primario con pipeline de replicación."""
    block = db.query(Block).filter(Block.block_id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail=f"block_id {block_id} no registrado")

    replicas = (
        db.query(BlockReplica)
        .filter(BlockReplica.block_id == block.id)
        .join(BlockReplica.datanode)
        .filter_by(status=DataNodeStatus.ACTIVE)
        .all()
    )
    if not replicas:
        raise HTTPException(status_code=503, detail="Sin DataNodes activos para este bloque")

    primary = replicas[0].datanode
    next_nodes = [f"{r.datanode.address}:{r.datanode.port}" for r in replicas[1:]]
    next_node_param = next_nodes[0] if next_nodes else None

    url = f"http://{primary.address}:{primary.port}/blocks/{block_id}"
    params = {"next_node": next_node_param} if next_node_param else {}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, content=data, params=params,
                                 headers={"Content-Type": "application/octet-stream"})
        resp.raise_for_status()

    # Actualizar tamaño real del bloque
    block.size_bytes = len(data)
    db.commit()
    logger.info("[block_proxy] PUT OK block_id=%s size=%s primary=%s:%s",
                block_id, len(data), primary.address, primary.port)


async def proxy_get(db: Session, block_id: str) -> bytes:
    """Recupera bloque desde cualquier réplica activa (failover automático)."""
    block = db.query(Block).filter(Block.block_id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail=f"block_id {block_id} no encontrado")

    replicas = (
        db.query(BlockReplica)
        .filter(BlockReplica.block_id == block.id)
        .join(BlockReplica.datanode)
        .filter_by(status=DataNodeStatus.ACTIVE)
        .all()
    )
    if not replicas:
        raise HTTPException(status_code=503, detail="Sin réplicas activas para este bloque")

    last_exc = None
    for replica in replicas:
        dn = replica.datanode
        url = f"http://{dn.address}:{dn.port}/blocks/{block_id}"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                logger.info("[block_proxy] GET OK block_id=%s from=%s:%s", block_id, dn.address, dn.port)
                return resp.content
        except Exception as exc:
            logger.warning("[block_proxy] Fallo en réplica %s:%s: %s", dn.address, dn.port, exc)
            last_exc = exc

    raise HTTPException(status_code=502, detail=f"Todas las réplicas fallaron: {last_exc}")
