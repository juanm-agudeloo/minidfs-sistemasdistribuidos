"""Fixtures para tests del NameNode (Avance 1)."""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Base de datos en memoria para tests aislados
os.environ.setdefault("DB_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("HEARTBEAT_TIMEOUT", "5")

from namenode.database import Base, SessionLocal, engine, init_db  # noqa: E402
from namenode.main import app  # noqa: E402
from namenode.seed import seed_default_user  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    init_db()
    seed_default_user()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    r = client.post("/auth/login", json={"username": "demo", "password": "demo123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
