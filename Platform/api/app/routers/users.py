from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db_session, require_permissions
from ..models import Role, User
from ..schemas import (
    MessageOut,
    RoleOut,
    RoleCreateIn,
    RoleUpdateIn,
    UserCreateIn,
    UserOut,
    UserPermissionsUpdateIn,
    UserRoleAssignIn,
    UserUpdateIn,
)
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])


def normalize_role_name(raw: str) -> str:
    return str(raw or "").strip().lower()


def validate_role_name(raw: str) -> str:
    role_name = normalize_role_name(raw)
    if not role_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name is required")
    if role_name == "super_admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the built-in 'admin' role instead of legacy 'super_admin'.",
        )
    return role_name


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    _: User = Depends(require_permissions("manage_users", "manage_roles")),
    db: Session = Depends(get_db_session),
):
    stmt = select(Role).order_by(Role.name.asc())
    return list(db.execute(stmt).scalars().all())


@router.get("/roles/{role_id}", response_model=RoleOut)
def get_role(
    role_id: str,
    _: User = Depends(require_permissions("manage_users", "manage_roles")),
    db: Session = Depends(get_db_session),
):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


@router.post("/roles", response_model=RoleOut)
def create_role(
    body: RoleCreateIn,
    _: User = Depends(require_permissions("manage_roles")),
    db: Session = Depends(get_db_session),
):
    role_name = validate_role_name(body.name)
    exists = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")

    role = Role(name=role_name, description=body.description, permissions=body.permissions)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: str,
    body: RoleUpdateIn,
    _: User = Depends(require_permissions("manage_roles")),
    db: Session = Depends(get_db_session),
):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if body.name is not None:
        role_name = validate_role_name(body.name)
        exists = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
        if exists and exists.id != role_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists")
        role.name = role_name

    if body.description is not None:
        role.description = body.description

    if body.permissions is not None:
        role.permissions = body.permissions

    db.commit()
    db.refresh(role)
    return role


@router.delete("/roles/{role_id}", response_model=MessageOut)
def delete_role(
    role_id: str,
    _: User = Depends(require_permissions("manage_roles")),
    db: Session = Depends(get_db_session),
):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Prevent deletion of built-in roles
    if role.name in ["admin", "trader", "viewer"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete built-in roles")

    db.delete(role)
    db.commit()
    return MessageOut(message="Role deleted")


@router.get("", response_model=list[UserOut])
def list_users(
    _: User = Depends(require_permissions("manage_users")),
    db: Session = Depends(get_db_session),
):
    stmt = select(User).order_by(User.created_at.desc())
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=UserOut)
def create_user(
    body: UserCreateIn,
    _: User = Depends(require_permissions("manage_users")),
    db: Session = Depends(get_db_session),
):
    exists = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        is_active=body.is_active,
        permissions=[],
    )
    viewer_role = db.execute(select(Role).where(Role.name == "viewer")).scalar_one_or_none()
    if viewer_role:
        user.roles.append(viewer_role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdateIn,
    _: User = Depends(require_permissions("manage_users")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password:
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/permissions", response_model=UserOut)
def update_user_permissions(
    user_id: str,
    body: UserPermissionsUpdateIn,
    _: User = Depends(require_permissions("manage_users")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.permissions = body.permissions
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=MessageOut)
def delete_user(
    user_id: str,
    _: User = Depends(require_permissions("manage_users")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Prevent deleting the last admin user
    if user.email == "admin@local":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the default admin user")

    db.delete(user)
    db.commit()
    return MessageOut(message="User deleted")


@router.post("/{user_id}/roles", response_model=MessageOut)
def assign_role(
    user_id: str,
    body: UserRoleAssignIn,
    _: User = Depends(require_permissions("manage_users", "manage_roles")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role = db.execute(select(Role).where(Role.name == normalize_role_name(body.role))).scalar_one_or_none()
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
    _: User = Depends(require_permissions("manage_users", "manage_roles")),
    db: Session = Depends(get_db_session),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role = db.execute(select(Role).where(Role.name == normalize_role_name(role_name))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Remove from user's roles by directly deleting the association
    from ..models import UserRole
    association = db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id
        )
    ).scalar_one_or_none()

    if association:
        db.delete(association)
        db.commit()

    return MessageOut(message="Role removed")
