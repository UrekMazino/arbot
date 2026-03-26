from __future__ import annotations

import html
import json
from urllib import error, request

from ..config import settings


def build_password_reset_link(raw_token: str) -> str:
    base = str(settings.password_reset_link_base or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:3000/reset-password"
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}token={raw_token}"


def send_password_reset_email(recipient_email: str, reset_link: str) -> None:
    provider = str(settings.email_provider or "").strip().lower()
    if provider != "resend":
        raise RuntimeError(f"Unsupported email provider: {provider or 'none'}")
    if not str(settings.resend_api_key or "").strip():
        raise RuntimeError("RESEND_API_KEY is not configured")
    if not str(settings.email_from or "").strip():
        raise RuntimeError("EMAIL_FROM is not configured")

    escaped_link = html.escape(reset_link, quote=True)
    payload = {
        "from": settings.email_from,
        "to": [recipient_email],
        "subject": "Reset your OKXStatBot admin password",
        "html": (
            "<p>Hello,</p>"
            "<p>We received a request to reset your OKXStatBot admin password.</p>"
            f'<p><a href="{escaped_link}">Reset Password</a></p>'
            "<p>This link expires soon and can only be used once.</p>"
            "<p>If you did not request this, you can ignore this email.</p>"
        ),
        "text": (
            "We received a request to reset your OKXStatBot admin password.\n"
            f"Reset link: {reset_link}\n"
            "If you did not request this, you can ignore this email."
        ),
    }

    encoded = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{str(settings.resend_api_base).rstrip('/')}/emails",
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=12) as response:
            status = int(getattr(response, "status", 0) or 0)
            if status < 200 or status >= 300:
                raise RuntimeError(f"Resend API responded with status {status}")
    except error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = ""
        snippet = detail[:280] if detail else str(exc)
        raise RuntimeError(f"Resend API error {exc.code}: {snippet}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed sending password reset email: {exc}") from exc
