from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.main_deps import get_db
from app.models.schemas import MonitoringPointRequest
from app.services.monitoring_points import (
    add_monitoring_point,
    deactivate_monitoring_point,
    list_monitoring_points,
    refresh_monitoring_points,
)
from app.utils.response import fail, ok


router = APIRouter()


@router.get("/api/monitoring-points")
def monitoring_points(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return ok({"points": list_monitoring_points(conn)})


@router.post("/api/monitoring-points")
def create_monitoring_point(req: MonitoringPointRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        point = add_monitoring_point(
            conn,
            name=req.name,
            address=req.address,
            latitude=req.latitude,
            longitude=req.longitude,
        )
    except ValueError as exc:
        return fail(str(exc), "MONITORING_POINT_LIMIT")
    return ok({"point": point, "points": list_monitoring_points(conn)})


@router.post("/api/monitoring-points/refresh")
def refresh_points(
    force: bool = Query(default=False),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    return ok({"points": refresh_monitoring_points(conn, force=force)})


@router.delete("/api/monitoring-points/{point_id}")
def delete_monitoring_point(point_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    if not deactivate_monitoring_point(conn, point_id):
        return fail("모니터링 지점을 찾을 수 없습니다.", "MONITORING_POINT_NOT_FOUND")
    return ok({"points": list_monitoring_points(conn)})
