import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.worker import WorkerStatus


class WorkerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    queue_id: uuid.UUID
    hostname: str
    pid: int
    status: WorkerStatus
    max_concurrency: int
    current_jobs: int
    last_seen: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkerHeartbeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worker_id: uuid.UUID
    ts: datetime
    cpu_pct: float | None
    mem_pct: float | None
    active_job_count: int


class WorkerDetailOut(WorkerOut):
    heartbeats: list[WorkerHeartbeatOut]
