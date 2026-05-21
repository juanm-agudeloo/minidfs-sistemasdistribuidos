"""Tests Avance 3: namespace (mkdir/ls/rmdir/rm) y re-replicación automática."""

import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"
sys.path.insert(0, str(CLIENT_DIR))


# ── Namespace ────────────────────────────────────────────────────────────────
def test_mkdir_ls_rmdir(client, auth_headers):
    assert client.post("/files/mkdir", json={"path": "/d"}, headers=auth_headers).status_code == 200

    listing = client.get("/files/ls/", headers=auth_headers)
    assert listing.status_code == 200
    assert "/d" in [e["path"] for e in listing.json()]

    assert client.delete("/files/rmdir/d", headers=auth_headers).status_code == 200


def test_rmdir_not_empty(client, auth_headers):
    client.post("/files/mkdir", json={"path": "/d"}, headers=auth_headers)
    client.post("/files/mkdir", json={"path": "/d/sub"}, headers=auth_headers)
    assert client.delete("/files/rmdir/d", headers=auth_headers).status_code == 409


def test_rmdir_missing(client, auth_headers):
    assert client.delete("/files/rmdir/nope", headers=auth_headers).status_code == 404


def test_put_then_rm_file(client, auth_headers, monkeypatch):
    from namenode.routes import files as files_route

    for nid, addr in [("d0", "10.0.2.10"), ("d1", "10.0.2.11")]:
        client.post("/nodes/register", json={
            "node_id": nid, "address": addr, "port": 8001, "free_space_bytes": 10**10,
        })

    put = client.post("/files/put", json={"path": "/x.bin", "size_bytes": 1024}, headers=auth_headers)
    assert put.status_code == 200, put.text
    assert len(put.json()["blocks"]) == 1

    # rm hace borrado físico best-effort; evitamos red real en el test
    monkeypatch.setattr(files_route.httpx, "delete", lambda *a, **k: None)
    assert client.delete("/files/rm/x.bin", headers=auth_headers).status_code == 200
    assert client.get("/files/get/x.bin", headers=auth_headers).status_code == 404


# ── Re-replicación ───────────────────────────────────────────────────────────
def test_rereplication_copies_to_active_node(client, monkeypatch):
    """Un bloque con una réplica viva y una muerta debe re-replicarse a un nodo activo."""
    from namenode.database import SessionLocal
    from namenode import models
    from namenode.services import monitor

    db = SessionLocal()
    try:
        dn1 = models.DataNode(node_id="dn1", address="10.0.2.10", port=8001,
                              node_token="t1", status=models.DataNodeStatus.ACTIVE,
                              free_space_bytes=10**10)
        dn2 = models.DataNode(node_id="dn2", address="10.0.2.11", port=8001,
                              node_token="t2", status=models.DataNodeStatus.DEAD,
                              free_space_bytes=10**10)
        dn3 = models.DataNode(node_id="dn3", address="10.0.2.12", port=8001,
                              node_token="t3", status=models.DataNodeStatus.ACTIVE,
                              free_space_bytes=10**10)
        db.add_all([dn1, dn2, dn3])
        db.flush()

        user = models.User(username="repluser", password_hash="x")
        db.add(user)
        db.flush()
        fe = models.FileEntry(path="/f.bin", owner_id=user.id, size_bytes=10, committed=True)
        db.add(fe)
        db.flush()
        blk = models.Block(block_id="b1", file_id=fe.id, block_index=0, size_bytes=10)
        db.add(blk)
        db.flush()
        db.add_all([
            models.BlockReplica(block_id=blk.id, datanode_id=dn1.id),
            models.BlockReplica(block_id=blk.id, datanode_id=dn2.id),
        ])
        db.commit()
        block_pk = blk.id
    finally:
        db.close()

    pushed = {}
    monkeypatch.setattr(monitor, "_fetch_block", lambda dn, bid: b"datos")
    monkeypatch.setattr(monitor, "_push_block",
                        lambda dn, bid, data: pushed.update(node=dn.node_id))

    monitor._rereplicate()

    assert pushed.get("node") == "dn3"

    db = SessionLocal()
    try:
        replicas = db.query(models.BlockReplica).filter_by(block_id=block_pk).all()
        node_ids = {r.datanode.node_id for r in replicas}
        assert "dn3" in node_ids
        assert len([r for r in replicas if r.datanode.status == models.DataNodeStatus.ACTIVE]) >= 2
    finally:
        db.close()


# ── Cliente ──────────────────────────────────────────────────────────────────
def test_client_module_imports():
    import dfs_client

    c = dfs_client.DfsClient("http://localhost:8000/")
    assert c.base_url == "http://localhost:8000"
    assert c.block_size > 0
