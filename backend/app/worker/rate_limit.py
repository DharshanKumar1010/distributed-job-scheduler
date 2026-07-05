import time

from redis.asyncio import Redis

# Atomic refill + consume: read current tokens, top up for elapsed time (capped
# at capacity), then consume `requested` tokens if enough are available.
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= requested then
  tokens = tokens - requested
  redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
  redis.call('EXPIRE', key, 3600)
  return {1, tokens}
else
  redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
  redis.call('EXPIRE', key, 3600)
  return {0, tokens}
end
"""

_script_cache: dict[int, object] = {}


def _get_script(redis_client: Redis):
    cache_key = id(redis_client)
    script = _script_cache.get(cache_key)
    if script is None:
        script = redis_client.register_script(TOKEN_BUCKET_LUA)
        _script_cache[cache_key] = script
    return script


def queue_bucket_key(queue_id: object) -> str:
    return f"ratelimit:queue:{queue_id}"


async def check_token_bucket(
    redis_client: Redis,
    key: str,
    capacity: float,
    refill_rate: float,
    requested: float = 1,
    now: float | None = None,
) -> tuple[bool, float]:
    """Returns (allowed, tokens_remaining)."""
    script = _get_script(redis_client)
    now = now if now is not None else time.time()
    allowed, tokens = await script(
        keys=[key], args=[str(capacity), str(refill_rate), str(now), str(requested)]
    )
    return bool(allowed), float(tokens)


async def peek_token_bucket(
    redis_client: Redis, key: str, capacity: float, refill_rate: float
) -> float:
    """Read-only estimate of current tokens, without consuming any. Used to
    display the gauge on GET endpoints - doesn't need Lua-level atomicity
    since it never mutates state.
    """
    tokens_raw, last_refill_raw = await redis_client.hmget(key, "tokens", "last_refill")
    now = time.time()
    tokens = float(tokens_raw) if tokens_raw is not None else capacity
    last_refill = float(last_refill_raw) if last_refill_raw is not None else now
    elapsed = max(0.0, now - last_refill)
    return min(capacity, tokens + elapsed * refill_rate)
