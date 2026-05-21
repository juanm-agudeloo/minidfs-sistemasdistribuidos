"""DataNode — Avance 2: almacenamiento de bloques y pipeline de replicación."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datanode.routes import blocks
from datanode.services.heartbeat import start_heartbeat, stop_heartbeat
from datanode.services.storage import free_space_bytes, list_blocks
from shared import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_heartbeat()
    logger.info("[datanode] Iniciado puerto=%s namenode=%s:%s",
                config.DATANODE_PORT, config.NAMENODE_HOST, config.NAMENODE_PORT)
    yield
    stop_heartbeat()
    logger.info("[datanode] Detenido")


app = FastAPI(title="Mini-DFS DataNode", version="0.2.0", lifespan=lifespan)
app.include_router(blocks.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "datanode",
        "blocks": len(list_blocks()),
        "free_space_bytes": free_space_bytes(),
    }
