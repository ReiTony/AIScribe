from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.config import get_settings
from db.connection import get_db
from models import User
from schemas.auth import Token, UserCreate, UserRead
from services import auth as auth_service

router = APIRouter(prefix=f"{get_settings().api_prefix}/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    user = auth_service.create_user(db, user_in)
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token)
def login(token: Token = Depends(auth_service.login_for_access_token)) -> Token:
    return token


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(auth_service.get_current_active_user)) -> UserRead:
    return UserRead.model_validate(current_user)
