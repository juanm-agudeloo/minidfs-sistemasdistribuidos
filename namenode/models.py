"""Modelos SQLAlchemy del NameNode."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from namenode.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataNodeStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEAD = "DEAD"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataNode(Base):
    """address almacena la IP privada del DataNode dentro de la VPC."""

    __tablename__ = "datanodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(64))  # IP privada
    port: Mapped[int] = mapped_column(Integer, default=8001)
    status: Mapped[DataNodeStatus] = mapped_column(
        Enum(DataNodeStatus), default=DataNodeStatus.ACTIVE
    )
    node_token: Mapped[str] = mapped_column(String(128), unique=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    blocks_count: Mapped[int] = mapped_column(Integer, default=0)
    free_space_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    block_replicas: Mapped[list["BlockReplica"]] = relationship(back_populates="datanode")


class FileEntry(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("owner_id", "path", name="uq_owner_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path: Mapped[str] = mapped_column(String(1024), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    is_directory: Mapped[bool] = mapped_column(Boolean, default=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    committed: Mapped[bool] = mapped_column(Boolean, default=False)

    owner: Mapped["User"] = relationship()
    blocks: Mapped[list["Block"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", order_by="Block.block_index"
    )


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("file_id", "block_index", name="uq_file_block_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    block_index: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    file: Mapped["FileEntry"] = relationship(back_populates="blocks")
    replicas: Mapped[list["BlockReplica"]] = relationship(
        back_populates="block", cascade="all, delete-orphan"
    )


class BlockReplica(Base):
    __tablename__ = "block_replicas"
    __table_args__ = (UniqueConstraint("block_id", "datanode_id", name="uq_block_datanode"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("blocks.id"))
    datanode_id: Mapped[int] = mapped_column(ForeignKey("datanodes.id"))

    block: Mapped["Block"] = relationship(back_populates="replicas")
    datanode: Mapped["DataNode"] = relationship(back_populates="block_replicas")


class HeartbeatLog(Base):
    """Registro opcional de heartbeats para auditoría."""

    __tablename__ = "heartbeat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    datanode_id: Mapped[int] = mapped_column(ForeignKey("datanodes.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    blocks_report: Mapped[str] = mapped_column(Text, default="[]")
