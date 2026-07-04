import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class JobStatus(str, enum.Enum):
    queued = "queued"
    scheduled = "scheduled"
    claimed = "claimed"
    running = "running"
    completed = "completed"
    failed = "failed"
    dead = "dead"
    cancelled = "cancelled"
    blocked = "blocked"


class JobType(str, enum.Enum):
    immediate = "immediate"
    delayed = "delayed"
    scheduled = "scheduled"
    recurring = "recurring"
    batch = "batch"


job_status_enum = Enum(
    JobStatus, name="job_status", values_callable=lambda enum_cls: [e.value for e in enum_cls]
)
job_type_enum = Enum(
    JobType, name="job_type", values_callable=lambda enum_cls: [e.value for e in enum_cls]
)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("priority >= 0 AND priority <= 10", name="ck_jobs_priority_range"),
        # Claim query index: matches the FOR UPDATE SKIP LOCKED pattern in CLAUDE.md exactly.
        Index("ix_jobs_claim_query", "queue_id", "status", text("priority DESC"), "created_at"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_scheduled_at", "scheduled_at"),
        Index("ix_jobs_worker_id", "worker_id"),
    )

    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queues.id"), nullable=False
    )
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        job_status_enum,
        nullable=False,
        default=JobStatus.queued,
        server_default=text(f"'{JobStatus.queued.value}'"),
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default=text("5"))

    job_type: Mapped[JobType] = mapped_column(job_type_enum, nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_runtime_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300, server_default=text("300")
    )

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    retry_strategy: Mapped[str] = mapped_column(
        String(50), nullable=False, default="exponential", server_default=text("'exponential'")
    )
    base_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default=text("60")
    )
    max_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, server_default=text("3600")
    )

    worker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workers.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
