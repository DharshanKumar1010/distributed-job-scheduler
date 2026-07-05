import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter
from redis.asyncio import Redis
from sqlalchemy import text, update

from app.database import AsyncSessionLocal, engine
from app.models.job import Job, JobStatus, JobType
from app.models.scheduled_job import ScheduledJob
from app.scheduler.locks import SCHEDULER_LOCK_ID, RedisLock, acquire_advisory_lock, release_advisory_lock

logger = logging.getLogger("dispatcher")

MATERIALIZER_INTERVAL_SECONDS = 1
CRON_SCHEDULER_INTERVAL_SECONDS = 30
LEADER_RETRY_INTERVAL_SECONDS = 10
CRON_LOCK_TTL_SECONDS = 55

# Materializes due SCHEDULED jobs (delayed/scheduled) to QUEUED so workers can
# claim them. FOR UPDATE SKIP LOCKED so multiple dispatcher instances never
# double-materialize the same row.
#
# Recurring job *templates* are deliberately excluded: a template row is only
# ever a config source for the cron scheduler below (which clones it into a
# fresh `immediate` job each time it's due) and must never become claimable
# and executed itself.
MATERIALIZE_QUERY = text(
    """
    UPDATE jobs
    SET status = 'queued', scheduled_at = NULL
    WHERE id IN (
        SELECT id FROM jobs
        WHERE status = 'scheduled' AND scheduled_at <= now() AND job_type != 'recurring'
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)

# Claims due recurring-job templates so multiple dispatcher instances never
# fire the same cron occurrence twice.
CRON_CLAIM_QUERY = text(
    """
    SELECT id, job_id, cron_expression FROM scheduled_jobs
    WHERE is_active = true AND next_run_at <= now()
    FOR UPDATE SKIP LOCKED
    """
)


async def _run_materializer_once() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(MATERIALIZE_QUERY)
        materialized_ids = [row[0] for row in result.all()]
        await db.commit()
    return len(materialized_ids)


def _cron_lock_key(scheduled_job_id, now: datetime) -> str:
    current_minute = now.strftime("%Y-%m-%dT%H:%M")
    return f"cron:{scheduled_job_id}:{current_minute}"


async def _fire_due_cron_row(db, row, redis_client: Redis | None) -> bool:
    """Fires one due cron row (clones its template into a fresh immediate
    job, advances next_run_at), guarded by a Redis lock keyed on
    (scheduled_job_id, current_minute) so multiple dispatcher instances can
    never both fire the same occurrence - even if their FOR UPDATE SKIP
    LOCKED windows don't overlap. Returns True iff this call fired it.
    """
    now = datetime.now(timezone.utc)
    lock = RedisLock(_cron_lock_key(row["id"], now), ttl_seconds=CRON_LOCK_TTL_SECONDS, redis=redis_client)

    if redis_client is not None:
        acquired = await lock.acquire()
        if not acquired:
            logger.info("Cron %s already fired this minute, skipping", row["job_id"])
            return False

    try:
        template_job = await db.get(Job, row["job_id"])
        if template_job is None:
            # Orphaned scheduled_jobs row (template job was deleted); skip it.
            return False

        new_job = Job(
            queue_id=template_job.queue_id,
            name=template_job.name,
            payload=template_job.payload,
            status=JobStatus.queued,
            priority=template_job.priority,
            job_type=JobType.immediate,
            max_runtime_seconds=template_job.max_runtime_seconds,
            max_attempts=template_job.max_attempts,
            retry_strategy=template_job.retry_strategy,
            base_delay_seconds=template_job.base_delay_seconds,
            max_delay_seconds=template_job.max_delay_seconds,
            tags=template_job.tags,
        )
        db.add(new_job)

        next_run_at = croniter(row["cron_expression"], now).get_next(datetime)
        await db.execute(
            update(ScheduledJob)
            .where(ScheduledJob.id == row["id"])
            .values(next_run_at=next_run_at, last_run_at=now)
        )
        await db.commit()
        return True
    finally:
        if redis_client is not None:
            await lock.release()


async def _run_cron_scheduler_once(redis_client: Redis | None = None) -> int:
    created_count = 0
    async with AsyncSessionLocal() as db:
        due_rows = (await db.execute(CRON_CLAIM_QUERY)).mappings().all()
        for row in due_rows:
            if await _fire_due_cron_row(db, row, redis_client):
                created_count += 1
    return created_count


async def run_materializer_loop() -> None:
    while True:
        try:
            count = await _run_materializer_once()
            if count:
                logger.info("Materialized %d scheduled job(s) to queued", count)
        except Exception:
            logger.exception("Error in materializer loop")
        await asyncio.sleep(MATERIALIZER_INTERVAL_SECONDS)


async def run_cron_scheduler_loop(redis_client: Redis | None = None) -> None:
    while True:
        try:
            count = await _run_cron_scheduler_once(redis_client)
            if count:
                logger.info("Cron scheduler created %d new job instance(s)", count)
        except Exception:
            logger.exception("Error in cron scheduler loop")
        await asyncio.sleep(CRON_SCHEDULER_INTERVAL_SECONDS)


async def run_dispatcher(redis_client: Redis | None = None) -> None:
    await asyncio.gather(run_materializer_loop(), run_cron_scheduler_loop(redis_client))


async def run_dispatcher_with_leader_election(redis_client: Redis | None = None) -> None:
    """Only one dispatcher process actually runs the materializer/cron loops
    (the PRIMARY); every other instance is a STANDBY that just polls for the
    Postgres advisory lock. If the primary's connection dies (crash, restart),
    Postgres auto-releases the lock and a standby picks it up within
    LEADER_RETRY_INTERVAL_SECONDS - zero-downtime failover with no manual
    intervention.
    """
    async with engine.connect() as conn:
        is_leader = False
        dispatcher_task: asyncio.Task | None = None
        try:
            while True:
                if not is_leader:
                    acquired = await acquire_advisory_lock(conn, SCHEDULER_LOCK_ID)
                    if acquired:
                        is_leader = True
                        logger.info("Dispatcher: acquired leader lock, running as PRIMARY")
                        dispatcher_task = asyncio.create_task(run_dispatcher(redis_client))
                    else:
                        logger.info("Dispatcher: lock not available, running as STANDBY")
                if is_leader and dispatcher_task is not None and dispatcher_task.done():
                    # The primary's own loops don't return in normal operation;
                    # if they did (crashed), fall back to re-contending the lock.
                    dispatcher_task.result()
                await asyncio.sleep(LEADER_RETRY_INTERVAL_SECONDS)
        finally:
            if dispatcher_task is not None:
                dispatcher_task.cancel()
            if is_leader:
                await release_advisory_lock(conn, SCHEDULER_LOCK_ID)
