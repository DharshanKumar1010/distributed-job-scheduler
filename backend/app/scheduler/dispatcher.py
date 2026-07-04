import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import text, update

from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatus, JobType
from app.models.scheduled_job import ScheduledJob

logger = logging.getLogger("dispatcher")

MATERIALIZER_INTERVAL_SECONDS = 1
CRON_SCHEDULER_INTERVAL_SECONDS = 30

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


async def _run_cron_scheduler_once() -> int:
    created_count = 0
    async with AsyncSessionLocal() as db:
        due_rows = (await db.execute(CRON_CLAIM_QUERY)).mappings().all()

        for row in due_rows:
            template_job = await db.get(Job, row["job_id"])
            if template_job is None:
                # Orphaned scheduled_jobs row (template job was deleted); skip it.
                continue

            now = datetime.now(timezone.utc)
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
            created_count += 1

        await db.commit()
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


async def run_cron_scheduler_loop() -> None:
    while True:
        try:
            count = await _run_cron_scheduler_once()
            if count:
                logger.info("Cron scheduler created %d new job instance(s)", count)
        except Exception:
            logger.exception("Error in cron scheduler loop")
        await asyncio.sleep(CRON_SCHEDULER_INTERVAL_SECONDS)


async def run_dispatcher() -> None:
    await asyncio.gather(run_materializer_loop(), run_cron_scheduler_loop())
