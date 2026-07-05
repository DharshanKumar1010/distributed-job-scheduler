import asyncio
import logging
import os
import random
import signal
import socket
import time
import traceback
import uuid
from datetime import datetime, timezone

import psutil
from redis.asyncio import Redis
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.dead_letter_queue import DeadLetterQueueEntry
from app.models.job import Job, JobStatus
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog, LogLevel
from app.models.project import Project
from app.models.queue import Queue
from app.models.worker import Worker, WorkerHeartbeat, WorkerStatus
from app.services import dependency_service, queue_service
from app.websocket.publisher import publish_event
from app.worker import shard
from app.worker.rate_limit import check_token_bucket, queue_bucket_key
from app.worker.retry import compute_next_run

logger = logging.getLogger("worker")

SHARD_REASSIGN_INTERVAL_SECONDS = 30

# THE MOST IMPORTANT QUERY IN THE ENTIRE PROJECT. Do not "optimize" this into an
# ORM SELECT-then-UPDATE — FOR UPDATE SKIP LOCKED is what makes claiming atomic
# across concurrent workers. See CLAUDE.md.
CLAIM_QUERY = text(
    """
    UPDATE jobs
    SET status = 'claimed',
        worker_id = :worker_id,
        claimed_at = now(),
        attempts = attempts + 1
    WHERE id = (
        SELECT id FROM jobs
        WHERE queue_id = :queue_id
          AND status = 'queued'
          AND (scheduled_at IS NULL OR scheduled_at <= now())
        ORDER BY priority DESC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *
    """
)

# Same claim query, plus a shard filter. hashtext() % N can be negative in
# Postgres (sign follows the dividend), so it's normalized into [0, N) before
# comparing to :shard_id - otherwise roughly half of all jobs would never
# match any shard.
SHARD_CLAIM_QUERY = text(
    """
    UPDATE jobs
    SET status = 'claimed',
        worker_id = :worker_id,
        claimed_at = now(),
        attempts = attempts + 1
    WHERE id = (
        SELECT id FROM jobs
        WHERE queue_id = :queue_id
          AND status = 'queued'
          AND (scheduled_at IS NULL OR scheduled_at <= now())
          AND (((hashtext(id::text) % :shard_count) + :shard_count) % :shard_count) = :shard_id
        ORDER BY priority DESC, created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *
    """
)


async def _run_handler(payload: dict, attempt_number: int) -> None:
    """Execute a job's work.

    Real handler dispatch is out of scope for this phase. To avoid executing
    arbitrary code from user-supplied payloads (an injection risk), only a
    small fixed set of demo handlers is supported; anything else falls back
    to a simulated delay.
    """
    handler_name = payload.get("handler") if isinstance(payload, dict) else None

    if handler_name == "fail":
        raise RuntimeError(payload.get("error_message", "Simulated handler failure"))
    if handler_name == "fail_until_attempt":
        succeed_on_attempt = int(payload.get("succeed_on_attempt", 1))
        if attempt_number < succeed_on_attempt:
            raise RuntimeError(f"Simulated failure on attempt {attempt_number}")
        return
    if handler_name == "sleep":
        await asyncio.sleep(float(payload.get("seconds", 1)))
        return
    if handler_name == "noop":
        return

    await asyncio.sleep(random.uniform(1, 5))


