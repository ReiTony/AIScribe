from pydantic import BaseModel, constr
from typing import Annotated, Optional
from datetime import datetime

# Request Schemas
class RegisterRequest(BaseModel):
    username: Annotated[str, constr(strip_whitespace=True, min_length=3, max_length=50)]
    password: Annotated[str, constr(min_length=8)]

class LoginRequest(BaseModel):
    username: str
    password: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

# Response Schemas
class MessageResponse(BaseModel):
    message: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until token expires

class UserResponse(BaseModel):
    username: str
    created_at: Optional[datetime] = None

class AuthenticatedUserResponse(BaseModel):
    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenValidationResponse(BaseModel):
    valid: bool
    username: Optional[str] = None
    expires_at: Optional[datetime] = None