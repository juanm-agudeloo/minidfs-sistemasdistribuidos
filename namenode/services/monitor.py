"""Monitor en background: detecta DataNodes caídos por timeout de heartbeat."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from namenode.database import SessionLocal
from namenode.models import DataNode, DataNodeStatus
from shared import config

logger = logging.getLogger(__name__)

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


async def _monitor_loop() -> None:
    logger.info(
        "[%s] Monitor de DataNodes iniciado (timeout=%ss, intervalo chequeo=2s)",
        datetime.now(timezone.utc).isoformat(),
        config.HEARTBEAT_TIMEOUT,
    )
    while True:
        await asyncio.to_thread(_check_dead_nodes)
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