class JobWorker:
    def __init__(self, queue_id: uuid.UUID):
        self.queue_id = queue_id
        self.worker_id: uuid.UUID | None = None
        self.org_id: uuid.UUID | None = None
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.active_tasks: dict[uuid.UUID, asyncio.Task] = {}
        self.redis: Redis | None = None
        self._stopping = asyncio.Event()
        self._process = psutil.Process(self.pid)
        self.shard_count = 1
        self.assigned_shard = 0
        self._shard_id_override: int | None = None
        self._next_shard_refresh = 0.0

    # ------------------------------------------------------------------ #
    # Startup / shutdown
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        self._install_signal_handlers()

        self.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await self.redis.ping()

        # Prime psutil's cpu_percent baseline; its first reading is always 0.0.
        self._process.cpu_percent(interval=None)

        async with AsyncSessionLocal() as db:
            queue = await db.get(Queue, self.queue_id)
            if queue is None:
                raise RuntimeError(f"Queue {self.queue_id} does not exist")

            project = await db.get(Project, queue.project_id)
            if project is None:
                raise RuntimeError(f"Project {queue.project_id} does not exist")
            self.org_id = project.org_id

            worker = Worker(
                queue_id=self.queue_id,
                hostname=self.hostname,
                pid=self.pid,
                status=WorkerStatus.idle,
                max_concurrency=settings.WORKER_CONCURRENCY,
                current_jobs=0,
                last_seen=datetime.now(timezone.utc),
            )
            db.add(worker)
            await db.commit()
            await db.refresh(worker)
            self.worker_id = worker.id

            self.shard_count = queue.shard_count
            shard_env = os.environ.get("SHARD_ID")
            if shard_env is not None:
                self._shard_id_override = int(shard_env)
                self.assigned_shard = self._shard_id_override % max(1, self.shard_count)
            elif self.shard_count > 1:
                self.assigned_shard = await shard.assign_shard(
                    self.worker_id, self.queue_id, self.shard_count, db, self.redis
                )
            else:
                self.assigned_shard = 0

        logger.info(
            "Worker %s claiming shard %d/%d of queue %s",
            self.worker_id,
            self.assigned_shard,
            self.shard_count,
            queue.name,
        )

        logger.info("Worker %s started, watching queue %s", self.worker_id, self.queue_id)
        await self._publish_event(
            "worker.connected", {"worker_id": str(self.worker_id), "queue_id": str(self.queue_id)}
        )

        poll_task = asyncio.create_task(self._poll_loop())
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        await asyncio.gather(poll_task, heartbeat_task)
        await self._graceful_shutdown()

    def request_stop(self) -> None:
        self._stopping.set()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.request_stop)
            except NotImplementedError:
                # Windows' event loop can't register POSIX signal handlers;
                # fall back to the (best-effort) synchronous signal module.
                signal.signal(sig, lambda *_args: self.request_stop())

    async def _graceful_shutdown(self) -> None:
        if self.active_tasks:
            logger.info("Waiting for %d active job(s) to finish", len(self.active_tasks))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.active_tasks.values(), return_exceptions=True),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Timed out after 30s waiting for %d active job(s)", len(self.active_tasks)
                )

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Worker).where(Worker.id == self.worker_id).values(status=WorkerStatus.offline)
            )
            await db.commit()

        await self._publish_event(
            "worker.disconnected", {"worker_id": str(self.worker_id), "queue_id": str(self.queue_id)}
        )
        if self.redis is not None:
            await self.redis.aclose()

        logger.info("Worker shut down cleanly")

    # ------------------------------------------------------------------ #
    # Polling loop
    # ------------------------------------------------------------------ #

    async def _poll_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._poll_once()
            except Exception:
                logger.exception("Error while polling queue %s", self.queue_id)
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=settings.WORKER_POLL_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass

    async def _poll_once(self) -> None:
        if self._stopping.is_set():
            return

        async with AsyncSessionLocal() as db:
            queue = await db.get(Queue, self.queue_id)
            if queue is None or not queue.is_active or queue.is_paused:
                return

            if len(self.active_tasks) >= min(queue.concurrency_limit, settings.WORKER_CONCURRENCY):
                return

            if self.shard_count > 1:
                result = await db.execute(
                    SHARD_CLAIM_QUERY,
                    {
                        "worker_id": self.worker_id,
                        "queue_id": self.queue_id,
                        "shard_count": self.shard_count,
                        "shard_id": self.assigned_shard,
                    },
                )
            else:
                result = await db.execute(
                    CLAIM_QUERY, {"worker_id": self.worker_id, "queue_id": self.queue_id}
                )
            row = result.mappings().first()
            await db.commit()

        if row is None:
            return

        job_row = dict(row)
        job_id = job_row["id"]

        if queue.rate_limit_per_minute and self.redis is not None:
            capacity = queue.rate_limit_burst or queue.rate_limit_per_minute
            refill_rate = queue.rate_limit_per_minute / 60.0
            allowed, tokens_remaining = await check_token_bucket(
                self.redis, queue_bucket_key(queue.id), capacity, refill_rate
            )
            if not allowed:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(Job)
                        .where(Job.id == job_id)
                        .values(
                            status=JobStatus.queued,
                            worker_id=None,
                            claimed_at=None,
                            attempts=Job.attempts - 1,
                        )
                    )
                    await db.commit()
                logger.info(
                    "Rate limited on queue %s — %.2f tokens remaining", queue.name, tokens_remaining
                )
                await self._publish_event(
                    "queue.rate_limited",
                    {
                        "queue_id": str(queue.id),
                        "queue_name": queue.name,
                        "tokens_remaining": tokens_remaining,
                    },
                )
                await asyncio.sleep(1 / refill_rate)
                return

        await self._publish_event(
            "job.claimed",
            {
                "job_id": str(job_id),
                "name": job_row["name"],
                "queue_id": str(job_row["queue_id"]),
                "worker_id": str(self.worker_id),
                "attempts": job_row["attempts"],
            },
        )
        await self._publish_queue_stats(job_row["queue_id"])

        task = asyncio.create_task(self._execute_job(job_row))
        self.active_tasks[job_id] = task
        task.add_done_callback(lambda _t, jid=job_id: asyncio.create_task(self._on_job_task_done(jid)))

    async def _on_job_task_done(self, job_id: uuid.UUID) -> None:
        self.active_tasks.pop(job_id, None)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Worker)
                .where(Worker.id == self.worker_id)
                .values(
                    current_jobs=len(self.active_tasks),
                    status=WorkerStatus.busy if self.active_tasks else WorkerStatus.idle,
                )
            )
            await db.commit()

    # ------------------------------------------------------------------ #
    # Job execution
    # ------------------------------------------------------------------ #

    async def _execute_job(self, job_row: dict) -> None:
        job_id = job_row["id"]
        attempt_number = job_row["attempts"]

        started_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=JobStatus.running, started_at=started_at)
            )
            execution = JobExecution(
                job_id=job_id,
                worker_id=self.worker_id,
                attempt_number=attempt_number,
                status=JobStatus.running,
                started_at=started_at,
            )
            db.add(execution)
            await db.commit()
            await db.refresh(execution)
            execution_id = execution.id

        await self._publish_event(
            "job.running",
            {
                "job_id": str(job_id),
                "name": job_row["name"],
                "queue_id": str(job_row["queue_id"]),
                "worker_id": str(self.worker_id),
                "started_at": started_at.isoformat(),
            },
        )
        await self._publish_queue_stats(job_row["queue_id"])

        error: Exception | None = None
        tb: str | None = None
        try:
            await _run_handler(job_row.get("payload") or {}, attempt_number)
        except Exception as exc:  # noqa: BLE001 - a bad job must never crash the worker
            error = exc
            tb = traceback.format_exc()

        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)

        if error is None:
            await self._finish_success(job_id, execution_id, completed_at, duration_ms)
            async with AsyncSessionLocal() as db:
                await dependency_service.check_and_unblock(job_id, db, self.redis, self.org_id)
            await self._publish_event(
                "job.completed",
                {
                    "job_id": str(job_id),
                    "name": job_row["name"],
                    "queue_id": str(job_row["queue_id"]),
                    "duration_ms": duration_ms,
                    "attempts": attempt_number,
                },
            )
        else:
            await self._finish_failure(
                job_row, execution_id, completed_at, duration_ms, attempt_number, error, tb
            )

        await self._publish_queue_stats(job_row["queue_id"])

    async def _finish_success(
        self,
        job_id: uuid.UUID,
        execution_id: uuid.UUID,
        completed_at: datetime,
        duration_ms: int,
    ) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=JobStatus.completed, completed_at=completed_at, result={"success": True})
            )
            await db.execute(
                update(JobExecution)
                .where(JobExecution.id == execution_id)
                .values(status=JobStatus.completed, completed_at=completed_at, duration_ms=duration_ms)
            )
            db.add(
                JobLog(
                    job_id=job_id,
                    execution_id=execution_id,
                    level=LogLevel.info,
                    message="Job completed successfully",
                    timestamp=completed_at,
                )
            )
            await db.commit()

    async def _finish_failure(
        self,
        job_row: dict,
        execution_id: uuid.UUID,
        completed_at: datetime,
        duration_ms: int,
        attempt_number: int,
        error: Exception,
        tb: str | None,
    ) -> None:
        job_id = job_row["id"]

        async with AsyncSessionLocal() as db:
            db.add(
                JobLog(
                    job_id=job_id,
                    execution_id=execution_id,
                    level=LogLevel.error,
                    message=str(error),
                    timestamp=completed_at,
                    extra_metadata={"traceback": tb},
                )
            )
            await db.execute(
                update(JobExecution)
                .where(JobExecution.id == execution_id)
                .values(
                    status=JobStatus.failed,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    error_message=str(error),
                    error_traceback=tb,
                )
            )

            will_retry = attempt_number < job_row["max_attempts"]
            next_run: datetime | None = None

            if will_retry:
                next_run = compute_next_run(
                    job_row["retry_strategy"],
                    job_row["base_delay_seconds"],
                    attempt_number,
                    job_row["max_delay_seconds"],
                )
                await db.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(
                        status=JobStatus.queued,
                        scheduled_at=next_run,
                        worker_id=None,
                        error_message=str(error),
                        error_traceback=tb,
                    )
                )
            else:
                await db.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(
                        status=JobStatus.dead,
                        failed_at=completed_at,
                        error_message=str(error),
                        error_traceback=tb,
                    )
                )
                db.add(
                    DeadLetterQueueEntry(
                        job_id=job_id,
                        queue_id=job_row["queue_id"],
                        failed_at=completed_at,
                        total_attempts=attempt_number,
                        last_error=str(error),
                        last_traceback=tb,
                    )
                )

            await db.commit()

        await self._publish_event(
            "job.failed",
            {
                "job_id": str(job_id),
                "name": job_row["name"],
                "queue_id": str(job_row["queue_id"]),
                "error_message": str(error),
                "attempts": attempt_number,
                "max_attempts": job_row["max_attempts"],
                "next_retry_at": next_run.isoformat() if next_run else None,
                "will_retry": will_retry,
            },
        )

        if not will_retry:
            await self._publish_event(
                "job.dead",
                {
                    "job_id": str(job_id),
                    "name": job_row["name"],
                    "queue_id": str(job_row["queue_id"]),
                    "total_attempts": attempt_number,
                    "last_error": str(error),
                },
            )

    async def _publish_queue_stats(self, queue_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as db:
            pending, running, failed, _throughput = await queue_service.get_stats_for_queue(
                db, queue_id
            )
        await self._publish_event(
            "queue.stats",
            {
                "queue_id": str(queue_id),
                "pending_count": pending,
                "running_count": running,
                "failed_count": failed,
            },
        )

    # ------------------------------------------------------------------ #
    # Heartbeat loop
    # ------------------------------------------------------------------ #

    async def _heartbeat_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await self._send_heartbeat()
            except Exception:
                logger.exception("Error while sending heartbeat for worker %s", self.worker_id)
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=settings.HEARTBEAT_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass

    async def _maybe_refresh_shard_assignment(self) -> None:
        """Re-registers this worker in the queue's active-workers set every
        SHARD_REASSIGN_INTERVAL_SECONDS, so shard assignments reshuffle
        automatically as workers join/leave or shard_count changes - without
        needing a restart. A worker pinned via SHARD_ID never reassigns.
        """
        now = time.monotonic()
        if now < self._next_shard_refresh:
            return
        self._next_shard_refresh = now + SHARD_REASSIGN_INTERVAL_SECONDS

        if self._shard_id_override is not None:
            return

        async with AsyncSessionLocal() as db:
            queue = await db.get(Queue, self.queue_id)
            if queue is None:
                return
            self.shard_count = queue.shard_count
            if self.shard_count <= 1:
                self.assigned_shard = 0
                return
            if self.redis is not None:
                self.assigned_shard = await shard.assign_shard(
                    self.worker_id, self.queue_id, self.shard_count, db, self.redis
                )

    async def _send_heartbeat(self) -> None:
        await self._maybe_refresh_shard_assignment()

        cpu_pct: float | None = None
        mem_pct: float | None = None
        try:
            cpu_pct = self._process.cpu_percent(interval=None)
            mem_pct = self._process.memory_percent()
        except Exception:
            logger.debug("Failed to read process stats", exc_info=True)

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            db.add(
                WorkerHeartbeat(
                    worker_id=self.worker_id,
                    ts=now,
                    cpu_pct=cpu_pct,
                    mem_pct=mem_pct,
                    active_job_count=len(self.active_tasks),
                )
            )
            await db.execute(
                update(Worker)
                .where(Worker.id == self.worker_id)
                .values(
                    last_seen=now,
                    current_jobs=len(self.active_tasks),
                    status=WorkerStatus.busy if self.active_tasks else WorkerStatus.idle,
                )
            )
            await db.commit()

        await self._publish_event(
            "worker.heartbeat",
            {
                "worker_id": str(self.worker_id),
                "hostname": self.hostname,
                "queue_id": str(self.queue_id),
                "cpu_pct": cpu_pct,
                "mem_pct": mem_pct,
                "active_jobs": len(self.active_tasks),
                "max_concurrency": settings.WORKER_CONCURRENCY,
            },
        )

    # ------------------------------------------------------------------ #
    # Misc
    # ------------------------------------------------------------------ #

    async def _publish_event(self, event: str, data: dict) -> None:
        if self.redis is None or self.org_id is None:
            return
        try:
            await publish_event(self.redis, self.org_id, event, data)
        except Exception:
            logger.exception("Failed to publish %s event", event)


async def run(queue_id: uuid.UUID) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    worker = JobWorker(queue_id)
    await worker.start()
