import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.dead_letter_queue import DeadLetterQueueEntry
from app.models.job import Job
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.dead_letter_queue import DeadLetterQueueEntryOut
from app.schemas.job import JobOut
from app.services import dead_letter_queue_service

router = APIRouter(prefix="/dead-letter-queue", tags=["dead-letter-queue"])


def _to_entry_out(entry: DeadLetterQueueEntry, job: Job) -> DeadLetterQueueEntryOut:
    return DeadLetterQueueEntryOut(
        id=entry.id,
        job_id=entry.job_id,
        queue_id=entry.queue_id,
        job_name=job.name,
        job_status=job.status,
        failed_at=entry.failed_at,
        total_attempts=entry.total_attempts,
        last_error=entry.last_error,
        last_traceback=entry.last_traceback,
        ai_summary=entry.ai_summary,
        is_resolved=entry.is_resolved,
        resolved_at=entry.resolved_at,
        resolved_by=entry.resolved_by,
        created_at=entry.created_at,
    )


@router.get("", response_model=PaginatedResponse[DeadLetterQueueEntryOut])
async def list_dlq_entries(
    queue_id: uuid.UUID | None = Query(default=None),
    is_resolved: bool | None = Query(default=None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows, total = await dead_letter_queue_service.list_dlq_entries(
        db, current_user.org_id, queue_id, is_resolved, page, limit
    )
    return PaginatedResponse(
        data=[_to_entry_out(entry, job) for entry, job in rows],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.post("/{entry_id}/resolve", response_model=DataResponse[DeadLetterQueueEntryOut])
async def resolve_dlq_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry, job = await dead_letter_queue_service.resolve_dlq_entry(
        db, current_user.org_id, entry_id, current_user.id
    )
    return DataResponse(data=_to_entry_out(entry, job))


@router.post("/{entry_id}/replay", response_model=DataResponse[JobOut])
async def replay_dlq_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await dead_letter_queue_service.replay_dlq_entry(db, current_user.org_id, entry_id)
    return DataResponse(data=JobOut.model_validate(job))
