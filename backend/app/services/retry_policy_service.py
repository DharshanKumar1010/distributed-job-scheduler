import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.retry_policy import RetryPolicy


async def list_retry_policies(
    db: AsyncSession, page: int, limit: int
) -> tuple[list[RetryPolicy], int]:
    total = await db.scalar(select(func.count()).select_from(RetryPolicy))
    result = await db.execute(
        select(RetryPolicy)
        .order_by(RetryPolicy.created_at.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def create_retry_policy(db: AsyncSession, data: dict) -> RetryPolicy:
    policy = RetryPolicy(**data)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def get_retry_policy(db: AsyncSession, policy_id: uuid.UUID) -> RetryPolicy:
    policy = await db.get(RetryPolicy, policy_id)
    if policy is None:
        raise APIError(404, "RETRY_POLICY_NOT_FOUND", "Retry policy not found")
    return policy


async def update_retry_policy(
    db: AsyncSession, policy_id: uuid.UUID, data: dict
) -> RetryPolicy:
    policy = await get_retry_policy(db, policy_id)
    for field, value in data.items():
        setattr(policy, field, value)
    await db.commit()
    await db.refresh(policy)
    return policy
