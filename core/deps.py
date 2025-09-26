"""Reusable FastAPI dependency functions."""
from typing import Callable

from fastapi import Depends, HTTPException, status

from models import User
from services.auth import get_current_active_user
from core.roles import UserRole


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Return a dependency that ensures the current user has one of the given roles."""

    def _checker(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role not in {r.value for r in roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _checker