import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.job import JobStatus


class DeadLetterQueueEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    queue_id: uuid.UUID
    job_name: str
    job_status: JobStatus
    failed_at: datetime
    total_attempts: int
    last_error: str
    last_traceback: str | None
    ai_summary: str | None
    is_resolved: bool
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    created_at: datetime
