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


def bootstrap_identity() -> None:
    db = SessionLocal()
    try:
        for role_name in ("admin", "trader", "viewer"):
            role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
            if not role:
                db.add(Role(name=role_name, description=f"{role_name} role"))
        db.flush()

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
                        is_superuser=True,
                    )
                    admin_role = db.execute(select(Role).where(Role.name == "admin")).scalar_one()
                    admin.roles.append(admin_role)
                    db.add(admin)
        else:
            logger.info("BOOTSTRAP_ADMIN_EMAIL is empty; skipping bootstrap admin creation")
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    bootstrap_identity()
