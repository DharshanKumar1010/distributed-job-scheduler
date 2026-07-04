import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WorkerStatus(str, enum.Enum):
    idle = "idle"
    busy = "busy"
    offline = "offline"


worker_status_enum = Enum(
    WorkerStatus, name="worker_status", values_callable=lambda enum_cls: [e.value for e in enum_cls]
)


class Worker(Base, TimestampMixin):
    __tablename__ = "workers"

    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queues.id"), nullable=False
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WorkerStatus] = mapped_column(
        worker_status_enum,
        nullable=False,
        default=WorkerStatus.idle,
        server_default=text(f"'{WorkerStatus.idle.value}'"),
    )
    max_concurrency: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default=text("10")
    )
    current_jobs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


class WorkerHeartbeat(Base, TimestampMixin):
    __tablename__ = "worker_heartbeats"
    __table_args__ = (Index("ix_worker_heartbeats_ts", "ts"),)

    worker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    cpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_job_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
