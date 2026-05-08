from __future__ import annotations

from fastapi import APIRouter, Response

from app.config.settings import settings
from app.db.core import connect, query_one
from app.utils.response import fail, ok


router = APIRouter()


@router.get("/api/health")
def health(response: Response) -> dict:
    try:
        conn = connect(settings.db_path)
        try:
            query_one(conn, "SELECT 1 AS ok")
            table_row = query_one(
                conn,
                "SELECT COUNT(*) AS count FROM sqlite_master WHERE type = 'table'",
            )
        finally:
            conn.close()
    except Exception as exc:
        response.status_code = 503
        return fail(
            "Service unhealthy.",
            "HEALTH_CHECK_FAILED",
            data={
                "status": "error",
                "database": {"status": "error", "message": str(exc)},
            },
        )

    return ok(
        {
            "status": "ok",
            "environment": settings.environment,
            "database": {
                "status": "ok",
                "table_count": int(table_row["count"] if table_row else 0),
            },
        }
    )
