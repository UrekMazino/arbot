from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db_session
from ..models import RefreshToken, User
from ..schemas import LoginIn, LogoutIn, MessageOut, RefreshIn, TokenPairOut, UserOut
from ..security import (
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPairOut)
def login(
    body: LoginIn,
    request: Request,
    db: Session = Depends(get_db_session),
):
    stmt = select(User).where(User.email == body.email)
    user = db.execute(stmt).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")

    access_token = create_access_token(user.id)
    refresh_token, refresh_hash, expires = create_refresh_token()
    token_row = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=expires,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(token_row)
    db.commit()

    return TokenPairOut(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPairOut)
def refresh(
    body: RefreshIn,
    request: Request,
    db: Session = Depends(get_db_session),
):
    token_hash = hash_refresh_token(body.refresh_token)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    token_row = db.execute(stmt).scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if token_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")
    if token_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.get(User, token_row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not active")

    token_row.revoked_at = datetime.now(timezone.utc)
    access_token = create_access_token(user.id)
    refresh_token, refresh_hash, expires = create_refresh_token()
    new_row = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=expires,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(new_row)
    db.commit()

    return TokenPairOut(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", response_model=MessageOut)
def logout(
    body: LogoutIn,
    db: Session = Depends(get_db_session),
):
    token_hash = hash_refresh_token(body.refresh_token)
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    token_row = db.execute(stmt).scalar_one_or_none()
    if token_row and token_row.revoked_at is None:
        token_row.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return MessageOut(message="Logged out")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user

