import uuid
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy import text

SCHEDULER_LOCK_ID = 123456789

_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


@dataclass
class RedisLock:
    """Short-lived mutual-exclusion lock (e.g. cron dedup across dispatcher
    instances). `release` only deletes the key if it still holds this
    lock's own owner_id, so a slow/stale holder can never release a lock
    someone else has since acquired.
    """

    key: str
    ttl_seconds: int
    redis: Redis | None = None
    owner_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    async def acquire(self, redis: Redis | None = None) -> bool:
        client = redis or self.redis
        result = await client.set(f"lock:{self.key}", self.owner_id, nx=True, ex=self.ttl_seconds)
        return result is not None

    async def release(self, redis: Redis | None = None) -> bool:
        client = redis or self.redis
        result = await client.eval(_RELEASE_LUA, 1, f"lock:{self.key}", self.owner_id)
        return bool(result)

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, *exc_info) -> None:
        # Safe even if we never acquired it: release() only deletes the key
        # if its value still matches our owner_id.
        await self.release()


async def acquire_advisory_lock(db, lock_id: int) -> bool:
    result = await db.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id})
    return bool(result.scalar())


async def release_advisory_lock(db, lock_id: int) -> None:
    await db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
