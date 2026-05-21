"""Autenticación de usuarios del cliente CLI."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from namenode.database import get_db
from namenode.models import User
from namenode.security import create_access_token, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_hours: int


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        logger.warning(
            "[%s] Intento de login fallido para usuario=%s",
            datetime.now(timezone.utc).isoformat(),
            body.username,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    token = create_access_token(user.username, token_type="user")
    logger.info(
        "[%s] Login exitoso usuario=%s",
        datetime.now(timezone.utc).isoformat(),
        user.username,
    )
    from shared import config

    return LoginResponse(access_token=token, expires_in_hours=config.JWT_EXPIRE_HOURS)
