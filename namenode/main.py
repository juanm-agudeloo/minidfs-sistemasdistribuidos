"""NameNode — Avance 1: metadatos, auth y gestión de DataNodes."""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from namenode.database import init_db  # noqa: E402
from namenode.routes import auth, nodes  # noqa: E402
from namenode.seed import seed_default_user  # noqa: E402
from namenode.services.monitor import start_monitor, stop_monitor  # noqa: E402
from shared import config  # noqa: E402

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
    description="Avance 1 — Auth, namespace y registro de DataNodes",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(nodes.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "namenode",
        "version": "avance-1",
        "heartbeat_timeout": config.HEARTBEAT_TIMEOUT,
    }
