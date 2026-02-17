from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db_session, require_roles
from ..models import Role, User
from ..schemas import MessageOut, UserCreateIn, UserOut, UserRoleAssignIn, UserUpdateIn
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session),
):
    stmt = select(User).order_by(User.created_at.desc())
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=UserOut)
def create_user(
    body: UserCreateIn,
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session),
):
    exists = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        is_active=body.is_active,
        is_superuser=body.is_superuser,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdateIn,
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_superuser is not None:
        user.is_superuser = body.is_superuser
    if body.password:
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/roles", response_model=MessageOut)
def assign_role(
    user_id: str,
    body: UserRoleAssignIn,
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role = db.execute(select(Role).where(Role.name == body.role.lower())).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role not in user.roles:
        user.roles.append(role)
        db.commit()
    return MessageOut(message="Role assigned")


@router.delete("/{user_id}/roles/{role_name}", response_model=MessageOut)
def remove_role(
    user_id: str,
    role_name: str,
    _: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role = db.execute(select(Role).where(Role.name == role_name.lower())).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role in user.roles:
        user.roles.remove(role)
        db.commit()
    return MessageOut(message="Role removed")

