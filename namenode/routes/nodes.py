"""Registro y heartbeats de DataNodes."""

import json
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from namenode.database import get_db
from namenode.models import DataNode, DataNodeStatus, HeartbeatLog
from namenode.security import get_datanode_from_token
from shared import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])


class RegisterRequest(BaseModel):
    node_id: str
    address: str = Field(..., description="IP privada del DataNode en la VPC")
    port: int = 8001
    free_space_bytes: int = 0


class RegisterResponse(BaseModel):
    node_token: str
    node_id: str
    message: str


class HeartbeatRequest(BaseModel):
    free_space_bytes: int = 0
    blocks_count: int = 0
    block_ids: list[str] = Field(default_factory=list)


class HeartbeatResponse(BaseModel):
    status: str
    heartbeat_interval: int


class DataNodeInfo(BaseModel):
    node_id: str
    address: str
    port: int
    status: str
    last_heartbeat: datetime | None
    blocks_count: int
    free_space_bytes: int


@router.post("/register", response_model=RegisterResponse)
def register_node(body: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(DataNode).filter(DataNode.node_id == body.node_id).first()
    token = secrets.token_urlsafe(32)

    if existing:
        existing.address = body.address
        existing.port = body.port
        existing.free_space_bytes = body.free_space_bytes
        existing.status = DataNodeStatus.ACTIVE
        existing.last_heartbeat = datetime.now(timezone.utc)
        existing.node_token = token
        db.commit()
        logger.info(
            "[%s] DataNode re-registrado node_id=%s address=%s port=%s",
            datetime.now(timezone.utc).isoformat(),
            body.node_id,
            body.address,
            body.port,
        )
        return RegisterResponse(
            node_token=token,
            node_id=body.node_id,
            message="DataNode actualizado y reactivado",
        )

    node = DataNode(
        node_id=body.node_id,
        address=body.address,
        port=body.port,
        free_space_bytes=body.free_space_bytes,
        node_token=token,
        last_heartbeat=datetime.now(timezone.utc),
        status=DataNodeStatus.ACTIVE,
    )
    db.add(node)
    db.commit()

    logger.info(
        "[%s] DataNode registrado node_id=%s address=%s port=%s",
        datetime.now(timezone.utc).isoformat(),
        body.node_id,
        body.address,
        body.port,
    )
    return RegisterResponse(
        node_token=token,
        node_id=body.node_id,
        message="DataNode registrado correctamente",
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    body: HeartbeatRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere Bearer token de DataNode",
        )
    token = authorization.split(" ", 1)[1]
    node = get_datanode_from_token(token, db)

    now = datetime.now(timezone.utc)
    node.last_heartbeat = now
    node.free_space_bytes = body.free_space_bytes
    node.blocks_count = body.blocks_count
    if node.status == DataNodeStatus.DEAD:
        node.status = DataNodeStatus.ACTIVE
        logger.info(
            "[%s] DataNode recuperado tras heartbeat node_id=%s",
            now.isoformat(),
            node.node_id,
        )

    db.add(
        HeartbeatLog(
            datanode_id=node.id,
            blocks_report=json.dumps(body.block_ids),
        )
    )
    db.commit()

    logger.debug(
        "[%s] Heartbeat node_id=%s blocks=%s free_space=%s",
        now.isoformat(),
        node.node_id,
        body.blocks_count,
        body.free_space_bytes,
    )
    return HeartbeatResponse(status="ok", heartbeat_interval=config.HEARTBEAT_INTERVAL)


@router.get("/", response_model=list[DataNodeInfo])
def list_nodes(db: Session = Depends(get_db)):
    """Endpoint de diagnóstico para ver estado de DataNodes (sin auth en avance 1 tests)."""
    nodes = db.query(DataNode).all()
    return [
        DataNodeInfo(
            node_id=n.node_id,
            address=n.address,
            port=n.port,
            status=n.status.value,
            last_heartbeat=n.last_heartbeat,
            blocks_count=n.blocks_count,
            free_space_bytes=n.free_space_bytes,
        )
        for n in nodes
    ]
