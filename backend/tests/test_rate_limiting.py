import asyncio
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.middleware.rate_limit import build_429_headers, check_sliding_window
from app.models.job import Job, JobStatus, JobType
from app.models.scheduled_job import ScheduledJob
from app.scheduler.dispatcher import _fire_due_cron_row
from app.worker.rate_limit import check_token_bucket


def _redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def test_sliding_window_allows_limit_then_429_with_headers():
    redis_client = _redis()
    key = f"test:ratelimit:{uuid.uuid4().hex}"
    await redis_client.delete(key)
    try:
        for i in range(1, 101):
            result = await check_sliding_window(redis_client, key, limit=100)
            assert result.allowed is True
            assert result.count == i

        blocked = await check_sliding_window(redis_client, key, limit=100)
        assert blocked.allowed is False
        assert blocked.count == 100

        headers = build_429_headers(100, blocked)
        assert headers["X-RateLimit-Limit"] == "100"
        assert headers["X-RateLimit-Remaining"] == "0"
        assert int(headers["X-RateLimit-Reset"]) > 0
        assert int(headers["Retry-After"]) >= 1
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()


async def test_sliding_window_resets_after_window_elapses():
    redis_client = _redis()
    key = f"test:ratelimit:{uuid.uuid4().hex}"
    await redis_client.delete(key)
    try:
        now_ms = 1_000_000_000_000.0  # arbitrary fixed synthetic clock
        window_ms = 60_000

        for i in range(1, 6):
            result = await check_sliding_window(
                redis_client, key, limit=5, window_ms=window_ms, now_ms=now_ms
            )
            assert result.allowed is True
            assert result.count == i

        still_blocked = await check_sliding_window(
            redis_client, key, limit=5, window_ms=window_ms, now_ms=now_ms
        )
        assert still_blocked.allowed is False

        # Jump the synthetic clock past the 60s window - old entries fall out.
        after_window = await check_sliding_window(
            redis_client, key, limit=5, window_ms=window_ms, now_ms=now_ms + window_ms + 1
        )
        assert after_window.allowed is True
        assert after_window.count == 1
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()


async def test_token_bucket_burst_then_refill():
    redis_client = _redis()
    key = f"test:tokenbucket:{uuid.uuid4().hex}"
    await redis_client.delete(key)
    try:
        capacity = 10.0
        refill_rate = 10.0  # tokens/sec
        now = 1_700_000_000.0

        for _ in range(10):
            allowed, _tokens = await check_token_bucket(redis_client, key, capacity, refill_rate, now=now)
            assert allowed is True

        denied, tokens_after_burst = await check_token_bucket(redis_client, key, capacity, refill_rate, now=now)
        assert denied is False
        assert tokens_after_burst < 1

        allowed_after_refill, remaining = await check_token_bucket(
            redis_client, key, capacity, refill_rate, now=now + 1.0
        )
        assert allowed_after_refill is True
        assert remaining > 5
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()


async def test_sliding_window_lua_is_atomic_under_concurrency():
    redis_client = _redis()
    key = f"test:ratelimit:{uuid.uuid4().hex}"
    await redis_client.delete(key)
    try:
        limit = 20
        results = await asyncio.gather(
            *[check_sliding_window(redis_client, key, limit=limit) for _ in range(50)]
        )
        allowed_count = sum(1 for r in results if r.allowed)
        assert allowed_count == limit
    finally:
        await redis_client.delete(key)
        await redis_client.aclose()


async def test_cron_dedup_exactly_one_job_created(test_org_queue):
    _org_id, queue_id = test_org_queue
    redis_client = _redis()
    template_name = f"cron-template-{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        template = Job(
            queue_id=queue_id,
            name=template_name,
            payload={},
            status=JobStatus.scheduled,
            job_type=JobType.recurring,
            max_attempts=3,
            retry_strategy="fixed",
            base_delay_seconds=0,
            max_delay_seconds=60,
            cron_expression="* * * * *",
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)

        scheduled = ScheduledJob(
            job_id=template.id,
            next_run_at=datetime.now(timezone.utc),
            cron_expression="* * * * *",
            is_active=True,
        )
        db.add(scheduled)
        await db.commit()
        await db.refresh(scheduled)

    row = {"id": scheduled.id, "job_id": template.id, "cron_expression": "* * * * *"}

    async def fire() -> bool:
        async with AsyncSessionLocal() as db:
            return await _fire_due_cron_row(db, row, redis_client)

    try:
        results = await asyncio.gather(fire(), fire())
        assert sorted(results) == [False, True]

        async with AsyncSessionLocal() as db:
            created_count = await db.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.name == template_name, Job.job_type == JobType.immediate)
            )
        assert created_count == 1
    finally:
        await redis_client.delete(f"lock:cron:{scheduled.id}:{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M')}")
        await redis_client.aclose()
