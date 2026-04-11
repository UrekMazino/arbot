from __future__ import annotations

from collections.abc import Generator
from functools import wraps
from urllib.parse import urlsplit

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select

from .config import settings
from .database import get_db
from .models import Role, User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login", auto_error=False)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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

    # Ensure roles are loaded while session is active
    # This fixes the 403 error for traders by making role permissions available
    _ = user.roles

    return user


def _normalize_origin(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def validate_browser_request_origin(request: Request) -> None:
    if request.method.upper() in SAFE_METHODS:
        return

    sec_fetch_site = str(request.headers.get("sec-fetch-site") or "").strip().lower()
    if sec_fetch_site and sec_fetch_site not in {"same-origin", "same-site", "none"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request blocked")

    allowed_origins = {
        origin
        for origin in (_normalize_origin(item) for item in settings.cors_origin_list())
        if origin
    }
    if not allowed_origins:
        return

    origin = _normalize_origin(request.headers.get("origin"))
    if origin:
        if origin not in allowed_origins:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request blocked")
        return

    referer_origin = _normalize_origin(request.headers.get("referer"))
    if referer_origin and referer_origin not in allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request blocked")


def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db_session),
) -> User:
    if not token:
        token = request.cookies.get("okxstatbot_access_token")
        if token:
            validate_browser_request_origin(request)
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
    # Process role permissions
    for role in user.roles:
        role_perms = role.permissions
        for permission_id in (role_perms or []):
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
