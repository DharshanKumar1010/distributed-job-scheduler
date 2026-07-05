import uuid

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Permission
from app.dependencies import get_db, get_redis, require_permission
from app.models.user import User
from app.models.worker import Worker
from app.schemas.common import DataResponse
from app.schemas.shard import RebalanceResult, ShardDistributionOut, ShardOut, ShardWorkerOut
from app.services import queue_service
from app.worker import shard as shard_engine
from app.websocket.publisher import publish_event

router = APIRouter(tags=["shards"])


@router.get("/queues/{queue_id}/shards", response_model=DataResponse[ShardDistributionOut])
async def get_shards(
    queue_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.QUEUE_READ)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    queue = await queue_service.get_queue_for_org(db, current_user.org_id, queue_id)
    distribution = await shard_engine.get_shard_distribution(queue_id, queue.shard_count, db, redis)

    worker_ids = {uuid.UUID(wid) for s in distribution["shards"] for wid in s["workers"]}
    workers_by_id: dict[uuid.UUID, Worker] = {}
    if worker_ids:
        rows = (await db.execute(select(Worker).where(Worker.id.in_(worker_ids)))).scalars().all()
        workers_by_id = {w.id: w for w in rows}

    shards_out = [
        ShardOut(
            shard_id=s["shard_id"],
            workers=[
                ShardWorkerOut(
                    worker_id=w.id, hostname=w.hostname, current_jobs=w.current_jobs
                )
                for wid in s["workers"]
                if (w := workers_by_id.get(uuid.UUID(wid))) is not None
            ],
            pending_jobs=s["pending_jobs"],
            running_jobs=s["running_jobs"],
        )
        for s in distribution["shards"]
    ]

    return DataResponse(
        data=ShardDistributionOut(
            shard_count=distribution["shard_count"],
            shards=shards_out,
            unassigned_jobs=distribution["unassigned_jobs"],
            recommendation=distribution["recommendation"],
        )
    )


@router.post("/queues/{queue_id}/shards/rebalance", response_model=DataResponse[RebalanceResult])
async def rebalance_shards(
    queue_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.QUEUE_CONFIGURE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    queue = await queue_service.get_queue_for_org(db, current_user.org_id, queue_id)
    await shard_engine.trigger_rebalance(redis, queue_id)
    await publish_event(
        redis,
        current_user.org_id,
        "queue.rebalancing",
        {"queue_id": str(queue_id), "queue_name": queue.name},
    )
    return DataResponse(data=RebalanceResult(status="rebalancing", expected_completion_seconds=15))
