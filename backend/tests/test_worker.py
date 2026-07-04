import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.dead_letter_queue import DeadLetterQueueEntry
from app.models.job import Job, JobStatus, JobType
from app.models.job_execution import JobExecution
from app.models.worker import Worker, WorkerStatus
from app.scheduler.reaper import reap_once
from app.worker.worker import JobWorker


async def _create_job(queue_id: uuid.UUID, **overrides) -> Job:
    defaults = dict(
        queue_id=queue_id,
        name="test-job",
        payload={},
        status=JobStatus.queued,
        job_type=JobType.immediate,
        max_attempts=3,
        retry_strategy="fixed",
        base_delay_seconds=0,
        max_delay_seconds=60,
    )
    defaults.update(overrides)
    async with AsyncSessionLocal() as db:
        job = Job(**defaults)
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job


async def _register_worker(queue_id: uuid.UUID, **overrides) -> Worker:
    defaults = dict(
        queue_id=queue_id,
        hostname="test-host",
        pid=1234,
        status=WorkerStatus.idle,
        last_seen=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    async with AsyncSessionLocal() as db:
        worker = Worker(**defaults)
        db.add(worker)
        await db.commit()
        await db.refresh(worker)
        return worker


async def _make_job_worker(queue_id: uuid.UUID) -> JobWorker:
    """A JobWorker wired to a real DB-registered Worker row, without redis/signals."""
    worker_row = await _register_worker(queue_id)
    job_worker = JobWorker(queue_id)
    job_worker.worker_id = worker_row.id
    return job_worker


async def _run_one_claim_cycle(worker: JobWorker) -> uuid.UUID | None:
    """Runs one poll iteration and, if a job was claimed, waits for it to finish."""
    before = set(worker.active_tasks.keys())
    await worker._poll_once()
    new_ids = set(worker.active_tasks.keys()) - before
    if not new_ids:
        return None

    job_id = next(iter(new_ids))
    await worker.active_tasks[job_id]
    await asyncio.sleep(0.1)  # let the done_callback's scheduled task pop active_tasks
    return job_id


async def test_job_that_always_fails_lands_in_dlq(test_queue):
    job = await _create_job(
        test_queue,
        payload={"handler": "fail", "error_message": "always fails"},
        max_attempts=2,
    )
    worker = await _make_job_worker(test_queue)

    for _ in range(2):
        claimed_id = await _run_one_claim_cycle(worker)
        assert claimed_id == job.id

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Job, job.id)
        assert refreshed.status == JobStatus.dead
        assert refreshed.attempts == 2

        dlq_entry = await db.scalar(
            select(DeadLetterQueueEntry).where(DeadLetterQueueEntry.job_id == job.id)
        )
        assert dlq_entry is not None
        assert dlq_entry.total_attempts == 2
        assert "always fails" in dlq_entry.last_error


async def test_job_fails_twice_then_succeeds(test_queue):
    job = await _create_job(
        test_queue,
        payload={"handler": "fail_until_attempt", "succeed_on_attempt": 3},
        max_attempts=5,
    )
    worker = await _make_job_worker(test_queue)

    for _ in range(3):
        claimed_id = await _run_one_claim_cycle(worker)
        assert claimed_id == job.id

    async with AsyncSessionLocal() as db:
        refreshed = await db.get(Job, job.id)
        assert refreshed.status == JobStatus.completed

        executions = (
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
        assert len(executions) == 3
        assert [e.status for e in executions] == [
            JobStatus.failed,
            JobStatus.failed,
            JobStatus.completed,
        ]


async def test_reaper_requeues_jobs_from_stale_worker(test_queue):
    stale_worker = await _register_worker(
        test_queue,
        status=WorkerStatus.busy,
        last_seen=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    job = await _create_job(
        test_queue,
        status=JobStatus.running,
        worker_id=stale_worker.id,
        claimed_at=datetime.now(timezone.utc),
        attempts=1,
    )

    reaped_ids = await reap_once()
    assert stale_worker.id in reaped_ids

    async with AsyncSessionLocal() as db:
        refreshed_worker = await db.get(Worker, stale_worker.id)
        assert refreshed_worker.status == WorkerStatus.offline

        refreshed_job = await db.get(Job, job.id)
        assert refreshed_job.status == JobStatus.queued
        assert refreshed_job.worker_id is None
        assert refreshed_job.claimed_at is None
        # Attempts is untouched by the reaper - the claim that made it "running"
        # already counted, and the requeue itself doesn't add another.
        assert refreshed_job.attempts == 1


async def test_concurrent_workers_claim_same_job_exactly_once(test_queue):
    job = await _create_job(test_queue, payload={"handler": "noop"})

    worker_a = await _make_job_worker(test_queue)
    worker_b = await _make_job_worker(test_queue)

    await asyncio.gather(worker_a._poll_once(), worker_b._poll_once())

    claimed_by = [w for w in (worker_a, worker_b) if job.id in w.active_tasks]
    assert len(claimed_by) == 1

    await asyncio.gather(*claimed_by[0].active_tasks.values())
    await asyncio.sleep(0.1)

    async with AsyncSessionLocal() as db:
        executions = (
            (await db.execute(select(JobExecution).where(JobExecution.job_id == job.id)))
            .scalars()
            .all()
        )
        assert len(executions) == 1

        refreshed = await db.get(Job, job.id)
        assert refreshed.status == JobStatus.completed
        assert refreshed.attempts == 1
