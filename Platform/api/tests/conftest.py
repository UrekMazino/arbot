from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import settings
from app.database import Base
from app.deps import get_db_session
from app.models import Role, User
from app.permissions import BUILTIN_ROLE_PERMISSIONS
from app.routers import admin, auth, health, users
from app.security import hash_password

TEST_ALLOWED_ORIGIN = "http://127.0.0.1:3000"
TEST_PASSWORD = "Passw0rd!"


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db_session_factory(db_engine):
    return sessionmaker(bind=db_engine, autocommit=False, autoflush=False)


@pytest.fixture
def db_session(db_session_factory) -> Session:
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_app(db_session_factory):
    settings.app_env = "development"
    settings.cors_origins = TEST_ALLOWED_ORIGIN
    settings.access_token_secret = "test-access-secret"
    settings.refresh_token_secret = "test-refresh-secret"
    settings.access_token_minutes = 15
    settings.refresh_token_days = 14

    app = FastAPI(title="test-auth-app")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(users.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)

    def override_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db_session] = override_db
    return app


@pytest.fixture
def client(test_app):
    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def admin_identity(db_session: Session):
    admin_role = Role(
        name="admin",
        description="admin role",
        permissions=list(BUILTIN_ROLE_PERMISSIONS["admin"]),
    )
    viewer_role = Role(
        name="viewer",
        description="viewer role",
        permissions=list(BUILTIN_ROLE_PERMISSIONS["viewer"]),
    )
    admin_user = User(
        email="admin@example.com",
        password_hash=hash_password(TEST_PASSWORD),
        is_active=True,
        permissions=[],
    )
    admin_user.roles.extend([admin_role])
    db_session.add_all([admin_role, viewer_role, admin_user])
    db_session.commit()
    db_session.refresh(admin_user)
    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "password": TEST_PASSWORD,
    }
