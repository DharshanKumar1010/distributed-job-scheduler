import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.project import Project
from app.models.queue import Queue
from app.models.worker import Worker, WorkerHeartbeat, WorkerStatus


async def list_workers(
    db: AsyncSession, org_id: uuid.UUID, page: int, limit: int
) -> tuple[list[Worker], int]:
    total = await db.scalar(
        select(func.count())
        .select_from(Worker)
        .join(Queue, Queue.id == Worker.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(Project.org_id == org_id)
    )
    result = await db.execute(
        select(Worker)
        .join(Queue, Queue.id == Worker.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(Project.org_id == org_id)
        .order_by(Worker.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def get_worker_for_org(
    db: AsyncSession, org_id: uuid.UUID, worker_id: uuid.UUID
) -> Worker:
    worker = await db.scalar(
        select(Worker)
        .join(Queue, Queue.id == Worker.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(Worker.id == worker_id, Project.org_id == org_id)
    )
    if worker is None:
        raise APIError(404, "WORKER_NOT_FOUND", "Worker not found")
    return worker


async def get_worker_detail(
    db: AsyncSession, org_id: uuid.UUID, worker_id: uuid.UUID, heartbeat_limit: int = 20
) -> tuple[Worker, list[WorkerHeartbeat]]:
    worker = await get_worker_for_org(db, org_id, worker_id)
    heartbeats = list(
        (
            await db.execute(
                select(WorkerHeartbeat)
                .where(WorkerHeartbeat.worker_id == worker.id)
                .order_by(WorkerHeartbeat.ts.desc())
                .limit(heartbeat_limit)
            )
        )
        .scalars()
        .all()
    )
    return worker, heartbeats


async def force_offline(
    db: AsyncSession, org_id: uuid.UUID, worker_id: uuid.UUID
) -> Worker:
    worker = await get_worker_for_org(db, org_id, worker_id)
    worker.status = WorkerStatus.offline
    await db.commit()
    await db.refresh(worker)
    return worker
