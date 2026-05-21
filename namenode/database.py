"""Inicialización de base de datos y sesión SQLAlchemy."""

import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Permite importar shared/ desde el contenedor o tests locales
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared import config  # noqa: E402

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


connect_args = {}
if config.DB_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(config.DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from namenode import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("[%s] Base de datos inicializada: %s", __name__, config.DB_URL)
