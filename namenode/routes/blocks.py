"""Proxy de bloques del NameNode hacia DataNodes (cliente nunca ve IPs privadas)."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from namenode.database import get_db
from namenode.models import User
from namenode.security import get_current_user
from namenode.services.block_proxy import proxy_get, proxy_put

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/blocks", tags=["blocks"])


@router.post("/{block_id}", status_code=201)
async def upload_block(
    block_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await request.body()
    await proxy_put(db, block_id, data)
    return {"block_id": block_id, "size": len(data)}


@router.get("/{block_id}")
async def download_block(
    block_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await proxy_get(db, block_id)
    return Response(content=data, media_type="application/octet-stream")
