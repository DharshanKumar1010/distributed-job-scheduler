import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.job import Job, JobStatus
from app.models.project import Project
from app.models.queue import Queue
from app.models.retry_policy import RetryPolicy

StatsRow = tuple[int, int, int, int]


async def get_stats_for_queue(db: AsyncSession, queue_id: uuid.UUID) -> StatsRow:
    throughput_cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
    stmt = select(
        func.count(Job.id).filter(Job.status == JobStatus.queued),
        func.count(Job.id).filter(Job.status == JobStatus.running),
        func.count(Job.id).filter(Job.status == JobStatus.failed),
        func.count(Job.id).filter(
            Job.status == JobStatus.completed, Job.completed_at >= throughput_cutoff
        ),
    ).where(Job.queue_id == queue_id)
    row = (await db.execute(stmt)).first()
    return tuple(row) if row is not None else (0, 0, 0, 0)


async def list_queues_with_stats(
    db: AsyncSession, project_id: uuid.UUID, page: int, limit: int
) -> tuple[list[tuple[Queue, int, int, int, int]], int]:
    throughput_cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)

    total = await db.scalar(
        select(func.count())
        .select_from(Queue)
        .where(Queue.project_id == project_id, Queue.is_active.is_(True))
    )

    pending_count = (
        func.count(Job.id).filter(Job.status == JobStatus.queued).label("pending_count")
    )
    running_count = (
        func.count(Job.id)
        .filter(Job.status == JobStatus.running)
        .label("running_count")
    )
    failed_count = (
        func.count(Job.id).filter(Job.status == JobStatus.failed).label("failed_count")
    )
    throughput = (
        func.count(Job.id)
        .filter(
            Job.status == JobStatus.completed, Job.completed_at >= throughput_cutoff
        )
        .label("throughput_per_min")
    )

    stmt = (
        select(Queue, pending_count, running_count, failed_count, throughput)
        .outerjoin(Job, Job.queue_id == Queue.id)
        .where(Queue.project_id == project_id, Queue.is_active.is_(True))
        .group_by(Queue.id)
        .order_by(Queue.created_at.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [tuple(row) for row in rows], total or 0


async def _get_queue_or_404(
    db: AsyncSession,
    project_id: uuid.UUID,
    queue_id: uuid.UUID,
    require_active: bool = True,
) -> Queue:
    conditions = [Queue.id == queue_id, Queue.project_id == project_id]
    if require_active:
        conditions.append(Queue.is_active.is_(True))
    queue = await db.scalar(select(Queue).where(*conditions))
    if queue is None:
        raise APIError(404, "QUEUE_NOT_FOUND", "Queue not found")
    return queue


async def get_queue_for_org(
    db: AsyncSession, org_id: uuid.UUID, queue_id: uuid.UUID
) -> Queue:
    queue = await db.scalar(
        select(Queue)
        .join(Project, Project.id == Queue.project_id)
        .where(
            Queue.id == queue_id, Project.org_id == org_id, Queue.is_active.is_(True)
        )
    )
    if queue is None:
        raise APIError(404, "QUEUE_NOT_FOUND", "Queue not found")
    return queue


async def get_queue_with_stats(
    db: AsyncSession, project_id: uuid.UUID, queue_id: uuid.UUID
) -> tuple[Queue, int, int, int, int]:
    queue = await _get_queue_or_404(db, project_id, queue_id, require_active=True)
    stats = await get_stats_for_queue(db, queue.id)
    return (queue, *stats)


async def _check_slug_available(
    db: AsyncSession,
    project_id: uuid.UUID,
    slug: str,
    exclude_queue_id: uuid.UUID | None = None,
) -> None:
    stmt = select(Queue).where(Queue.project_id == project_id, Queue.slug == slug)
    if exclude_queue_id is not None:
        stmt = stmt.where(Queue.id != exclude_queue_id)
    existing = await db.scalar(stmt)
    if existing is not None:
        raise APIError(
            409,
            "QUEUE_SLUG_TAKEN",
            "A queue with this slug already exists in this project",
        )


async def _check_retry_policy_exists(
    db: AsyncSession, retry_policy_id: uuid.UUID | None
) -> None:
    if retry_policy_id is None:
        return
    policy = await db.get(RetryPolicy, retry_policy_id)
    if policy is None:
        raise APIError(404, "RETRY_POLICY_NOT_FOUND", "Retry policy not found")


async def create_queue(db: AsyncSession, project_id: uuid.UUID, data: dict) -> Queue:
    await _check_slug_available(db, project_id, data["slug"])
    await _check_retry_policy_exists(db, data.get("retry_policy_id"))
    queue = Queue(project_id=project_id, **data)
    db.add(queue)
    await db.commit()
    await db.refresh(queue)
    return queue


async def update_queue(
    db: AsyncSession, project_id: uuid.UUID, queue_id: uuid.UUID, data: dict
) -> Queue:
    queue = await _get_queue_or_404(db, project_id, queue_id, require_active=True)
    if "slug" in data and data["slug"] != queue.slug:
        await _check_slug_available(
            db, project_id, data["slug"], exclude_queue_id=queue.id
        )
    if "retry_policy_id" in data:
        await _check_retry_policy_exists(db, data["retry_policy_id"])
    for field, value in data.items():
        setattr(queue, field, value)
    await db.commit()
    await db.refresh(queue)
    return queue


async def pause_queue(
    db: AsyncSession, project_id: uuid.UUID, queue_id: uuid.UUID
) -> Queue:
    queue = await _get_queue_or_404(db, project_id, queue_id, require_active=True)
    queue.is_paused = True
    await db.commit()
    await db.refresh(queue)
    return queue


async def resume_queue(
    db: AsyncSession, project_id: uuid.UUID, queue_id: uuid.UUID
) -> Queue:
    queue = await _get_queue_or_404(db, project_id, queue_id, require_active=True)
    queue.is_paused = False
    await db.commit()
    await db.refresh(queue)
    return queue


async def soft_delete_queue(
    db: AsyncSession, project_id: uuid.UUID, queue_id: uuid.UUID
) -> Queue:
    queue = await _get_queue_or_404(db, project_id, queue_id, require_active=True)
    queue.is_active = False
    await db.commit()
    await db.refresh(queue)
    return queue
