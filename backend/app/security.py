"""Browser-owned sessions. Local demo preserves the pre-existing local history."""
import hashlib
import hmac
import os
import secrets
from contextvars import ContextVar
from app.config import settings

owner = ContextVar("owner", default="local-demo")


def allowed_origins():
    return [s.strip().rstrip("/") for s in settings.frontend_url.split(",") if s.strip()]


def identity(cookie):
    if settings.app_mode == "local":
        return "local-demo"
    if not cookie or "." not in cookie:
        return None
    value, signature = cookie.rsplit(".", 1)
    expected = hmac.new(settings.session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return value if hmac.compare_digest(signature, expected) else None


def new_identity():
    value = secrets.token_hex(24)
    signature = hmac.new(settings.session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()
    return value, f"{value}.{signature}"


def validate_deployment():
    if settings.app_mode not in {"local", "hosted"}:
        raise RuntimeError("APP_MODE must be local or hosted")
    if settings.app_mode == "hosted" and len(settings.session_secret) < 32:
        raise RuntimeError("Hosted mode requires a stable SESSION_SECRET of at least 32 characters")
