"""Tests Avance 1: registro de DataNodes, heartbeats y detección DEAD."""

import time

import pytest

from namenode.database import SessionLocal
from namenode.models import DataNode, DataNodeStatus


def _register_node(client, node_id: str, address: str, port: int) -> str:
    r = client.post(
        "/nodes/register",
        json={
            "node_id": node_id,
            "address": address,
            "port": port,
            "free_space_bytes": 10_000_000_000,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["node_token"]


def _heartbeat(client, token: str, blocks_count: int = 0):
    return client.post(
        "/nodes/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "free_space_bytes": 9_000_000_000,
            "blocks_count": blocks_count,
            "block_ids": [],
        },
    )


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_login_success_and_failure(client):
    ok = client.post("/auth/login", json={"username": "demo", "password": "demo123"})
    assert ok.status_code == 200
    assert "access_token" in ok.json()

    bad = client.post("/auth/login", json={"username": "demo", "password": "wrong"})
    assert bad.status_code == 401


def test_register_three_datanodes(client):
    nodes = [
        ("datanode-0", "10.0.2.10", 8001),
        ("datanode-1", "10.0.2.11", 8002),
        ("datanode-2", "10.0.2.12", 8003),
    ]
    for node_id, address, port in nodes:
        token = _register_node(client, node_id, address, port)
        hb = _heartbeat(client, token)
        assert hb.status_code == 200

    listing = client.get("/nodes/")
    assert listing.status_code == 200
    data = listing.json()
    assert len(data) == 3
    addresses = {n["address"] for n in data}
    assert addresses == {"10.0.2.10", "10.0.2.11", "10.0.2.12"}
    assert all(n["status"] == "ACTIVE" for n in data)


def test_datanode_marked_dead_without_heartbeat(client):
    """Simula un DataNode que deja de enviar heartbeats."""
    token_alive = _register_node(client, "dn-alive", "10.0.2.20", 8001)
    token_dead = _register_node(client, "dn-dead", "10.0.2.21", 8002)

    _heartbeat(client, token_alive)
    _heartbeat(client, token_dead)

    # Solo el nodo 'alive' sigue enviando heartbeats
    time.sleep(7)  # > HEARTBEAT_TIMEOUT (5s en tests)
    _heartbeat(client, token_alive)

    time.sleep(3)  # dar tiempo al monitor background

    db = SessionLocal()
    try:
        dead = db.query(DataNode).filter(DataNode.node_id == "dn-dead").first()
        alive = db.query(DataNode).filter(DataNode.node_id == "dn-alive").first()
        assert dead is not None
        assert alive is not None
        assert dead.status == DataNodeStatus.DEAD
        assert alive.status == DataNodeStatus.ACTIVE
    finally:
        db.close()

    listing = client.get("/nodes/")
    statuses = {n["node_id"]: n["status"] for n in listing.json()}
    assert statuses["dn-dead"] == "DEAD"
    assert statuses["dn-alive"] == "ACTIVE"


def test_heartbeat_reactivates_dead_node(client):
    token = _register_node(client, "dn-recover", "10.0.2.30", 8001)
    _heartbeat(client, token)

    time.sleep(7)
    time.sleep(3)

    db = SessionLocal()
    try:
        node = db.query(DataNode).filter(DataNode.node_id == "dn-recover").first()
        assert node.status == DataNodeStatus.DEAD
    finally:
        db.close()

    hb = _heartbeat(client, token)
    assert hb.status_code == 200

    db = SessionLocal()
    try:
        node = db.query(DataNode).filter(DataNode.node_id == "dn-recover").first()
        assert node.status == DataNodeStatus.ACTIVE
    finally:
        db.close()
