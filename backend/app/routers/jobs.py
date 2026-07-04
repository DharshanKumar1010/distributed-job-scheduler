import uuid

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.job import JobStatus, JobType
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.job import (
    BatchCancelRequest,
    BatchCancelResult,
    JobCreateRequest,
    JobDetailOut,
    JobExecutionOut,
    JobLogOut,
    JobOut,
)
from app.services import job_service

router = APIRouter(tags=["jobs"])


def _build_detail(job, executions, logs) -> JobDetailOut:
    return JobDetailOut(
        **JobOut.model_validate(job).model_dump(),
        payload=job.payload,
        result=job.result,
        error_traceback=job.error_traceback,
        cron_expression=job.cron_expression,
        executions=[JobExecutionOut.model_validate(e) for e in executions],
        logs=[JobLogOut.model_validate(log) for log in logs],
    )


@router.post("/queues/{queue_id}/jobs", response_model=DataResponse[JobOut])
async def create_job(
    queue_id: uuid.UUID,
    payload: JobCreateRequest,
    response: Response,
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job, created = await job_service.create_job(
        db, current_user.org_id, queue_id, payload, x_idempotency_key
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return DataResponse(data=JobOut.model_validate(job))


@router.get("/queues/{queue_id}/jobs", response_model=PaginatedResponse[JobOut])
async def list_jobs(
    queue_id: uuid.UUID,
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    job_type: JobType | None = Query(default=None),
    tag: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort: str = Query(default="created_at", pattern="^(created_at|priority)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    jobs, total = await job_service.list_jobs(
        db, current_user.org_id, queue_id, status_filter, job_type, tag, page, limit, sort
    )
    return PaginatedResponse(
        data=[JobOut.model_validate(j) for j in jobs],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.get("/jobs/{job_id}", response_model=DataResponse[JobDetailOut])
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job, executions, logs = await job_service.get_job_detail(db, current_user.org_id, job_id)
    return DataResponse(data=_build_detail(job, executions, logs))


@router.delete("/jobs/{job_id}", response_model=DataResponse[JobOut])
async def cancel_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await job_service.cancel_job(db, current_user.org_id, job_id)
    return DataResponse(data=JobOut.model_validate(job))


@router.post("/jobs/{job_id}/retry", response_model=DataResponse[JobOut])
async def retry_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await job_service.retry_job(db, current_user.org_id, job_id)
    return DataResponse(data=JobOut.model_validate(job))


@router.get("/jobs/{job_id}/logs", response_model=PaginatedResponse[JobLogOut])
async def get_job_logs(
    job_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logs, total = await job_service.get_job_logs(db, current_user.org_id, job_id, page, limit)
    return PaginatedResponse(
        data=[JobLogOut.model_validate(log) for log in logs],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.post("/jobs/batch-cancel", response_model=DataResponse[BatchCancelResult])
async def batch_cancel_jobs(
    payload: BatchCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await job_service.batch_cancel_jobs(db, current_user.org_id, payload.job_ids)
    return DataResponse(data=BatchCancelResult(**result))
