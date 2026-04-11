from __future__ import annotations

from sqlalchemy import select

from app.models import RefreshToken, User

TEST_ALLOWED_ORIGIN = "http://127.0.0.1:3000"


def _same_origin_headers() -> dict[str, str]:
    return {
        "Origin": TEST_ALLOWED_ORIGIN,
        "Referer": f"{TEST_ALLOWED_ORIGIN}/login",
        "Sec-Fetch-Site": "same-origin",
    }


def _cross_site_headers() -> dict[str, str]:
    return {
        "Origin": "https://evil.example",
        "Referer": "https://evil.example/pwn",
        "Sec-Fetch-Site": "cross-site",
    }


def _set_cookie_header(headers, cookie_name: str) -> str:
    for value in headers.get_list("set-cookie"):
        if value.startswith(f"{cookie_name}="):
            return value
    raise AssertionError(f"Missing Set-Cookie header for {cookie_name}")


def _login(client, admin_identity, remember_me: bool):
    return client.post(
        "/api/v2/auth/login",
        json={
            "email": admin_identity["email"],
            "password": admin_identity["password"],
            "remember_me": remember_me,
        },
        headers=_same_origin_headers(),
    )


def test_login_uses_session_cookies_without_token_body_when_not_remembered(client, db_session, admin_identity):
    response = _login(client, admin_identity, remember_me=False)

    assert response.status_code == 200
    assert response.json() == {"message": "Signed in"}
    body = response.json()
    assert "access_token" not in body
    assert "refresh_token" not in body

    access_cookie = _set_cookie_header(response.headers, "okxstatbot_access_token").lower()
    refresh_cookie = _set_cookie_header(response.headers, "okxstatbot_refresh_token").lower()
    assert "httponly" in access_cookie
    assert "httponly" in refresh_cookie
    assert "samesite=lax" in access_cookie
    assert "samesite=lax" in refresh_cookie
    assert "max-age=" not in access_cookie
    assert "max-age=" not in refresh_cookie

    token_row = db_session.execute(select(RefreshToken)).scalar_one()
    assert token_row.is_persistent is False


def test_login_with_remember_me_sets_persistent_refresh_cookie(client, db_session, admin_identity):
    response = _login(client, admin_identity, remember_me=True)

    assert response.status_code == 200
    assert response.json() == {"message": "Signed in"}

    access_cookie = _set_cookie_header(response.headers, "okxstatbot_access_token").lower()
    refresh_cookie = _set_cookie_header(response.headers, "okxstatbot_refresh_token").lower()
    assert "max-age=" not in access_cookie
    assert "max-age=" in refresh_cookie

    token_row = db_session.execute(select(RefreshToken)).scalar_one()
    assert token_row.is_persistent is True


def test_refresh_rotates_token_and_preserves_session_mode_without_exposing_tokens(client, db_session, admin_identity):
    login_response = _login(client, admin_identity, remember_me=False)
    assert login_response.status_code == 200

    original_row = db_session.execute(select(RefreshToken)).scalar_one()
    original_id = original_row.id

    response = client.post("/api/v2/auth/refresh", headers=_same_origin_headers())

    assert response.status_code == 200
    assert response.json() == {"message": "Session refreshed"}
    body = response.json()
    assert "access_token" not in body
    assert "refresh_token" not in body
    refresh_cookie = _set_cookie_header(response.headers, "okxstatbot_refresh_token").lower()
    assert "max-age=" not in refresh_cookie

    db_session.expire_all()
    rows = db_session.execute(select(RefreshToken).order_by(RefreshToken.created_at.asc())).scalars().all()
    assert len(rows) == 2
    old_row = next(row for row in rows if row.id == original_id)
    new_row = next(row for row in rows if row.id != original_id)
    assert old_row.revoked_at is not None
    assert new_row.revoked_at is None
    assert new_row.is_persistent is False


def test_cross_site_login_is_blocked(client, admin_identity):
    response = client.post(
        "/api/v2/auth/login",
        json={
            "email": admin_identity["email"],
            "password": admin_identity["password"],
            "remember_me": True,
        },
        headers=_cross_site_headers(),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-site request blocked"


def test_cross_site_cookie_authenticated_mutation_is_blocked(client, db_session, admin_identity):
    login_response = _login(client, admin_identity, remember_me=True)
    assert login_response.status_code == 200

    response = client.post(
        "/api/v2/users",
        json={"email": "new-user@example.com", "password": "Passw0rd!", "is_active": True},
        headers=_cross_site_headers(),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-site request blocked"
    assert db_session.execute(select(User).where(User.email == "new-user@example.com")).scalar_one_or_none() is None
