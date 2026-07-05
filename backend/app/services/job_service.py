import uuid
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import cast, delete, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.dead_letter_queue import DeadLetterQueueEntry
from app.models.job import Job, JobStatus, JobType
from app.models.job_dependency import JobDependency
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.project import Project
from app.models.queue import Queue
from app.models.scheduled_job import ScheduledJob
from app.schemas.job import JobCreateRequest
from app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowCreateResult,
    WorkflowJobResult,
)
from app.services import dependency_service, queue_service

CANCELLABLE_STATUSES = {JobStatus.queued, JobStatus.scheduled, JobStatus.blocked}
ACTIVE_STATUSES = {JobStatus.claimed, JobStatus.running}
RETRYABLE_STATUSES = {JobStatus.failed, JobStatus.dead}


async def get_job_for_org(
    db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID
) -> Job:
    job = await db.scalar(
        select(Job)
        .join(Queue, Queue.id == Job.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(Job.id == job_id, Project.org_id == org_id)
    )
    if job is None:
        raise APIError(404, "JOB_NOT_FOUND", "Job not found")
    return job


async def _verify_dependencies_exist(
    db: AsyncSession, org_id: uuid.UUID, depends_on: list[uuid.UUID]
) -> None:
    result = await db.execute(
        select(Job.id)
        .join(Queue, Queue.id == Job.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(Job.id.in_(depends_on), Project.org_id == org_id)
    )
    found = {row[0] for row in result.all()}
    missing = [str(jid) for jid in depends_on if jid not in found]
    if missing:
        raise APIError(
            400,
            "INVALID_DEPENDENCY",
            "One or more dependency job IDs do not exist",
            details={"missing_job_ids": missing},
        )


async def _dependencies_completed(
    db: AsyncSession, depends_on: list[uuid.UUID]
) -> bool:
    incomplete = await db.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.id.in_(depends_on), Job.status != JobStatus.completed)
    )
    return (incomplete or 0) == 0


