from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.organization import Organization
from app.models.user import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


async def register_organization(
    db: AsyncSession,
    *,
    org_name: str,
    org_slug: str,
    email: str,
    password: str,
    full_name: str | None,
) -> tuple[Organization, User]:
    existing_org = await db.scalar(
        select(Organization).where(Organization.slug == org_slug)
    )
    if existing_org is not None:
        raise APIError(
            409, "ORG_SLUG_TAKEN", "An organization with this slug already exists"
        )

    existing_user = await db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise APIError(409, "EMAIL_TAKEN", "A user with this email already exists")

    org = Organization(name=org_name, slug=org_slug)
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=UserRole.owner,
    )
    db.add(user)
    await db.commit()
    await db.refresh(org)
    await db.refresh(user)
    return org, user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not user.is_active
        or not verify_password(password, user.hashed_password)
    ):
        raise APIError(401, "INVALID_CREDENTIALS", "Invalid email or password")
    return user
