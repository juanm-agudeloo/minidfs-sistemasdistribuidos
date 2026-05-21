"""NameNode — Avance 2: metadatos, auth, DataNodes, proxy de bloques y namespace."""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from namenode.database import init_db
from namenode.routes import auth, nodes
from namenode.routes import files, blocks
from namenode.seed import seed_default_user
from namenode.services.monitor import start_monitor, stop_monitor
from shared import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_default_user()
    start_monitor()
    logger.info(
        "[%s] NameNode iniciado puerto=%s private_host=%s",
        datetime.now(timezone.utc).isoformat(),
        config.NAMENODE_PORT,
        config.NAMENODE_PRIVATE_HOST,
    )
    yield
    stop_monitor()
    logger.info("[%s] NameNode detenido", datetime.now(timezone.utc).isoformat())


app = FastAPI(
    title="Mini-DFS NameNode",
    description="Avance 2 — Proxy de bloques, namespace y replicación",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(nodes.router)
app.include_router(files.router)
app.include_router(blocks.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "namenode",
        "version": "avance-2",
        "heartbeat_timeout": config.HEARTBEAT_TIMEOUT,
    }
