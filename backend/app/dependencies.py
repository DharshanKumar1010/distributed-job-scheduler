import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import has_permission, roles_with_permission
from app.config import settings
from app.database import get_db  # noqa: F401 - re-exported for routers
from app.exceptions import APIError
from app.models.user import User, UserRole

ALGORITHM = "HS256"

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise APIError(401, "UNAUTHORIZED", "Invalid or expired token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise APIError(401, "UNAUTHORIZED", "Missing bearer token")

    payload = verify_token(credentials.credentials)
    user_id = payload.get("sub")
    if user_id is None:
        raise APIError(401, "UNAUTHORIZED", "Invalid token payload")

    user = await db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise APIError(401, "UNAUTHORIZED", "User not found or inactive")
    return user


def require_role(*roles: UserRole):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if roles and current_user.role not in roles:
            raise APIError(403, "FORBIDDEN", "Insufficient permissions for this action")
        return current_user

    return checker


def _insufficient_permissions_error(role: UserRole, missing: list[str]) -> APIError:
    roles_ok: set[str] = set()
    for permission in missing:
        roles_ok.update(roles_with_permission(permission))
    return APIError(
        403,
        "INSUFFICIENT_PERMISSIONS",
        f"Your role '{role.value}' does not have permission '{missing[0]}'"
        if len(missing) == 1
        else f"Your role '{role.value}' is missing permissions: {', '.join(missing)}",
        details={
            "required_permission": missing[0] if len(missing) == 1 else missing,
            "your_role": role.value,
            "roles_with_this_permission": sorted(roles_ok),
        },
    )


def require_permission(permission: str):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise _insufficient_permissions_error(current_user.role, [permission])
        return current_user

    return checker


def require_any_permission(*permissions: str):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if not any(has_permission(current_user.role, p) for p in permissions):
            raise _insufficient_permissions_error(current_user.role, list(permissions))
        return current_user

    return checker


def require_all_permissions(*permissions: str):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        missing = [p for p in permissions if not has_permission(current_user.role, p)]
        if missing:
            raise _insufficient_permissions_error(current_user.role, missing)
        return current_user

    return checker


def ensure_same_org(current_user: User, org_id: uuid.UUID) -> None:
    if current_user.org_id != org_id:
        raise APIError(404, "ORG_NOT_FOUND", "Organization not found")


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis_client
