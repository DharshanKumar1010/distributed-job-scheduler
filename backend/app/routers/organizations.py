import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import ensure_same_org, get_current_user, get_db, require_role
from app.models.user import User, UserRole
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.organization import OrganizationOut, OrganizationUpdate
from app.schemas.user import UserInviteRequest, UserInviteResponse, UserOut, UserRoleUpdateRequest
from app.services import organization_service

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("/{org_id}", response_model=DataResponse[OrganizationOut])
async def get_org(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    org = await organization_service.get_organization(db, org_id)
    return DataResponse(data=OrganizationOut.model_validate(org))


@router.patch("/{org_id}", response_model=DataResponse[OrganizationOut])
async def update_org(
    org_id: uuid.UUID,
    payload: OrganizationUpdate,
    current_user: User = Depends(require_role(UserRole.owner, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    org = await organization_service.update_organization(
        db, org_id, payload.model_dump(exclude_unset=True)
    )
    return DataResponse(data=OrganizationOut.model_validate(org))


@router.get("/{org_id}/users", response_model=PaginatedResponse[UserOut])
async def list_org_users(
    org_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    users, total = await organization_service.list_org_users(db, org_id, page, limit)
    return PaginatedResponse(
        data=[UserOut.model_validate(u) for u in users],
        meta=PaginationMeta(total=total, page=page, limit=limit),
    )


@router.post(
    "/{org_id}/users",
    response_model=DataResponse[UserInviteResponse],
    status_code=status.HTTP_201_CREATED,
)
async def invite_user(
    org_id: uuid.UUID,
    payload: UserInviteRequest,
    current_user: User = Depends(require_role(UserRole.owner, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    user, temp_password = await organization_service.invite_user(
        db, org_id, payload.email, payload.full_name, payload.role
    )
    return DataResponse(
        data=UserInviteResponse(user=UserOut.model_validate(user), temporary_password=temp_password)
    )


@router.patch("/{org_id}/users/{user_id}", response_model=DataResponse[UserOut])
async def update_user_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    current_user: User = Depends(require_role(UserRole.owner, UserRole.admin)),
    db: AsyncSession = Depends(get_db),
):
    ensure_same_org(current_user, org_id)
    user = await organization_service.update_user_role(db, org_id, user_id, payload.role)
    return DataResponse(data=UserOut.model_validate(user))
