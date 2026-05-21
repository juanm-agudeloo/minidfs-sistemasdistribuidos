"""Lógica de asignación de DataNodes para nuevos bloques."""

import logging
import uuid

from sqlalchemy.orm import Session

from namenode.models import Block, BlockReplica, DataNodeStatus, FileEntry
from shared import config

logger = logging.getLogger(__name__)


def select_datanodes(db: Session, count: int = None) -> list:
    """Selecciona DataNodes activos ordenados por menor carga."""
    n = count or config.REPLICATION_FACTOR
    nodes = (
        db.query(__import__("namenode.models", fromlist=["DataNode"]).DataNode)
        .filter_by(status=DataNodeStatus.ACTIVE)
        .filter(__import__("namenode.models", fromlist=["DataNode"]).DataNode.free_space_bytes >= config.BLOCK_SIZE)
        .order_by(__import__("namenode.models", fromlist=["DataNode"]).DataNode.blocks_count.asc())
        .limit(n)
        .all()
    )
    if len(nodes) < n:
        raise ValueError(f"No hay suficientes DataNodes activos (necesito {n}, hay {len(nodes)})")
    return nodes


def allocate_blocks(db: Session, file_entry: FileEntry, file_size: int) -> list[dict]:
    """Crea registros Block en la BD y devuelve la lista de asignaciones."""
    import math
    n_blocks = max(1, math.ceil(file_size / config.BLOCK_SIZE))
    result = []

    for i in range(n_blocks):
        nodes = select_datanodes(db)
        block_id = str(uuid.uuid4())
        block = Block(
            block_id=block_id,
            file_id=file_entry.id,
            block_index=i,
            size_bytes=0,  # se actualiza al confirmar
        )
        db.add(block)
        db.flush()  # obtener block.id

        for node in nodes:
            db.add(BlockReplica(block_id=block.id, datanode_id=node.id))

        result.append({
            "block_id": block_id,
            "block_index": i,
            "primary": {"address": nodes[0].address, "port": nodes[0].port},
            "replicas": [{"address": n.address, "port": n.port} for n in nodes[1:]],
        })

    db.commit()
    logger.info("[block_manager] %s bloques asignados para file_id=%s", n_blocks, file_entry.id)
    return result
