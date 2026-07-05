import enum

from sqlalchemy import Boolean, Enum, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RetryStrategy(str, enum.Enum):
    fixed = "fixed"
    linear = "linear"
    exponential = "exponential"


retry_strategy_enum = Enum(
    RetryStrategy,
    name="retry_strategy",
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
)


class RetryPolicy(Base, TimestampMixin):
    __tablename__ = "retry_policies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    strategy: Mapped[RetryStrategy] = mapped_column(
        retry_strategy_enum,
        nullable=False,
        default=RetryStrategy.exponential,
        server_default=text(f"'{RetryStrategy.exponential.value}'"),
    )
    base_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default=text("60")
    )
    max_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600, server_default=text("3600")
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
