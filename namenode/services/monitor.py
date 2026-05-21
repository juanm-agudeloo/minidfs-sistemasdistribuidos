"""Monitor en background: detecta DataNodes caídos y re-replica bloques sub-replicados."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from namenode.database import SessionLocal
from namenode.models import Block, BlockReplica, DataNode, DataNodeStatus
from shared import config

logger = logging.getLogger(__name__)

REREPLICATION_TIMEOUT = 60

_monitor_task: asyncio.Task | None = None


def _check_dead_nodes() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        timeout = timedelta(seconds=config.HEARTBEAT_TIMEOUT)
        nodes = db.query(DataNode).filter(DataNode.status == DataNodeStatus.ACTIVE).all()

        for node in nodes:
            if node.last_heartbeat is None:
                continue
            last = node.last_heartbeat
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            elapsed = now - last
            if elapsed > timeout:
                node.status = DataNodeStatus.DEAD
                logger.warning(
                    "[%s] DataNode marcado DEAD node_id=%s address=%s "
                    "sin heartbeat por %.1fs (timeout=%ss)",
                    now.isoformat(),
                    node.node_id,
                    node.address,
                    elapsed.total_seconds(),
                    config.HEARTBEAT_TIMEOUT,
                )
        db.commit()
    finally:
        db.close()


def _fetch_block(dn: DataNode, block_id: str) -> bytes:
    resp = httpx.get(f"http://{dn.address}:{dn.port}/blocks/{block_id}", timeout=REREPLICATION_TIMEOUT)
    resp.raise_for_status()
    return resp.content


def _push_block(dn: DataNode, block_id: str, data: bytes) -> None:
    resp = httpx.post(
        f"http://{dn.address}:{dn.port}/blocks/{block_id}",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
        timeout=REREPLICATION_TIMEOUT,
    )
    resp.raise_for_status()


def _rereplicate() -> None:
    """Para cada bloque con menos réplicas activas que REPLICATION_FACTOR,
    copia el bloque desde una réplica viva a otro DataNode activo."""
    db = SessionLocal()
    try:
        rf = config.REPLICATION_FACTOR
        # Solo bloques ya escritos (size > 0); los recién asignados aún no tienen datos.
        blocks = db.query(Block).filter(Block.size_bytes > 0).all()
        for block in blocks:
            replicas = db.query(BlockReplica).filter_by(block_id=block.id).all()
            active = [r for r in replicas if r.datanode.status == DataNodeStatus.ACTIVE]
            if len(active) >= rf:
                continue
            if not active:
                logger.error(
                    "[monitor] Bloque %s sin réplicas activas; no recuperable", block.block_id
                )
                continue

            source = active[0].datanode
            owned_ids = {r.datanode_id for r in replicas}
            candidates = (
                db.query(DataNode)
                .filter(DataNode.status == DataNodeStatus.ACTIVE)
                .filter(DataNode.id.notin_(owned_ids))
                .filter(DataNode.free_space_bytes >= config.BLOCK_SIZE)
                .order_by(DataNode.blocks_count.asc())
                .all()
            )
            for target in candidates[: rf - len(active)]:
                try:
                    data = _fetch_block(source, block.block_id)
                    _push_block(target, block.block_id, data)
                    db.add(BlockReplica(block_id=block.id, datanode_id=target.id))
                    db.commit()
                    logger.info(
                        "[monitor] Re-replicado block_id=%s desde=%s hacia=%s",
                        block.block_id, source.node_id, target.node_id,
                    )
                except Exception as exc:
                    db.rollback()
                    logger.error(
                        "[monitor] Fallo re-replicando block_id=%s hacia=%s: %s",
                        block.block_id, target.node_id, exc,
                    )
    finally:
        db.close()


async def _monitor_loop() -> None:
    logger.info(
        "[%s] Monitor de DataNodes iniciado (timeout=%ss, intervalo chequeo=2s)",
        datetime.now(timezone.utc).isoformat(),
        config.HEARTBEAT_TIMEOUT,
    )
    while True:
        await asyncio.to_thread(_check_dead_nodes)
        await asyncio.to_thread(_rereplicate)
        await asyncio.sleep(2)


def start_monitor() -> None:
    global _monitor_task
    if _monitor_task is None or _monitor_task.done():
        _monitor_task = asyncio.create_task(_monitor_loop())


def stop_monitor() -> None:
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
    _monitor_task = None
