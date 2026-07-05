from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import ALL_PERMISSIONS, get_permissions_for_role
from app.dependencies import create_access_token, get_current_user, get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PermissionsOut,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.common import DataResponse
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(user: User) -> str:
    return create_access_token(
        {"sub": str(user.id), "org_id": str(user.org_id), "role": user.role.value}
    )


@router.post(
    "/register",
    response_model=DataResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    _org, user = await auth_service.register_organization(
        db,
        org_name=payload.org_name,
        org_slug=payload.org_slug,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    token = _issue_token(user)
    return DataResponse(
        data=TokenResponse(access_token=token, user=UserOut.model_validate(user))
    )


@router.post("/login", response_model=DataResponse[TokenResponse])
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate_user(db, payload.email, payload.password)
    token = _issue_token(user)
    return DataResponse(
        data=TokenResponse(access_token=token, user=UserOut.model_validate(user))
    )


@router.get("/me", response_model=DataResponse[UserOut])
async def me(current_user: User = Depends(get_current_user)):
    return DataResponse(data=UserOut.model_validate(current_user))


@router.get("/permissions", response_model=DataResponse[PermissionsOut])
async def get_permissions(current_user: User = Depends(get_current_user)):
    role = current_user.role.value
    granted = get_permissions_for_role(role)
    cannot_do = sorted(ALL_PERMISSIONS - set(granted))
    return DataResponse(
        data=PermissionsOut(role=role, permissions=granted, cannot_do=cannot_do)
    )