async def _resolve_job_names(
    db: AsyncSession, job_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    result = await db.execute(select(Job.id, Job.name).where(Job.id.in_(job_ids)))
    return {row[0]: row[1] for row in result.all()}


async def _raise_cycle_error(
    db: AsyncSession, job_id: uuid.UUID, path: list[str]
) -> None:
    full_path_ids = [job_id] + [uuid.UUID(p) for p in path]
    names = await _resolve_job_names(db, full_path_ids)
    raise APIError(
        400,
        "DEPENDENCY_CYCLE_DETECTED",
        "Creating this dependency would form a cycle",
        details={
            "cycle_path": [str(jid) for jid in full_path_ids],
            "cycle_path_names": [names.get(jid, str(jid)) for jid in full_path_ids],
        },
    )


async def _create_dependencies(
    db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID, depends_on: list[uuid.UUID]
) -> None:
    has_cycle, path = await dependency_service.detect_cycle(job_id, depends_on, db)
    if has_cycle:
        await _raise_cycle_error(db, job_id, path)
    for dep_id in depends_on:
        db.add(JobDependency(job_id=job_id, depends_on_job_id=dep_id))


def _compute_schedule(
    payload: JobCreateRequest,
) -> tuple[JobStatus, datetime | None, datetime | None]:
    if payload.job_type == JobType.immediate:
        return JobStatus.queued, None, None
    if payload.job_type == JobType.delayed:
        return JobStatus.scheduled, payload.run_at, payload.run_at
    if payload.job_type == JobType.scheduled:
        return JobStatus.scheduled, payload.scheduled_at, None
    if payload.job_type == JobType.recurring:
        next_run = croniter(
            payload.cron_expression, datetime.now(timezone.utc)
        ).get_next(datetime)
        return JobStatus.scheduled, next_run, None
    raise APIError(400, "INVALID_JOB_TYPE", f"Unsupported job_type: {payload.job_type}")


async def _create_single_job(
    db: AsyncSession,
    queue_id: uuid.UUID,
    org_id: uuid.UUID,
    payload: JobCreateRequest,
    idempotency_key: str | None,
) -> Job:
    depends_on = payload.depends_on or []
    if depends_on:
        await _verify_dependencies_exist(db, org_id, depends_on)

    status, scheduled_at, run_at = _compute_schedule(payload)

    if depends_on and not await _dependencies_completed(db, depends_on):
        status = JobStatus.blocked

    job = Job(
        queue_id=queue_id,
        name=payload.name,
        payload=payload.payload,
        status=status,
        priority=payload.priority,
        job_type=payload.job_type,
        cron_expression=(
            payload.cron_expression if payload.job_type == JobType.recurring else None
        ),
        scheduled_at=scheduled_at,
        run_at=run_at,
        max_runtime_seconds=payload.max_runtime_seconds,
        max_attempts=payload.max_attempts,
        retry_strategy=payload.retry_strategy.value,
        base_delay_seconds=payload.base_delay_seconds,
        max_delay_seconds=payload.max_delay_seconds,
        tags=payload.tags,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    await db.flush()

    if depends_on:
        await _create_dependencies(db, org_id, job.id, depends_on)

    if payload.job_type == JobType.recurring:
        db.add(
            ScheduledJob(
                job_id=job.id,
                next_run_at=scheduled_at,
                cron_expression=payload.cron_expression,
                is_active=True,
            )
        )

    await db.commit()
    await db.refresh(job)
    return job


async def _create_batch_job(
    db: AsyncSession,
    queue_id: uuid.UUID,
    org_id: uuid.UUID,
    payload: JobCreateRequest,
    idempotency_key: str | None,
) -> Job:
    depends_on = payload.depends_on or []
    if depends_on:
        await _verify_dependencies_exist(db, org_id, depends_on)

    now = datetime.now(timezone.utc)
    parent = Job(
        queue_id=queue_id,
        name=payload.name,
        payload=payload.payload,
        status=JobStatus.running,
        priority=payload.priority,
        job_type=JobType.batch,
        max_runtime_seconds=payload.max_runtime_seconds,
        max_attempts=payload.max_attempts,
        retry_strategy=payload.retry_strategy.value,
        base_delay_seconds=payload.base_delay_seconds,
        max_delay_seconds=payload.max_delay_seconds,
        tags=payload.tags,
        idempotency_key=idempotency_key,
        started_at=now,
    )
    db.add(parent)
    await db.flush()

    if depends_on:
        await _create_dependencies(db, org_id, parent.id, depends_on)

    for child in payload.batch_jobs or []:
        child_key = child.idempotency_key
        if child_key:
            existing_child = await db.scalar(
                select(Job).where(Job.idempotency_key == child_key)
            )
            if existing_child is not None:
                continue
        db.add(
            Job(
                queue_id=queue_id,
                parent_job_id=parent.id,
                name=child.name,
                payload=child.payload,
                status=JobStatus.queued,
                priority=child.priority,
                job_type=JobType.immediate,
                max_runtime_seconds=child.max_runtime_seconds,
                max_attempts=child.max_attempts,
                retry_strategy=child.retry_strategy.value,
                base_delay_seconds=child.base_delay_seconds,
                max_delay_seconds=child.max_delay_seconds,
                tags=child.tags,
                idempotency_key=child_key,
            )
        )

    await db.commit()
    await db.refresh(parent)
    return parent


async def create_job(
    db: AsyncSession,
    org_id: uuid.UUID,
    queue_id: uuid.UUID,
    payload: JobCreateRequest,
    idempotency_key_header: str | None,
) -> tuple[Job, bool]:
    await queue_service.get_queue_for_org(db, org_id, queue_id)

    idempotency_key = idempotency_key_header or payload.idempotency_key
    if idempotency_key:
        existing = await db.scalar(
            select(Job).where(Job.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False

    if payload.job_type == JobType.batch:
        job = await _create_batch_job(db, queue_id, org_id, payload, idempotency_key)
    else:
        job = await _create_single_job(db, queue_id, org_id, payload, idempotency_key)

    return job, True


async def list_jobs(
    db: AsyncSession,
    org_id: uuid.UUID,
    queue_id: uuid.UUID,
    status_filter: JobStatus | None,
    job_type: JobType | None,
    tag: str | None,
    page: int,
    limit: int,
    sort: str,
) -> tuple[list[Job], int]:
    await queue_service.get_queue_for_org(db, org_id, queue_id)

    conditions = [Job.queue_id == queue_id]
    if status_filter is not None:
        conditions.append(Job.status == status_filter)
    if job_type is not None:
        conditions.append(Job.job_type == job_type)
    if tag is not None:
        conditions.append(cast(Job.tags, JSONB).contains([tag]))

    total = await db.scalar(select(func.count()).select_from(Job).where(*conditions))

    order_column = Job.priority.desc() if sort == "priority" else Job.created_at.desc()

    result = await db.execute(
        select(Job)
        .where(*conditions)
        .order_by(order_column)
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def get_job_detail(
    db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID
) -> tuple[Job, list[JobExecution], list[JobLog]]:
    job = await get_job_for_org(db, org_id, job_id)

    executions = list(
        (
            await db.execute(
                select(JobExecution)
                .where(JobExecution.job_id == job.id)
                .order_by(JobExecution.attempt_number.asc())
            )
        )
        .scalars()
        .all()
    )
    logs = list(
        (
            await db.execute(
                select(JobLog)
                .where(JobLog.job_id == job.id)
                .order_by(JobLog.timestamp.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return job, executions, logs


async def cancel_job(db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = await get_job_for_org(db, org_id, job_id)
    if job.status in ACTIVE_STATUSES:
        raise APIError(
            409, "JOB_NOT_CANCELLABLE", "Cannot cancel a job that is currently running"
        )
    if job.status not in CANCELLABLE_STATUSES:
        raise APIError(409, "JOB_NOT_CANCELLABLE", "Job is already in a terminal state")
    job.status = JobStatus.cancelled
    await db.commit()
    await db.refresh(job)
    return job


async def retry_job(db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = await get_job_for_org(db, org_id, job_id)
    if job.status not in RETRYABLE_STATUSES:
        raise APIError(
            409, "JOB_NOT_RETRYABLE", "Only failed or dead jobs can be retried"
        )

    job.status = JobStatus.queued
    job.worker_id = None
    job.claimed_at = None
    job.started_at = None
    job.completed_at = None
    job.failed_at = None
    job.error_message = None
    job.error_traceback = None
    job.scheduled_at = None

    await db.execute(
        delete(DeadLetterQueueEntry).where(DeadLetterQueueEntry.job_id == job.id)
    )

    await db.commit()
    await db.refresh(job)
    return job


async def get_job_logs(
    db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID, page: int, limit: int
) -> tuple[list[JobLog], int]:
    job = await get_job_for_org(db, org_id, job_id)

    total = await db.scalar(
        select(func.count()).select_from(JobLog).where(JobLog.job_id == job.id)
    )
    result = await db.execute(
        select(JobLog)
        .where(JobLog.job_id == job.id)
        .order_by(JobLog.timestamp.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def batch_cancel_jobs(
    db: AsyncSession, org_id: uuid.UUID, job_ids: list[uuid.UUID]
) -> dict:
    existing_result = await db.execute(
        select(Job.id, Job.status)
        .join(Queue, Queue.id == Job.queue_id)
        .join(Project, Project.id == Queue.project_id)
        .where(Job.id.in_(job_ids), Project.org_id == org_id)
    )
    existing = {row[0]: row[1] for row in existing_result.all()}
    not_found = [jid for jid in job_ids if jid not in existing]
    cancellable_ids = [jid for jid, st in existing.items() if st == JobStatus.queued]
    skipped = [jid for jid, st in existing.items() if st != JobStatus.queued]

    cancelled_ids: list[uuid.UUID] = []
    if cancellable_ids:
        result = await db.execute(
            update(Job)
            .where(Job.id.in_(cancellable_ids))
            .values(status=JobStatus.cancelled)
            .returning(Job.id)
        )
        cancelled_ids = [row[0] for row in result.all()]
        await db.commit()

    return {"cancelled": cancelled_ids, "skipped": skipped, "not_found": not_found}


MODIFIABLE_DEPENDENCY_STATUSES = {JobStatus.blocked, JobStatus.queued}


async def add_dependency(
    db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID, depends_on_job_id: uuid.UUID
) -> Job:
    job = await get_job_for_org(db, org_id, job_id)
    if job.status not in MODIFIABLE_DEPENDENCY_STATUSES:
        raise APIError(
            409,
            "JOB_NOT_MODIFIABLE",
            "Dependencies can only be added to jobs in 'blocked' or 'queued' status",
        )

    await _verify_dependencies_exist(db, org_id, [depends_on_job_id])

    existing = await db.scalar(
        select(JobDependency).where(
            JobDependency.job_id == job_id,
            JobDependency.depends_on_job_id == depends_on_job_id,
        )
    )
    if existing is not None:
        raise APIError(
            409, "DEPENDENCY_ALREADY_EXISTS", "This dependency already exists"
        )

    has_cycle, path = await dependency_service.detect_cycle(
        job_id, [depends_on_job_id], db
    )
    if has_cycle:
        await _raise_cycle_error(db, job_id, path)

    db.add(JobDependency(job_id=job_id, depends_on_job_id=depends_on_job_id))

    dep_job = await db.get(Job, depends_on_job_id)
    if (
        job.status == JobStatus.queued
        and dep_job is not None
        and dep_job.status != JobStatus.completed
    ):
        job.status = JobStatus.blocked

    await db.commit()
    await db.refresh(job)
    return job


async def remove_dependency(
    db: AsyncSession, org_id: uuid.UUID, job_id: uuid.UUID, dep_job_id: uuid.UUID
) -> Job:
    job = await get_job_for_org(db, org_id, job_id)

    result = await db.execute(
        delete(JobDependency).where(
            JobDependency.job_id == job_id,
            JobDependency.depends_on_job_id == dep_job_id,
        )
    )
    if result.rowcount == 0:
        raise APIError(404, "DEPENDENCY_NOT_FOUND", "This dependency does not exist")

    if job.status == JobStatus.blocked:
        remaining = await db.scalar(
            select(func.count())
            .select_from(JobDependency)
            .join(Job, Job.id == JobDependency.depends_on_job_id)
            .where(JobDependency.job_id == job_id, Job.status != JobStatus.completed)
        )
        if (remaining or 0) == 0:
            job.status = JobStatus.queued

    await db.commit()
    await db.refresh(job)
    return job


def _validate_workflow_acyclic(payload: WorkflowCreateRequest) -> None:
    """Pure in-memory topological sort (Kahn's algorithm) over the local ref
    graph — the whole workflow is self-contained in the payload, so this
    needs no DB round-trips.
    """
    in_degree = {job.ref: 0 for job in payload.jobs}
    adjacency: dict[str, list[str]] = {job.ref: [] for job in payload.jobs}
    for job in payload.jobs:
        for dep_ref in job.depends_on:
            adjacency[dep_ref].append(job.ref)
            in_degree[job.ref] += 1

    queue = [ref for ref, degree in in_degree.items() if degree == 0]
    visited_count = 0
    while queue:
        current = queue.pop()
        visited_count += 1
        for neighbor in adjacency[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited_count != len(payload.jobs):
        raise APIError(
            400, "WORKFLOW_CYCLE_DETECTED", "Workflow job dependencies contain a cycle"
        )


async def create_workflow(
    db: AsyncSession, org_id: uuid.UUID, payload: WorkflowCreateRequest
) -> WorkflowCreateResult:
    _validate_workflow_acyclic(payload)

    queue_ids = {job.queue_id for job in payload.jobs}
    for queue_id in queue_ids:
        await queue_service.get_queue_for_org(db, org_id, queue_id)

    ref_to_job: dict[str, Job] = {}
    for job_spec in payload.jobs:
        job = Job(
            queue_id=job_spec.queue_id,
            name=job_spec.name,
            payload=job_spec.payload,
            status=JobStatus.blocked if job_spec.depends_on else JobStatus.queued,
            job_type=JobType.immediate,
            priority=job_spec.priority,
            max_runtime_seconds=job_spec.max_runtime_seconds,
            max_attempts=job_spec.max_attempts,
            retry_strategy=job_spec.retry_strategy.value,
            base_delay_seconds=job_spec.base_delay_seconds,
            max_delay_seconds=job_spec.max_delay_seconds,
            tags=job_spec.tags,
        )
        db.add(job)
        await db.flush()
        ref_to_job[job_spec.ref] = job

    dependency_map: dict[str, list[str]] = {}
    for job_spec in payload.jobs:
        dependency_map[job_spec.ref] = job_spec.depends_on
        for dep_ref in job_spec.depends_on:
            db.add(
                JobDependency(
                    job_id=ref_to_job[job_spec.ref].id,
                    depends_on_job_id=ref_to_job[dep_ref].id,
                )
            )

    await db.commit()
    for job in ref_to_job.values():
        await db.refresh(job)

    return WorkflowCreateResult(
        name=payload.name,
        jobs=[
            WorkflowJobResult(ref=ref, id=job.id, name=job.name, status=job.status)
            for ref, job in ref_to_job.items()
        ],
        dependency_map=dependency_map,
    )
