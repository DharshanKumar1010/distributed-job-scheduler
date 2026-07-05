import asyncio
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import func, select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatus, JobType
from app.models.job_execution import JobExecution
from app.models.queue import Queue
from app.models.worker import Worker, WorkerStatus
from app.worker import shard
from app.worker.worker import JobWorker


def _redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def _set_shard_count(queue_id: uuid.UUID, shard_count: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(Queue).where(Queue.id == queue_id).values(shard_count=shard_count))
        await db.commit()


async def _create_job(queue_id: uuid.UUID, **overrides) -> Job:
    defaults = dict(
        queue_id=queue_id,
        name="test-job",
        payload={"handler": "noop"},
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


async def _make_job_worker_with_shard(
    queue_id: uuid.UUID, shard_count: int, assigned_shard: int, worker_id: uuid.UUID | None = None
) -> JobWorker:
    """A JobWorker wired to a real DB-registered Worker row, without
    redis/signals, with its shard assignment set directly (bypassing the
    normal start()/assign_shard() dance so tests can pin exact shards).
    """
    worker_row = await _register_worker(queue_id, id=worker_id) if worker_id else await _register_worker(queue_id)
    job_worker = JobWorker(queue_id)
    job_worker.worker_id = worker_row.id
    job_worker.shard_count = shard_count
    job_worker.assigned_shard = assigned_shard
    return job_worker


async def _drain_worker(worker: JobWorker, max_iterations: int = 50) -> int:
    """Repeatedly polls a worker until it stops claiming new jobs. Returns
    how many jobs it claimed and ran to completion.
    """
    claimed = 0
    for _ in range(max_iterations):
        before = set(worker.active_tasks.keys())
        await worker._poll_once()
        new_ids = set(worker.active_tasks.keys()) - before
        if not new_ids:
            break
        job_id = next(iter(new_ids))
        await worker.active_tasks[job_id]
        await asyncio.sleep(0.05)
        claimed += 1
    return claimed


async def test_shard_count_one_is_backward_compatible(test_queue):
    queue_id = test_queue
    for i in range(5):
        await _create_job(queue_id, name=f"job-{i}")

    worker_row = await _register_worker(queue_id)
    worker = JobWorker(queue_id)
    worker.worker_id = worker_row.id
    assert worker.shard_count == 1  # default, no shard.assign_shard ever called

    claimed = await _drain_worker(worker, max_iterations=10)
    assert claimed == 5

    async with AsyncSessionLocal() as db:
        completed = await db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.queue_id == queue_id, Job.status == JobStatus.completed)
        )
    assert completed == 5


async def test_three_shards_three_workers_partition_jobs_disjointly(test_queue):
    queue_id = test_queue
    await _set_shard_count(queue_id, 3)

    redis_client = _redis()
    key = shard.workers_key(queue_id)
    await redis_client.delete(key)

    try:
        # Assignments only converge once ALL workers are registered (each
        # worker's position depends on who else is active) - so register
        # everyone first, then do a second pass to get each one's final,
        # stable assignment. This mirrors production: workers re-register
        # every 30s, so a transient assignment from mid-rollout self-corrects
        # on the next round.
        worker_ids = [uuid.uuid4() for _ in range(3)]
        async with AsyncSessionLocal() as db:
            for wid in worker_ids:
                await shard.assign_shard(wid, queue_id, 3, db, redis_client)
            final_shards = {
                wid: await shard.assign_shard(wid, queue_id, 3, db, redis_client) for wid in worker_ids
            }

        workers = [
            await _make_job_worker_with_shard(queue_id, 3, final_shards[wid], worker_id=wid)
            for wid in worker_ids
        ]

        assert {w.assigned_shard for w in workers} == {0, 1, 2}

        for i in range(30):
            await _create_job(queue_id, name=f"job-{i}")

        counts = [await _drain_worker(w, max_iterations=20) for w in workers]

        assert sum(counts) == 30
        for c in counts:
            assert abs(c - 10) <= 5

        async with AsyncSessionLocal() as db:
            total_completed = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.queue_id == queue_id, Job.status == JobStatus.completed)
            )
            total_executions = await db.scalar(
                select(func.count())
                .select_from(JobExecution)
                .join(Job, Job.id == JobExecution.job_id)
                .where(Job.queue_id == queue_id)
            )
        assert total_completed == 30
        assert total_executions == 30
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()


async def test_single_worker_with_three_shards_only_processes_its_shard(test_queue):
    queue_id = test_queue
    await _set_shard_count(queue_id, 3)

    redis_client = _redis()
    key = shard.workers_key(queue_id)
    await redis_client.delete(key)

    try:
        worker_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            assigned = await shard.assign_shard(worker_id, queue_id, 3, db, redis_client)
        assert assigned == 0  # sole active worker -> position 0 -> shard 0

        for i in range(30):
            await _create_job(queue_id, name=f"job-{i}")

        worker = await _make_job_worker_with_shard(queue_id, 3, assigned, worker_id=worker_id)
        claimed = await _drain_worker(worker, max_iterations=40)
        assert claimed > 0

        async with AsyncSessionLocal() as db:
            completed = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.queue_id == queue_id, Job.status == JobStatus.completed)
            )
            still_queued = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.queue_id == queue_id, Job.status == JobStatus.queued)
            )
        # Only shard 0's jobs got processed; shards 1 and 2 are left untouched.
        assert completed == claimed
        assert still_queued > 0
        assert completed + still_queued == 30
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()


async def test_worker_leave_does_not_let_survivor_steal_other_shard(test_queue):
    queue_id = test_queue
    await _set_shard_count(queue_id, 2)

    redis_client = _redis()
    key = shard.workers_key(queue_id)
    await redis_client.delete(key)

    try:
        worker_a_id, worker_b_id = uuid.uuid4(), uuid.uuid4()
        async with AsyncSessionLocal() as db:
            # First pass registers both; second pass gets each one's
            # converged assignment now that both are known to be active.
            await shard.assign_shard(worker_a_id, queue_id, 2, db, redis_client)
            await shard.assign_shard(worker_b_id, queue_id, 2, db, redis_client)
            shard_a = await shard.assign_shard(worker_a_id, queue_id, 2, db, redis_client)
            shard_b = await shard.assign_shard(worker_b_id, queue_id, 2, db, redis_client)
        assert {shard_a, shard_b} == {0, 1}

        for i in range(20):
            await _create_job(queue_id, name=f"job-{i}")

        # worker_b "dies" (request_stop() + its Redis registration ages out /
        # gets dropped rather than waiting 45 real seconds for it to expire).
        await redis_client.zrem(key, str(worker_b_id))

        async with AsyncSessionLocal() as db:
            new_shard_a = await shard.assign_shard(worker_a_id, queue_id, 2, db, redis_client)

        worker_a = await _make_job_worker_with_shard(queue_id, 2, new_shard_a, worker_id=worker_a_id)
        await _drain_worker(worker_a, max_iterations=40)

        async with AsyncSessionLocal() as db:
            still_queued = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.queue_id == queue_id, Job.status == JobStatus.queued)
            )
            completed = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.queue_id == queue_id, Job.status == JobStatus.completed)
            )
        # The survivor only ever covers ONE shard - jobs hashing to the other
        # shard are never touched (no automatic take-over of the dead
        # worker's shard). This is the documented trade-off.
        assert completed + still_queued == 20
        assert still_queued > 0
        assert completed > 0
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()
