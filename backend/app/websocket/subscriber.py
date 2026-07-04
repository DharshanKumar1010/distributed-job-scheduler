import asyncio
import json
import logging

from redis.asyncio import Redis

from app.websocket.hub import ConnectionManager

logger = logging.getLogger("websocket.subscriber")

EVENTS_PATTERN = "scheduler:events:*"
RECONNECT_DELAY_SECONDS = 2


async def run_redis_subscriber(hub: ConnectionManager, redis: Redis) -> None:
    """Bridges Redis pub/sub to in-process WebSocket connections.

    Every API/worker/scheduler process publishes to Redis rather than holding
    WebSocket connections itself; this is the one function, running inside
    the API process's lifespan, that actually fans those messages out to
    connected browsers. Reconnects with a short fixed delay if Redis drops.
    """
    while True:
        try:
            pubsub = redis.pubsub()
            await pubsub.psubscribe(EVENTS_PATTERN)
            logger.info("Subscribed to %s", EVENTS_PATTERN)

            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                org_id = channel.rsplit(":", 1)[-1]

                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()

                try:
                    payload = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Dropping malformed message on channel %s", channel)
                    continue

                await hub.broadcast_to_org(org_id, payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Redis subscriber error, reconnecting in %ss", RECONNECT_DELAY_SECONDS
            )
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
