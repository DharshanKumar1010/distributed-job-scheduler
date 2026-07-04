import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.worker import WorkerDetailOut, WorkerHeartbeatOut, WorkerOut
from app.services import worker_service

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("", response_model=PaginatedResponse[WorkerOut])
async def list_workers(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workers, total = await worker_service.list_workers(db, current_user.org_id, page, limit)
    return PaginatedResponse(
        data=[WorkerOut.model_validate(w) for w in workers],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.get("/{worker_id}", response_model=DataResponse[WorkerDetailOut])
async def get_worker(
    worker_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    worker, heartbeats = await worker_service.get_worker_detail(db, current_user.org_id, worker_id)
    detail = WorkerDetailOut(
        **WorkerOut.model_validate(worker).model_dump(),
        heartbeats=[WorkerHeartbeatOut.model_validate(h) for h in heartbeats],
    )
    return DataResponse(data=detail)


@router.delete("/{worker_id}", response_model=DataResponse[WorkerOut])
async def force_offline(
    worker_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    worker = await worker_service.force_offline(db, current_user.org_id, worker_id)
    return DataResponse(data=WorkerOut.model_validate(worker))
