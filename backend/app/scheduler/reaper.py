import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatus
from app.models.worker import Worker, WorkerStatus
from app.websocket.events import publish_event

logger = logging.getLogger("reaper")

STALE_WORKER_THRESHOLD_SECONDS = 45
REQUEUABLE_STATUSES = (JobStatus.claimed, JobStatus.running)


async def reap_once(redis_client: Redis | None = None) -> list[uuid.UUID]:
    """Find workers that have gone silent, mark them offline, and requeue
    whatever they had claimed/running. Returns the ids of workers reaped.

    Jobs re-queued this way keep their already-incremented `attempts` count —
    a reaper requeue counts as a used attempt, same as any other failure.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=STALE_WORKER_THRESHOLD_SECONDS)
    reaped_worker_ids: list[uuid.UUID] = []

    async with AsyncSessionLocal() as db:
        stale_workers = (
            (
                await db.execute(
                    select(Worker).where(Worker.status != WorkerStatus.offline, Worker.last_seen < cutoff)
                )
            )
            .scalars()
            .all()
        )

        for worker in stale_workers:
            worker.status = WorkerStatus.offline
            await db.execute(
                update(Job)
                .where(Job.worker_id == worker.id, Job.status.in_(REQUEUABLE_STATUSES))
                .values(status=JobStatus.queued, worker_id=None, claimed_at=None)
            )
            reaped_worker_ids.append(worker.id)

        await db.commit()

    if reaped_worker_ids:
        logger.info("Reaped %d stale worker(s): %s", len(reaped_worker_ids), reaped_worker_ids)

    if redis_client is not None:
        for worker_id in reaped_worker_ids:
            try:
                await publish_event(redis_client, "worker.disconnected", {"worker_id": str(worker_id)})
            except Exception:
                logger.exception("Failed to publish worker.disconnected for %s", worker_id)

    return reaped_worker_ids


async def run_reaper_loop(redis_client: Redis | None = None) -> None:
    while True:
        try:
            await reap_once(redis_client)
        except Exception:
            logger.exception("Error while reaping stale workers")
        await asyncio.sleep(settings.REAPER_INTERVAL_SECONDS)
