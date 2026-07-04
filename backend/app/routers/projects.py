import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import ensure_same_org, get_current_user, get_db
from app.models.user import User
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/orgs", tags=["projects"])


@router.get("/{org_id}/projects", response_model=PaginatedResponse[ProjectOut])
async def list_projects(
    org_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    projects, total = await project_service.list_projects(db, org_id, page, limit)
    return PaginatedResponse(
        data=[ProjectOut.model_validate(p) for p in projects],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.post(
    "/{org_id}/projects", response_model=DataResponse[ProjectOut], status_code=status.HTTP_201_CREATED
)
async def create_project(
    org_id: uuid.UUID,
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    project = await project_service.create_project(
        db, org_id, payload.name, payload.slug, payload.description
    )
    return DataResponse(data=ProjectOut.model_validate(project))


@router.get("/{org_id}/projects/{project_id}", response_model=DataResponse[ProjectOut])
async def get_project(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    project = await project_service.get_project(db, org_id, project_id)
    return DataResponse(data=ProjectOut.model_validate(project))


@router.patch("/{org_id}/projects/{project_id}", response_model=DataResponse[ProjectOut])
async def update_project(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    project = await project_service.update_project(
        db, org_id, project_id, payload.model_dump(exclude_unset=True)
    )
    return DataResponse(data=ProjectOut.model_validate(project))


@router.delete("/{org_id}/projects/{project_id}", response_model=DataResponse[ProjectOut])
async def delete_project(
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    project = await project_service.soft_delete_project(db, org_id, project_id)
    return DataResponse(data=ProjectOut.model_validate(project))
