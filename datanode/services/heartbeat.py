"""Tarea background: envía heartbeat al NameNode por IP privada."""

import asyncio
import logging
import os

import httpx

from datanode.services.storage import free_space_bytes, list_blocks
from shared import config

logger = logging.getLogger(__name__)

_heartbeat_task: asyncio.Task | None = None
_node_token: str = ""
_node_id: str = os.getenv("NODE_ID", "datanode-0")


async def _register_and_get_token() -> str:
    datanode_private_ip = config.DATANODE_PRIVATE_IP or os.getenv("DATANODE_PRIVATE_IP", "127.0.0.1")
    url = f"http://{config.NAMENODE_HOST}:{config.NAMENODE_PORT}/nodes/register"
    payload = {
        "node_id": _node_id,
        "address": datanode_private_ip,
        "port": config.DATANODE_PORT,
        "free_space_bytes": free_space_bytes(),
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        token = resp.json()["node_token"]
        logger.info("[heartbeat] Registrado en NameNode node_id=%s", _node_id)
        return token


async def _heartbeat_loop():
    global _node_token
    _node_token = await _register_and_get_token()
    url = f"http://{config.NAMENODE_HOST}:{config.NAMENODE_PORT}/nodes/heartbeat"

    while True:
        await asyncio.sleep(config.HEARTBEAT_INTERVAL)
        try:
            blocks = list_blocks()
            payload = {
                "free_space_bytes": free_space_bytes(),
                "blocks_count": len(blocks),
                "block_ids": blocks,
            }
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {_node_token}"},
                )
                resp.raise_for_status()
                logger.debug("[heartbeat] OK node_id=%s blocks=%s", _node_id, len(blocks))
        except Exception as exc:
            logger.warning("[heartbeat] Fallo al enviar heartbeat: %s", exc)


def start_heartbeat():
    global _heartbeat_task
    if _heartbeat_task is None or _heartbeat_task.done():
        _heartbeat_task = asyncio.create_task(_heartbeat_loop())


def stop_heartbeat():
    global _heartbeat_task
    if _heartbeat_task and not _heartbeat_task.done():
        _heartbeat_task.cancel()
    _heartbeat_task = None
