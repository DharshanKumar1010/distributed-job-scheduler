import json
import uuid
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis


def _json_default(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def events_channel(org_id: uuid.UUID | str) -> str:
    return f"scheduler:events:{org_id}"


def metrics_channel(org_id: uuid.UUID | str) -> str:
    return f"scheduler:metrics:{org_id}"


async def publish_event(
    redis_client: Redis, org_id: uuid.UUID | str, event: str, data: dict
) -> None:
    envelope = {
        "event": event,
        "data": data,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.publish(events_channel(org_id), json.dumps(envelope, default=_json_default))


async def publish_metric(
    redis_client: Redis, org_id: uuid.UUID | str, metric_name: str, value: float
) -> None:
    payload = {
        "metric": metric_name,
        "value": value,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    await redis_client.publish(metrics_channel(org_id), json.dumps(payload, default=_json_default))
