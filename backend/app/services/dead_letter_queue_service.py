import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.dead_letter_queue import DeadLetterQueueEntry
from app.models.job import Job
from app.models.project import Project
from app.models.queue import Queue
from app.services import job_service


def _scoped_conditions(
    org_id: uuid.UUID, queue_id: uuid.UUID | None, is_resolved: bool | None
) -> list:
    conditions = [Project.org_id == org_id]
    if queue_id is not None:
        conditions.append(DeadLetterQueueEntry.queue_id == queue_id)
    if is_resolved is not None:
        conditions.append(DeadLetterQueueEntry.is_resolved == is_resolved)
    return conditions


async def list_dlq_entries(
    db: AsyncSession,
    org_id: uuid.UUID,
    queue_id: uuid.UUID | None,
    is_resolved: bool | None,
    page: int,
    limit: int,
) -> tuple[list[tuple[DeadLetterQueueEntry, Job]], int]:
    conditions = _scoped_conditions(org_id, queue_id, is_resolved)

    total = await db.scalar(
        select(func.count())
        .select_from(DeadLetterQueueEntry)
        .join(Job, Job.id == DeadLetterQueueEntry.job_id)
        .join(Queue, Queue.id == DeadLetterQueueEntry.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(*conditions)
    )

    result = await db.execute(
        select(DeadLetterQueueEntry, Job)
        .join(Job, Job.id == DeadLetterQueueEntry.job_id)
        .join(Queue, Queue.id == DeadLetterQueueEntry.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(*conditions)
        .order_by(DeadLetterQueueEntry.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return [tuple(row) for row in result.all()], total or 0


async def get_dlq_entry_for_org(
    db: AsyncSession, org_id: uuid.UUID, entry_id: uuid.UUID
) -> tuple[DeadLetterQueueEntry, Job]:
    row = (
        await db.execute(
            select(DeadLetterQueueEntry, Job)
            .join(Job, Job.id == DeadLetterQueueEntry.job_id)
            .join(Queue, Queue.id == DeadLetterQueueEntry.queue_id)
            .join(Project, Project.id == Queue.project_id)
            .where(DeadLetterQueueEntry.id == entry_id, Project.org_id == org_id)
        )
    ).first()
    if row is None:
        raise APIError(404, "DLQ_ENTRY_NOT_FOUND", "Dead letter queue entry not found")
    return tuple(row)


async def resolve_dlq_entry(
    db: AsyncSession, org_id: uuid.UUID, entry_id: uuid.UUID, resolved_by: uuid.UUID
) -> tuple[DeadLetterQueueEntry, Job]:
    entry, job = await get_dlq_entry_for_org(db, org_id, entry_id)
    entry.is_resolved = True
    entry.resolved_at = datetime.now(timezone.utc)
    entry.resolved_by = resolved_by
    await db.commit()
    await db.refresh(entry)
    return entry, job


async def replay_dlq_entry(db: AsyncSession, org_id: uuid.UUID, entry_id: uuid.UUID) -> Job:
    entry, _job = await get_dlq_entry_for_org(db, org_id, entry_id)
    # retry_job() resets the job to queued and deletes any DLQ entry for it.
    return await job_service.retry_job(db, org_id, entry.job_id)
