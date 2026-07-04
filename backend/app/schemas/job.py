import uuid
from datetime import datetime

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.job import JobStatus, JobType
from app.models.job_log import LogLevel
from app.models.retry_policy import RetryStrategy


class JobCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    payload: dict = Field(default_factory=dict)
    job_type: JobType
    priority: int = Field(default=5, ge=0, le=10)
    run_at: datetime | None = None
    cron_expression: str | None = None
    scheduled_at: datetime | None = None
    max_attempts: int = Field(default=3, ge=1)
    retry_strategy: RetryStrategy = RetryStrategy.exponential
    base_delay_seconds: int = Field(default=60, ge=1)
    max_runtime_seconds: int = Field(default=300, ge=1)
    tags: list[str] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=255)
    depends_on: list[uuid.UUID] | None = None
    batch_jobs: list["JobCreateRequest"] | None = None

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: {v}")
        return v

    @model_validator(mode="after")
    def validate_job_type_fields(self) -> "JobCreateRequest":
        if self.job_type == JobType.delayed and self.run_at is None:
            raise ValueError("run_at is required when job_type is 'delayed'")
        if self.job_type == JobType.scheduled and self.scheduled_at is None:
            raise ValueError("scheduled_at is required when job_type is 'scheduled'")
        if self.job_type == JobType.recurring and not self.cron_expression:
            raise ValueError("cron_expression is required when job_type is 'recurring'")
        if self.job_type == JobType.batch and not self.batch_jobs:
            raise ValueError("batch_jobs is required and must be non-empty when job_type is 'batch'")
        return self


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    queue_id: uuid.UUID
    parent_job_id: uuid.UUID | None
    name: str
    status: JobStatus
    job_type: JobType
    priority: int
    scheduled_at: datetime | None
    run_at: datetime | None
    attempts: int
    max_attempts: int
    tags: list[str]
    claimed_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    error_message: str | None
    worker_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class JobExecutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: uuid.UUID | None
    attempt_number: int
    status: JobStatus
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    result: dict | None


class JobLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    execution_id: uuid.UUID | None
    level: LogLevel
    message: str
    timestamp: datetime


class JobDetailOut(JobOut):
    payload: dict | None
    result: dict | None
    error_traceback: str | None
    cron_expression: str | None
    executions: list[JobExecutionOut]
    logs: list[JobLogOut]


class BatchCancelRequest(BaseModel):
    job_ids: list[uuid.UUID] = Field(min_length=1)


class BatchCancelResult(BaseModel):
    cancelled: list[uuid.UUID]
    skipped: list[uuid.UUID]
    not_found: list[uuid.UUID]
