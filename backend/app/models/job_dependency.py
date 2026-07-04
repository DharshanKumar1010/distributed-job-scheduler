import uuid

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class JobDependency(Base, TimestampMixin):
    __tablename__ = "job_dependencies"
    __table_args__ = (
        UniqueConstraint("job_id", "depends_on_job_id", name="uq_job_dependencies_job_depends_on"),
        CheckConstraint("job_id != depends_on_job_id", name="ck_job_dependencies_no_self_reference"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
