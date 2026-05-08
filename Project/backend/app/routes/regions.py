from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db.core import query_all, query_one
from app.main_deps import get_db
from app.services.addressing import with_region_address
from app.utils.response import fail, ok


router = APIRouter()


@router.get("/api/regions")
def list_regions(
    region_type: str | None = Query(default=None),
    sido: str | None = Query(default=None),
    sigungu: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    where = []
    params: list[str] = []
    if region_type:
        where.append("region_type = ?")
        params.append(region_type)
    if sido:
        where.append("sido = ?")
        params.append(sido)
    if sigungu:
        where.append("sigungu = ?")
        params.append(sigungu)

    sql = "SELECT region_id, region_name, region_type, latitude, longitude, sido, sigungu FROM regions"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY region_id"
    return ok([with_region_address(row) for row in query_all(conn, sql, tuple(params))])


@router.get("/api/region/{region_id}")
def get_region(region_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = query_one(
        conn,
        """
        SELECT region_id, region_name, region_type, sido, sigungu, latitude, longitude
        FROM regions
        WHERE region_id = ?
        """,
        (region_id,),
    )
    if not row:
        return fail("데이터를 찾을 수 없습니다.", "NOT_FOUND")
    return ok(with_region_address(row))
