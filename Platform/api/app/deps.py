from __future__ import annotations

from collections.abc import Generator
from functools import wraps

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False)


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def _load_user_from_token(token: str | None, db: Session) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db_session),
) -> User:
    return _load_user_from_token(token, db)


def get_event_ingest_principal(
    token: str | None = Depends(oauth2_scheme),
    x_bot_ingest_key: str | None = Header(default=None, alias="X-Bot-Ingest-Key"),
    db: Session = Depends(get_db_session),
) -> dict[str, str]:
    # 1) Normal authenticated user token
    if token:
        user = _load_user_from_token(token, db)
        return {"kind": "user", "id": user.id}

    # 2) Bot ingest key
    configured_key = str(settings.event_ingest_key or "").strip()
    if configured_key:
        if not x_bot_ingest_key or x_bot_ingest_key != configured_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bot ingest key")
        return {"kind": "bot_key", "id": "bot_ingest_key"}

    # 3) Development fallback for local event flow bootstrap
    if settings.event_allow_unauthenticated:
        return {"kind": "unauthenticated_dev", "id": "dev_local"}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Event ingest authentication required")


def require_roles(*roles: str):
    wanted = {r.lower() for r in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        user_roles = {role.name.lower() for role in user.roles}
        if not user_roles.intersection(wanted):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


def get_user_permission_ids(user: User) -> set[str]:
    permissions: set[str] = set()
    for permission_id in user.permissions or []:
        normalized = str(permission_id or "").strip().lower()
        if normalized:
            permissions.add(normalized)
    for role in user.roles:
        for permission_id in role.permissions or []:
            normalized = str(permission_id or "").strip().lower()
            if normalized:
                permissions.add(normalized)
    return permissions


def require_permissions(*permissions: str, match: str = "any"):
    wanted = {permission.lower() for permission in permissions if permission}
    if match not in {"any", "all"}:
        raise ValueError("match must be 'any' or 'all'")

    def dependency(user: User = Depends(get_current_user)) -> User:
        user_permissions = get_user_permission_ids(user)
        if match == "all":
            allowed = wanted.issubset(user_permissions)
        else:
            allowed = bool(user_permissions.intersection(wanted))
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency
