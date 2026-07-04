import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.retry_policy import RetryStrategy


class RetryPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    max_attempts: int
    strategy: RetryStrategy
    base_delay_seconds: int
    max_delay_seconds: int
    is_default: bool


class RetryPolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    max_attempts: int = Field(default=3, ge=1)
    strategy: RetryStrategy = RetryStrategy.exponential
    base_delay_seconds: int = Field(default=60, ge=1)
    max_delay_seconds: int = Field(default=3600, ge=1)
    is_default: bool = False


class RetryPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    max_attempts: int | None = Field(default=None, ge=1)
    strategy: RetryStrategy | None = None
    base_delay_seconds: int | None = Field(default=None, ge=1)
    max_delay_seconds: int | None = Field(default=None, ge=1)
    is_default: bool | None = None
