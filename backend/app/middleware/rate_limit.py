import re
import time
import uuid
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from jose import JWTError, jwt
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import settings
from app.dependencies import ALGORITHM

WINDOW_MS = 60_000

ENDPOINT_LIMITS: dict[str, int] = {
    "job_write": 100,
    "job_read": 500,
    "queue_write": 60,
    "auth": 20,
    "default": 200,
}

SKIP_PREFIXES = ("/ws", "/health", "/docs", "/openapi.json", "/redoc")

_JOB_WRITE_RE = re.compile(r"^/queues/[^/]+/jobs/?$")
_JOB_READ_LIST_RE = re.compile(r"^/queues/[^/]+/jobs/?$")
_JOB_DETAIL_RE = re.compile(r"^/jobs(/|$)")
_QUEUE_WRITE_RE = re.compile(r"^/projects/[^/]+/queues")

# Atomic sliding-window check: prune expired entries, count, and (if under
# the limit) record this request — all in one round trip so concurrent
# requests can never both slip through past the limit.
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local req_id = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local reset_at = tonumber(oldest[2]) + window
  return {0, count, reset_at}
end
redis.call('ZADD', key, now, req_id)
redis.call('EXPIRE', key, 60)
return {1, count + 1, now + window}
"""

_script_cache: dict[int, object] = {}


def _get_script(redis_client: Redis):
    cache_key = id(redis_client)
    script = _script_cache.get(cache_key)
    if script is None:
        script = redis_client.register_script(SLIDING_WINDOW_LUA)
        _script_cache[cache_key] = script
    return script


@dataclass
class RateLimitResult:
    allowed: bool
    count: int
    reset_at_ms: float


async def check_sliding_window(
    redis_client: Redis,
    key: str,
    limit: int,
    window_ms: int = WINDOW_MS,
    now_ms: float | None = None,
) -> RateLimitResult:
    script = _get_script(redis_client)
    now = now_ms if now_ms is not None else time.time() * 1000
    req_id = str(uuid.uuid4())
    allowed, count, reset_at = await script(keys=[key], args=[str(now), str(window_ms), str(limit), req_id])
    return RateLimitResult(allowed=bool(allowed), count=int(count), reset_at_ms=float(reset_at))


def build_429_headers(limit: int, result: RateLimitResult) -> dict[str, str]:
    now_ms = time.time() * 1000
    retry_after = max(1, int((result.reset_at_ms - now_ms) / 1000))
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(int(result.reset_at_ms / 1000)),
        "Retry-After": str(retry_after),
    }


def classify_endpoint(method: str, path: str) -> str:
    if path.startswith("/auth/"):
        return "auth"
    if method == "POST" and (_JOB_WRITE_RE.match(path) or path == "/workflows"):
        return "job_write"
    if method == "GET" and (_JOB_READ_LIST_RE.match(path) or _JOB_DETAIL_RE.match(path)):
        return "job_read"
    if method in ("POST", "PATCH", "DELETE") and _QUEUE_WRITE_RE.match(path):
        return "queue_write"
    return "default"


def _resolve_identity(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except JWTError:
            pass
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or any(
            path == prefix or path.startswith(prefix + "/") for prefix in SKIP_PREFIXES
        ):
            return await call_next(request)

        redis_client: Redis | None = getattr(request.app.state, "redis_client", None)
        if redis_client is None:
            return await call_next(request)

        group = classify_endpoint(request.method, path)
        limit = ENDPOINT_LIMITS[group]
        identity = _resolve_identity(request)
        key = f"ratelimit:{identity}:{group}"

        result = await check_sliding_window(redis_client, key, limit)

        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": f"Rate limit exceeded for '{group}' ({limit}/min)",
                        "details": {"group": group, "limit": limit},
                    }
                },
                headers=build_429_headers(limit, result),
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - result.count))
        response.headers["X-RateLimit-Reset"] = str(int(result.reset_at_ms / 1000))
        return response
