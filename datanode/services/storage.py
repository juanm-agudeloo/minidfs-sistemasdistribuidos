"""Leer, escribir, listar y borrar bloques en disco."""

import logging
import os
from pathlib import Path

from shared import config

logger = logging.getLogger(__name__)
DATA_DIR = Path(config.DATA_DIR)


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def write_block(block_id: str, data: bytes) -> int:
    _ensure_dir()
    path = DATA_DIR / block_id
    path.write_bytes(data)
    size = len(data)
    logger.info("[storage] Bloque escrito block_id=%s size=%s bytes", block_id, size)
    return size


def read_block(block_id: str) -> bytes:
    path = DATA_DIR / block_id
    if not path.exists():
        raise FileNotFoundError(f"Bloque no encontrado: {block_id}")
    return path.read_bytes()


def delete_block(block_id: str) -> bool:
    path = DATA_DIR / block_id
    if path.exists():
        path.unlink()
        logger.info("[storage] Bloque eliminado block_id=%s", block_id)
        return True
    return False


def list_blocks() -> list[str]:
    _ensure_dir()
    return [f.name for f in DATA_DIR.iterdir() if f.is_file()]


def free_space_bytes() -> int:
    _ensure_dir()
    stat = os.statvfs(DATA_DIR)
    return stat.f_bavail * stat.f_frsize
