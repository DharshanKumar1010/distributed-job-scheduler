import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Queue(Base, TimestampMixin):
    __tablename__ = "queues"
    __table_args__ = (
        Index("ix_queues_project_id_slug", "project_id", "slug", unique=True),
        CheckConstraint("priority >= 0 AND priority <= 10", name="ck_queues_priority_range"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default=text("5"))
    concurrency_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default=text("10")
    )
    retry_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("retry_policies.id"), nullable=True
    )
    is_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    shard_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_limit_burst: Mapped[int | None] = mapped_column(Integer, nullable=True)
