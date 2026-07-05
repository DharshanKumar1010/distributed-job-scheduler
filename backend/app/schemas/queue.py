import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QueueStats(BaseModel):
    pending_count: int
    running_count: int
    failed_count: int
    throughput_per_min: int


class RateLimitStatus(BaseModel):
    limit_per_minute: int
    burst_capacity: int
    tokens_remaining: float | None
    is_rate_limited: bool


class QueueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    priority: int
    concurrency_limit: int
    retry_policy_id: uuid.UUID | None
    is_paused: bool
    is_active: bool
    shard_count: int
    rate_limit_per_minute: int | None
    rate_limit_burst: int | None
    created_at: datetime
    updated_at: datetime
    stats: QueueStats
    rate_limit_status: RateLimitStatus | None = None


class QueueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    description: str | None = None
    priority: int = Field(default=5, ge=0, le=10)
    concurrency_limit: int = Field(default=10, ge=1)
    retry_policy_id: uuid.UUID | None = None
    shard_count: int = Field(default=1, ge=1)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_burst: int | None = Field(default=None, ge=1)


class QueueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    priority: int | None = Field(default=None, ge=0, le=10)
    concurrency_limit: int | None = Field(default=None, ge=1)
    retry_policy_id: uuid.UUID | None = None
    shard_count: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_burst: int | None = Field(default=None, ge=1)
