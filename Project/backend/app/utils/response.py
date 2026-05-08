from __future__ import annotations

from typing import Any


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def fail(message: str, error_code: str = "ERROR", *, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"success": False, "message": message, "error_code": error_code}
    if data is not None:
        payload["data"] = data
    return payload
