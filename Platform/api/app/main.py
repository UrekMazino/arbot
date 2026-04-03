from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import settings
from .database import Base, SessionLocal, engine
from .models import Role, User
from .routers import admin, auth, events, health, reports, runs, users, ws
from .security import hash_password

app = FastAPI(title=settings.app_name)
logger = logging.getLogger(__name__)

allowed_origins = settings.cors_origin_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(runs.router, prefix=settings.api_prefix)
app.include_router(events.router, prefix=settings.api_prefix)
app.include_router(reports.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(ws.router)

BUILTIN_ROLES = {
    "admin": "admin role",
    "trader": "trader role",
    "viewer": "viewer role",
}


def bootstrap_identity() -> None:
    db = SessionLocal()
    try:
        for role_name, description in BUILTIN_ROLES.items():
            role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
            if not role:
                db.add(Role(name=role_name, description=description))
        db.flush()
        admin_role = db.execute(select(Role).where(Role.name == "admin")).scalar_one()

        legacy_super_admin_role = db.execute(select(Role).where(Role.name == "super_admin")).scalar_one_or_none()
        if legacy_super_admin_role:
            migrated_count = 0
            for user in list(legacy_super_admin_role.users):
                if admin_role not in user.roles:
                    user.roles.append(admin_role)
                if legacy_super_admin_role in user.roles:
                    user.roles.remove(legacy_super_admin_role)
                migrated_count += 1
            db.flush()
            db.delete(legacy_super_admin_role)
            logger.info(
                "Migrated legacy super_admin role to admin for %d user(s) and removed legacy role",
                migrated_count,
            )

        bootstrap_email = str(settings.bootstrap_admin_email or "").strip().lower()
        bootstrap_password = str(settings.bootstrap_admin_password or "")

        if bootstrap_email:
            admin = db.execute(select(User).where(User.email == bootstrap_email)).scalar_one_or_none()
            if not admin:
                if not bootstrap_password:
                    logger.warning(
                        "BOOTSTRAP_ADMIN_PASSWORD is empty; skipping bootstrap admin creation for %s",
                        bootstrap_email,
                    )
                else:
                    admin = User(
                        email=bootstrap_email,
                        password_hash=hash_password(bootstrap_password),
                        is_active=True,
                    )
                    admin.roles.append(admin_role)
                    db.add(admin)
            elif admin_role not in admin.roles:
                admin.roles.append(admin_role)
                logger.info("Assigned missing admin role to bootstrap user %s", bootstrap_email)
        else:
            logger.info("BOOTSTRAP_ADMIN_EMAIL is empty; skipping bootstrap admin creation")
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    bootstrap_identity()
