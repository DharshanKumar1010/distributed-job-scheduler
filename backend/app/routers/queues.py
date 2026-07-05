import uuid

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Permission
from app.dependencies import get_db, get_redis, require_permission
from app.models.queue import Queue
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.queue import (
    QueueCreate,
    QueueOut,
    QueueStats,
    QueueUpdate,
    RateLimitStatus,
)
from app.services import project_service, queue_service
from app.websocket.publisher import publish_event
from app.worker import shard as shard_engine
from app.worker.rate_limit import peek_token_bucket, queue_bucket_key

router = APIRouter(prefix="/projects", tags=["queues"])


async def _rate_limit_status(redis: Redis, queue: Queue) -> RateLimitStatus | None:
    if not queue.rate_limit_per_minute:
        return None
    capacity = queue.rate_limit_burst or queue.rate_limit_per_minute
    refill_rate = queue.rate_limit_per_minute / 60.0
    tokens_remaining = await peek_token_bucket(
        redis, queue_bucket_key(queue.id), capacity, refill_rate
    )
    return RateLimitStatus(
        limit_per_minute=queue.rate_limit_per_minute,
        burst_capacity=capacity,
        tokens_remaining=tokens_remaining,
        is_rate_limited=tokens_remaining < 1,
    )


async def _to_queue_out(
    redis: Redis, queue: Queue, pending: int, running: int, failed: int, throughput: int
) -> QueueOut:
    return QueueOut(
        id=queue.id,
        project_id=queue.project_id,
        name=queue.name,
        slug=queue.slug,
        description=queue.description,
        priority=queue.priority,
        concurrency_limit=queue.concurrency_limit,
        retry_policy_id=queue.retry_policy_id,
        is_paused=queue.is_paused,
        is_active=queue.is_active,
        shard_count=queue.shard_count,
        rate_limit_per_minute=queue.rate_limit_per_minute,
        rate_limit_burst=queue.rate_limit_burst,
        created_at=queue.created_at,
        updated_at=queue.updated_at,
        stats=QueueStats(
            pending_count=pending,
            running_count=running,
            failed_count=failed,
            throughput_per_min=throughput,
        ),
        rate_limit_status=await _rate_limit_status(redis, queue),
    )


@router.get("/{project_id}/queues", response_model=PaginatedResponse[QueueOut])
async def list_queues(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_permission(Permission.QUEUE_READ)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await project_service.get_project(db, current_user.org_id, project_id)
    rows, total = await queue_service.list_queues_with_stats(
        db, project_id, page, limit
    )
    return PaginatedResponse(
        data=[await _to_queue_out(redis, *row) for row in rows],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.post(
    "/{project_id}/queues",
    response_model=DataResponse[QueueOut],
    status_code=status.HTTP_201_CREATED,
)
async def create_queue(
    project_id: uuid.UUID,
    payload: QueueCreate,
    current_user: User = Depends(require_permission(Permission.QUEUE_CREATE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await project_service.get_project(db, current_user.org_id, project_id)
    queue = await queue_service.create_queue(db, project_id, payload.model_dump())
    stats = await queue_service.get_stats_for_queue(db, queue.id)
    return DataResponse(data=await _to_queue_out(redis, queue, *stats))


@router.get("/{project_id}/queues/{queue_id}", response_model=DataResponse[QueueOut])
async def get_queue(
    project_id: uuid.UUID,
    queue_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.QUEUE_READ)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await project_service.get_project(db, current_user.org_id, project_id)
    row = await queue_service.get_queue_with_stats(db, project_id, queue_id)
    return DataResponse(data=await _to_queue_out(redis, *row))


@router.patch("/{project_id}/queues/{queue_id}", response_model=DataResponse[QueueOut])
async def update_queue(
    project_id: uuid.UUID,
    queue_id: uuid.UUID,
    payload: QueueUpdate,
    current_user: User = Depends(require_permission(Permission.QUEUE_UPDATE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await project_service.get_project(db, current_user.org_id, project_id)
    old_row = await queue_service.get_queue_with_stats(db, project_id, queue_id)
    old_shard_count = old_row[0].shard_count

    queue = await queue_service.update_queue(
        db, project_id, queue_id, payload.model_dump(exclude_unset=True)
    )

    if queue.shard_count != old_shard_count:
        await shard_engine.trigger_rebalance(redis, queue.id)
        await publish_event(
            redis,
            current_user.org_id,
            "queue.rebalancing",
            {"queue_id": str(queue.id), "queue_name": queue.name},
        )

    stats = await queue_service.get_stats_for_queue(db, queue.id)
    return DataResponse(data=await _to_queue_out(redis, queue, *stats))


@router.delete("/{project_id}/queues/{queue_id}", response_model=DataResponse[QueueOut])
async def delete_queue(
    project_id: uuid.UUID,
    queue_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.QUEUE_DELETE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await project_service.get_project(db, current_user.org_id, project_id)
    queue = await queue_service.soft_delete_queue(db, project_id, queue_id)
    stats = await queue_service.get_stats_for_queue(db, queue.id)
    return DataResponse(data=await _to_queue_out(redis, queue, *stats))


@router.post(
    "/{project_id}/queues/{queue_id}/pause", response_model=DataResponse[QueueOut]
)
async def pause_queue(
    project_id: uuid.UUID,
    queue_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.QUEUE_PAUSE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await project_service.get_project(db, current_user.org_id, project_id)
    queue = await queue_service.pause_queue(db, project_id, queue_id)
    stats = await queue_service.get_stats_for_queue(db, queue.id)
    return DataResponse(data=await _to_queue_out(redis, queue, *stats))


@router.post(
    "/{project_id}/queues/{queue_id}/resume", response_model=DataResponse[QueueOut]
)
async def resume_queue(
    project_id: uuid.UUID,
    queue_id: uuid.UUID,
    current_user: User = Depends(require_permission(Permission.QUEUE_PAUSE)),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    await project_service.get_project(db, current_user.org_id, project_id)
    queue = await queue_service.resume_queue(db, project_id, queue_id)
    stats = await queue_service.get_stats_for_queue(db, queue.id)
    return DataResponse(data=await _to_queue_out(redis, queue, *stats))
