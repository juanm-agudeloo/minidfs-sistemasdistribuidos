"""Configuración compartida leída desde variables de entorno."""

import os

# ── Parámetros DFS ─────────────────────────────────────────────
BLOCK_SIZE: int = int(os.getenv("BLOCK_SIZE", "67108864"))
REPLICATION_FACTOR: int = int(os.getenv("REPLICATION_FACTOR", "2"))
HEARTBEAT_INTERVAL: int = int(os.getenv("HEARTBEAT_INTERVAL", "3"))
HEARTBEAT_TIMEOUT: int = int(os.getenv("HEARTBEAT_TIMEOUT", "10"))

# ── NameNode ────────────────────────────────────────────────────
NAMENODE_PUBLIC_HOST: str = os.getenv("NAMENODE_PUBLIC_HOST", "localhost")
NAMENODE_PRIVATE_HOST: str = os.getenv("NAMENODE_PRIVATE_HOST", "namenode")
NAMENODE_PORT: int = int(os.getenv("NAMENODE_PORT", "8000"))

# ── DataNode ────────────────────────────────────────────────────
NAMENODE_HOST: str = os.getenv("NAMENODE_HOST", NAMENODE_PRIVATE_HOST)
DATANODE_PORT: int = int(os.getenv("DATANODE_PORT", "8001"))
DATANODE_PRIVATE_IP: str = os.getenv("DATANODE_PRIVATE_IP", "")
DATA_DIR: str = os.getenv("DATA_DIR", "./blocks")

# ── Base de datos ───────────────────────────────────────────────
DB_URL: str = os.getenv("DB_URL", "sqlite:///./namenode.db")

# ── Seguridad ───────────────────────────────────────────────────
JWT_SECRET: str = os.getenv("JWT_SECRET", "change_me_in_dev")
JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
JWT_ALGORITHM: str = "HS256"
