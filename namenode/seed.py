"""Datos iniciales: usuario demo para pruebas."""

import logging

from namenode.database import SessionLocal
from namenode.models import User
from namenode.security import hash_password

logger = logging.getLogger(__name__)

DEFAULT_USER = "demo"
DEFAULT_PASSWORD = "demo123"


def seed_default_user() -> None:
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == DEFAULT_USER).first():
            return
        db.add(
            User(
                username=DEFAULT_USER,
                password_hash=hash_password(DEFAULT_PASSWORD),
            )
        )
        db.commit()
        logger.info("Usuario demo creado: %s / %s", DEFAULT_USER, DEFAULT_PASSWORD)
    finally:
        db.close()
