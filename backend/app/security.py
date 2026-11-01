"""Browser-owned sessions and cross-origin security for SoilMate."""
import hashlib
import hmac
import os
import secrets
from typing import Optional, List
from contextvars import ContextVar
from app.config import settings

owner = ContextVar("owner", default="local-demo")


def get_session_secret() -> str:
    """Return configured session secret or generate a deterministic persistent fallback."""
    secret = (settings.session_secret or "").strip()
    if len(secret) >= 32:
        return secret
    # Deterministic fallback based on API key + salt so Render doesn't crash on startup if SESSION_SECRET is unset
    salt = "soilmate-session-security-salt-2026"
    seed = settings.gemini_api_keys_raw or os.getenv("RENDER_SERVICE_ID") or "soilmate-default-seed-key"
    return hashlib.sha256(f"{seed}-{salt}".encode()).hexdigest()


def allowed_origins() -> List[str]:
    """Extract list of explicitly configured origins, plus local defaults if in local mode."""
    origins = [s.strip().rstrip("/") for s in settings.frontend_url.split(",") if s.strip()]
    
    # Always include common local ports for development flexibility
    local_defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    for loc in local_defaults:
        if loc not in origins:
            origins.append(loc)
    return origins


def origin_is_allowed(origin: Optional[str]) -> bool:
    """Check whether a request or WebSocket Origin header is authorized."""
    if not origin:
        return True
    clean_origin = origin.strip().rstrip("/")
    allowed = allowed_origins()

    if clean_origin in allowed or "*" in allowed:
        return True

    # Automatically permit any Vercel deployment (*.vercel.app)
    if clean_origin.endswith(".vercel.app") or "vercel.app" in clean_origin:
        return True

    for item in allowed:
        if item == clean_origin:
            return True
        if "vercel.app" in item and clean_origin.endswith(".vercel.app"):
            return True

    return False


def identity(cookie: Optional[str]) -> Optional[str]:
    """Validate signed session token and return the unique owner identity."""
    if settings.app_mode == "local":
        return "local-demo"
    if not cookie or "." not in cookie:
        return None
    try:
        value, signature = cookie.rsplit(".", 1)
        expected = hmac.new(get_session_secret().encode(), value.encode(), hashlib.sha256).hexdigest()
        return value if hmac.compare_digest(signature, expected) else None
    except Exception:
        return None


def new_identity() -> tuple[str, str]:
    """Generate a new unique owner ID and a signed cookie/header token."""
    value = secrets.token_hex(24)
    signature = hmac.new(get_session_secret().encode(), value.encode(), hashlib.sha256).hexdigest()
    return value, f"{value}.{signature}"


def validate_deployment():
    """Verify runtime configuration on startup."""
    # Automatically switch to hosted mode if running in Render environment
    if os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_URL"):
        settings.app_mode = "hosted"

    if settings.app_mode not in {"local", "hosted"}:
        raise RuntimeError("APP_MODE must be 'local' or 'hosted'")
