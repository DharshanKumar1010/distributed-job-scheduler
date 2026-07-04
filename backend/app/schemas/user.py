import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.user import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: UserRole
    is_active: bool


class UserInviteRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: UserRole = UserRole.member


class UserInviteResponse(BaseModel):
    user: UserOut
    temporary_password: str


class UserRoleUpdateRequest(BaseModel):
    role: UserRole
