from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db.core import query_all, query_one
from app.main_deps import get_db
from app.services.addressing import with_road_address
from app.utils.response import ok, fail


router = APIRouter()


@router.get("/api/roads")
def list_roads(
    region_id: int | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if region_id:
        rows = query_all(
            conn,
            "SELECT road_id, road_name, road_type, center_lat, center_lon, region_id FROM road_segments WHERE region_id = ? ORDER BY road_id",
            (region_id,),
        )
    else:
        rows = query_all(
            conn,
            "SELECT road_id, road_name, road_type, center_lat, center_lon, region_id FROM road_segments ORDER BY road_id",
        )
    return ok([with_road_address(row) for row in rows])


@router.get("/api/road/{road_id}")
def get_road(road_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = query_one(
        conn,
        """
        SELECT road_id, road_name, road_type, start_lat, start_lon, end_lat, end_lon,
               center_lat, center_lon, length_m, region_id
        FROM road_segments
        WHERE road_id = ?
        """,
        (road_id,),
    )
    if not row:
        return fail("도로를 찾을 수 없습니다.", "NOT_FOUND")
    return ok(with_road_address(row))
