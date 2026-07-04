import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.retry_policy import RetryPolicyCreate, RetryPolicyOut, RetryPolicyUpdate
from app.services import retry_policy_service

router = APIRouter(prefix="/retry-policies", tags=["retry-policies"])


@router.get("", response_model=PaginatedResponse[RetryPolicyOut])
async def list_retry_policies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policies, total = await retry_policy_service.list_retry_policies(db, page, limit)
    return PaginatedResponse(
        data=[RetryPolicyOut.model_validate(p) for p in policies],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.post("", response_model=DataResponse[RetryPolicyOut], status_code=status.HTTP_201_CREATED)
async def create_retry_policy(
    payload: RetryPolicyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await retry_policy_service.create_retry_policy(db, payload.model_dump())
    return DataResponse(data=RetryPolicyOut.model_validate(policy))


@router.get("/{policy_id}", response_model=DataResponse[RetryPolicyOut])
async def get_retry_policy(
    policy_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await retry_policy_service.get_retry_policy(db, policy_id)
    return DataResponse(data=RetryPolicyOut.model_validate(policy))


@router.patch("/{policy_id}", response_model=DataResponse[RetryPolicyOut])
async def update_retry_policy(
    policy_id: uuid.UUID,
    payload: RetryPolicyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await retry_policy_service.update_retry_policy(
        db, policy_id, payload.model_dump(exclude_unset=True)
    )
    return DataResponse(data=RetryPolicyOut.model_validate(policy))
