from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator
from core.roles import UserRole


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str = Field(..., description="Subject (user id as string).")
    email: EmailStr | None = Field(None, description="User email (duplicated for convenience).")
    exp: int


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: str = UserRole.client.value
    is_active: bool = True

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in UserRole.list():
            raise ValueError("Invalid role")
        return v


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserInDB(UserRead):
    hashed_password: str
