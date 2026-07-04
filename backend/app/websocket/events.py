import json
import uuid
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

CHANNEL = "job_events"


def _json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


async def publish_event(redis_client: Redis, event: str, data: dict) -> None:
    envelope = {
        "event": event,
        "data": data,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.publish(CHANNEL, json.dumps(envelope, default=_json_default))
