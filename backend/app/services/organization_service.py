import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.auth_service import hash_password


async def get_organization(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await db.get(Organization, org_id)
    if org is None:
        raise APIError(404, "ORG_NOT_FOUND", "Organization not found")
    return org


async def update_organization(
    db: AsyncSession, org_id: uuid.UUID, data: dict
) -> Organization:
    org = await get_organization(db, org_id)
    for field, value in data.items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return org


async def list_org_users(
    db: AsyncSession, org_id: uuid.UUID, page: int, limit: int
) -> tuple[list[User], int]:
    total = await db.scalar(
        select(func.count()).select_from(User).where(User.org_id == org_id)
    )
    result = await db.execute(
        select(User)
        .where(User.org_id == org_id)
        .order_by(User.created_at.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def invite_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    email: str,
    full_name: str | None,
    role: UserRole,
) -> tuple[User, str]:
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise APIError(409, "EMAIL_TAKEN", "A user with this email already exists")

    temp_password = secrets.token_urlsafe(12)
    user = User(
        org_id=org_id,
        email=email,
        full_name=full_name,
        role=role,
        hashed_password=hash_password(temp_password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, temp_password


async def update_user_role(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, role: UserRole
) -> User:
    user = await db.scalar(
        select(User).where(User.id == user_id, User.org_id == org_id)
    )
    if user is None:
        raise APIError(404, "USER_NOT_FOUND", "User not found")
    user.role = role
    await db.commit()
    await db.refresh(user)
    return user


async def remove_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    requesting_user_id: uuid.UUID,
) -> User:
    if user_id == requesting_user_id:
        raise APIError(400, "CANNOT_REMOVE_SELF", "You cannot remove your own account")
    user = await db.scalar(
        select(User).where(User.id == user_id, User.org_id == org_id)
    )
    if user is None:
        raise APIError(404, "USER_NOT_FOUND", "User not found")
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user
