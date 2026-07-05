import asyncio
import logging

from redis.asyncio import Redis

from app.config import settings
from app.scheduler.dispatcher import run_dispatcher_with_leader_election
from app.scheduler.reaper import run_reaper_loop


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    await redis_client.ping()

    logging.getLogger("scheduler").info("Dispatcher + reaper started")

    await asyncio.gather(
        run_dispatcher_with_leader_election(redis_client), run_reaper_loop(redis_client)
    )


if __name__ == "__main__":
    asyncio.run(main())
