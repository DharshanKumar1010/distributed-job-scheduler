import asyncio
import os
import uuid

from app.worker.worker import run


def main() -> None:
    queue_id_str = os.environ.get("QUEUE_ID")
    if not queue_id_str:
        raise RuntimeError("QUEUE_ID environment variable is required")

    queue_id = uuid.UUID(queue_id_str)
    asyncio.run(run(queue_id))


if __name__ == "__main__":
    main()
