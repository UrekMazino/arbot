from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_current_user, get_db_session
from ..models import PasswordResetToken, RefreshToken, User
from ..schemas import (
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    LogoutIn,
    MessageOut,
    RefreshIn,
    ResetPasswordIn,
    TokenPairOut,
    UserOut,
)
from ..security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    verify_password,
)
from ..services.email_delivery import build_password_reset_link, send_password_reset_email

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


@router.post("/forgot-password", response_model=ForgotPasswordOut)
def forgot_password(
    body: ForgotPasswordIn,
    request: Request,
    db: Session = Depends(get_db_session),
):
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    generic_message = "If the account exists, a password reset link has been sent."
    if not user or not user.is_active:
        return ForgotPasswordOut(message=generic_message)

    now = datetime.now(timezone.utc)
    existing_tokens = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
    ).scalars().all()
    for token in existing_tokens:
        token.used_at = now

    raw_token, token_hash, expires = create_password_reset_token()
    token_row = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(token_row)

    reset_link = build_password_reset_link(raw_token)
    try:
        send_password_reset_email(user.email, reset_link)
    except Exception as exc:
        token_row.used_at = datetime.now(timezone.utc)
        db.commit()
        if settings.app_env.lower() != "production" and settings.password_reset_return_token_in_response:
            return ForgotPasswordOut(
                message=(
                    "Email delivery is not configured. Using development fallback token flow. "
                    f"Reason: {exc}. Configure RESEND_API_KEY and EMAIL_FROM for real email delivery."
                ),
                reset_token=raw_token,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to send reset email right now.",
        )

    db.commit()
    if settings.app_env.lower() != "production" and settings.password_reset_return_token_in_response:
        return ForgotPasswordOut(message=generic_message, reset_token=raw_token)
    return ForgotPasswordOut(message=generic_message)


@router.post("/reset-password", response_model=MessageOut)
def reset_password(
    body: ResetPasswordIn,
    db: Session = Depends(get_db_session),
):
    token_value = body.reset_token.strip()
    if not token_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token is required")

    now = datetime.now(timezone.utc)
    token_hash = hash_password_reset_token(token_value)
    token_row = db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)).scalar_one_or_none()
    if not token_row or token_row.used_at is not None or token_row.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    user = db.get(User, token_row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid reset token user")

    user.password_hash = hash_password(body.password)
    token_row.used_at = now
    refresh_rows = db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at.is_(None),
        )
    ).scalars().all()
    for row in refresh_rows:
        row.revoked_at = now
    db.commit()

    return MessageOut(message="Password reset successful. Please sign in with your new password.")


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
