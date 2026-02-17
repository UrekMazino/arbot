from __future__ import annotations

from collections.abc import Generator
from functools import wraps

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db_session),
) -> User:
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_roles(*roles: str):
    wanted = {r.lower() for r in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        user_roles = {role.name.lower() for role in user.roles}
        if not user_roles.intersection(wanted):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency

