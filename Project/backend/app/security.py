from __future__ import annotations

import base64
import secrets

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config.settings import settings


AUTH_EXEMPT_PATHS = {"/api/health"}


def _basic_auth_valid(header_value: str | None) -> bool:
    if not header_value or not header_value.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header_value.removeprefix("Basic ").strip()).decode("utf-8")
    except Exception:
        return False
    username, separator, password = decoded.partition(":")
    if not separator:
        return False
    expected_username = settings.basic_auth_username or ""
    expected_password = settings.basic_auth_password or ""
    return secrets.compare_digest(username, expected_username) and secrets.compare_digest(password, expected_password)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.basic_auth_enabled or request.url.path in AUTH_EXEMPT_PATHS:
            return await call_next(request)

        if _basic_auth_valid(request.headers.get("Authorization")):
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "Authentication required.", "error_code": "AUTH_REQUIRED"},
            headers={"WWW-Authenticate": 'Basic realm="sinkhole"'},
        )
