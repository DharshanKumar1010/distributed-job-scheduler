import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LogLevel(str, enum.Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


log_level_enum = Enum(
    LogLevel,
    name="log_level",
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
)


class JobLog(Base, TimestampMixin):
    __tablename__ = "job_logs"
    __table_args__ = (Index("ix_job_logs_timestamp", "timestamp"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_executions.id"), nullable=True
    )
    level: Mapped[LogLevel] = mapped_column(
        log_level_enum, nullable=False, default=LogLevel.info
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
