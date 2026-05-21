"""Cliente del Mini-DFS.

Fragmenta archivos en bloques y los transfiere SIEMPRE a través del NameNode
(proxy de bloques). El cliente nunca conoce ni contacta las IPs de los DataNodes.
"""

import os
from pathlib import Path

import httpx

# Debe coincidir con BLOCK_SIZE del servidor (el NameNode calcula el nº de bloques
# con su propio BLOCK_SIZE, así que el cliente fragmenta con el mismo tamaño).
DEFAULT_BLOCK_SIZE = int(os.getenv("BLOCK_SIZE", str(64 * 1024 * 1024)))


class DfsError(Exception):
    """Error de operación contra el NameNode."""


class DfsClient:
    def __init__(self, base_url: str, token: str | None = None,
                 block_size: int = DEFAULT_BLOCK_SIZE, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.block_size = block_size
        self.timeout = timeout

    # ── Auth ────────────────────────────────────────────────────────────────
    def login(self, username: str, password: str) -> str:
        r = httpx.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=self.timeout,
        )
        if r.status_code != 200:
            raise DfsError(f"Login fallido: {r.text}")
        self.token = r.json()["access_token"]
        return self.token

    def _auth_headers(self) -> dict:
        if not self.token:
            raise DfsError("No autenticado: ejecuta 'login' primero")
        return {"Authorization": f"Bearer {self.token}"}

    # ── Namespace ───────────────────────────────────────────────────────────
    def mkdir(self, path: str) -> dict:
        r = httpx.post(f"{self.base_url}/files/mkdir", json={"path": path},
                       headers=self._auth_headers(), timeout=self.timeout)
        return self._json(r)

    def ls(self, path: str = "/") -> list:
        r = httpx.get(f"{self.base_url}/files/ls/{path.lstrip('/')}",
                      headers=self._auth_headers(), timeout=self.timeout)
        return self._json(r)

    def rm(self, path: str) -> dict:
        r = httpx.delete(f"{self.base_url}/files/rm/{path.lstrip('/')}",
                         headers=self._auth_headers(), timeout=self.timeout)
        return self._json(r)

    def rmdir(self, path: str) -> dict:
        r = httpx.delete(f"{self.base_url}/files/rmdir/{path.lstrip('/')}",
                         headers=self._auth_headers(), timeout=self.timeout)
        return self._json(r)

    # ── Transferencia de datos ──────────────────────────────────────────────
    def put(self, local_path: str, remote_path: str, progress=None) -> dict:
        local = Path(local_path)
        if not local.is_file():
            raise DfsError(f"Archivo local no existe: {local_path}")
        size = local.stat().st_size

        r = httpx.post(
            f"{self.base_url}/files/put",
            json={"path": remote_path, "size_bytes": size},
            headers=self._auth_headers(), timeout=self.timeout,
        )
        blocks = sorted(self._json(r)["blocks"], key=lambda b: b["block_index"])

        with local.open("rb") as f:
            for i, blk in enumerate(blocks):
                chunk = f.read(self.block_size)
                self._upload_block(blk["block_id"], chunk)
                if progress:
                    progress(i + 1, len(blocks))

        rc = httpx.post(f"{self.base_url}/files/commit/{remote_path.lstrip('/')}",
                        headers=self._auth_headers(), timeout=self.timeout)
        self._json(rc)
        return {"path": remote_path, "size_bytes": size, "blocks": len(blocks)}

    def get(self, remote_path: str, local_path: str, progress=None) -> dict:
        r = httpx.get(f"{self.base_url}/files/get/{remote_path.lstrip('/')}",
                      headers=self._auth_headers(), timeout=self.timeout)
        meta = self._json(r)
        blocks = sorted(meta["blocks"], key=lambda b: b["block_index"])

        out = Path(local_path)
        with out.open("wb") as f:
            for i, blk in enumerate(blocks):
                f.write(self._download_block(blk["block_id"]))
                if progress:
                    progress(i + 1, len(blocks))
        return {"path": remote_path, "local": str(out),
                "size_bytes": meta.get("size_bytes"), "blocks": len(blocks)}

    def _upload_block(self, block_id: str, data: bytes) -> None:
        r = httpx.post(
            f"{self.base_url}/blocks/{block_id}",
            content=data,
            headers={**self._auth_headers(), "Content-Type": "application/octet-stream"},
            timeout=self.timeout,
        )
        self._json(r)

    def _download_block(self, block_id: str) -> bytes:
        r = httpx.get(f"{self.base_url}/blocks/{block_id}",
                      headers=self._auth_headers(), timeout=self.timeout)
        if r.status_code != 200:
            raise DfsError(f"Error {r.status_code} descargando bloque: {r.text}")
        return r.content

    # ── Utilidad ────────────────────────────────────────────────────────────
    @staticmethod
    def _json(r: httpx.Response):
        if r.status_code not in (200, 201):
            raise DfsError(f"Error {r.status_code}: {r.text}")
        return r.json()
