import logging
import time
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("shard")

WORKER_KEY_TTL_SECONDS = 60
ACTIVE_WINDOW_SECONDS = 45

# hashtext() % N in Postgres can be negative (Postgres' % follows the sign of
# the dividend, not Python's always-non-negative modulo) - normalize into
# [0, shard_count) so every job maps to exactly one real shard.
_SHARD_EXPR = "(((hashtext(id::text) % :shard_count) + :shard_count) % :shard_count)"

SHARD_STATS_QUERY = text(f"""
    SELECT
      {_SHARD_EXPR} as shard_id,
      COUNT(*) FILTER (WHERE status = 'queued') as pending,
      COUNT(*) FILTER (WHERE status = 'running') as running
    FROM jobs
    WHERE queue_id = :queue_id
    GROUP BY shard_id
    """)


@dataclass
class ShardAssignment:
    queue_id: uuid.UUID
    shard_count: int
    worker_id: uuid.UUID
    assigned_shard: int
    total_workers_on_queue: int


def workers_key(queue_id: uuid.UUID) -> str:
    return f"shard:workers:{queue_id}"


def _shard_for_position(position: int, shard_count: int) -> int:
    return position % shard_count if shard_count > 0 else 0


async def _active_sorted_workers(
    redis: Redis, queue_id: uuid.UUID, now: float
) -> list[str]:
    raw = await redis.zrangebyscore(
        workers_key(queue_id), now - ACTIVE_WINDOW_SECONDS, "+inf"
    )
    return sorted(raw)


def compute_shard_map(
    active_sorted: list[str], shard_count: int
) -> dict[int, list[str]]:
    shard_map: dict[int, list[str]] = {i: [] for i in range(shard_count)}
    for position, worker_id in enumerate(active_sorted):
        shard_map[_shard_for_position(position, shard_count)].append(worker_id)
    return shard_map


async def assign_shard(
    worker_id: uuid.UUID,
    queue_id: uuid.UUID,
    shard_count: int,
    db: AsyncSession,
    redis: Redis,
) -> int:
    """Consistent-hashing-style shard assignment: workers register themselves
    in a Redis sorted set (score = last-seen timestamp), and a worker's shard
    is its lexicographic position among currently-active workers, mod
    shard_count. Re-registering periodically keeps the set fresh so shards
    reshuffle automatically as workers join/leave - no central coordinator,
    no fixed hash ring to maintain.
    """
    key = workers_key(queue_id)
    now = time.time()

    await redis.zadd(key, {str(worker_id): now})
    await redis.expire(key, WORKER_KEY_TTL_SECONDS)

    active_sorted = await _active_sorted_workers(redis, queue_id, now)
    if str(worker_id) not in active_sorted:
        # Clock/replication lag between the ZADD and ZRANGEBYSCORE read; make
        # sure we still see ourselves.
        active_sorted = sorted(active_sorted + [str(worker_id)])

    position = active_sorted.index(str(worker_id))
    assigned_shard = _shard_for_position(position, shard_count)

    logger.info(
        "Worker %s assigned shard %d/%d (%d workers on queue)",
        worker_id,
        assigned_shard,
        shard_count,
        len(active_sorted),
    )
    return assigned_shard


async def trigger_rebalance(redis: Redis, queue_id: uuid.UUID) -> None:
    """Clears the active-workers set for a queue. Every worker's next
    registration (at most WORKER_KEY_TTL/heartbeat cadence away) starts from
    a clean slate, so shard assignments reshuffle across whoever's still
    around.
    """
    await redis.delete(workers_key(queue_id))


async def get_shard_distribution(
    queue_id: uuid.UUID, shard_count: int, db: AsyncSession, redis: Redis
) -> dict:
    now = time.time()
    active_sorted = await _active_sorted_workers(redis, queue_id, now)
    shard_map = compute_shard_map(active_sorted, shard_count)

    rows = (
        (
            await db.execute(
                SHARD_STATS_QUERY, {"queue_id": queue_id, "shard_count": shard_count}
            )
        )
        .mappings()
        .all()
    )
    stats_by_shard = {row["shard_id"]: row for row in rows}

    shards = []
    unassigned_jobs = 0
    for shard_id in range(shard_count):
        workers = shard_map.get(shard_id, [])
        row = stats_by_shard.get(shard_id)
        pending = row["pending"] if row else 0
        running = row["running"] if row else 0
        if not workers and pending > 0:
            unassigned_jobs += pending
        shards.append(
            {
                "shard_id": shard_id,
                "workers": workers,
                "pending_jobs": pending,
                "running_jobs": running,
            }
        )

    total_active_workers = len(active_sorted)
    if any(len(s["workers"]) == 0 and s["pending_jobs"] > 0 for s in shards):
        recommendation = "add_workers"
    elif total_active_workers > 0 and shard_count > total_active_workers * 2:
        recommendation = "reduce_shards"
    else:
        recommendation = "optimal"

    return {
        "shard_count": shard_count,
        "shards": shards,
        "unassigned_jobs": unassigned_jobs,
        "recommendation": recommendation,
    }
