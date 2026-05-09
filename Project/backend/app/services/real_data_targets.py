from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.db.core import query_one


JINJU_BOUNDS = {
    "lat_min": 35.0,
    "lat_max": 35.35,
    "lon_min": 127.9,
    "lon_max": 128.3,
}

REGION_ID_BASE = 900001
GRID_SIZE_DEGREES = 0.025
DEFAULT_TARGET_LIMIT = 8
MIN_BOREHOLES_PER_TARGET = 12


def _table_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _has_molit_ground_coordinates(conn: sqlite3.Connection) -> bool:
    row = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM molit_ground_boreholes
        WHERE latitude BETWEEN ? AND ?
          AND longitude BETWEEN ? AND ?
        """,
        (
            JINJU_BOUNDS["lat_min"],
            JINJU_BOUNDS["lat_max"],
            JINJU_BOUNDS["lon_min"],
            JINJU_BOUNDS["lon_max"],
        ),
    )
    return int((row or {}).get("count") or 0) > 0


def _candidate_cells(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            CAST((latitude - ?) / ? AS INTEGER) AS lat_bin,
            CAST((longitude - ?) / ? AS INTEGER) AS lon_bin,
            COUNT(*) AS borehole_count,
            AVG(latitude) AS latitude,
            AVG(longitude) AS longitude,
            AVG(CASE
                WHEN total_depth_m IS NOT NULL
                 AND total_depth_m > 0
                 AND total_depth_m < 300
                THEN total_depth_m
            END) AS avg_total_depth_m,
            AVG(CASE
                WHEN groundwater_level_m IS NOT NULL
                 AND ABS(groundwater_level_m) > 0.01
                 AND ABS(groundwater_level_m) < 100
                THEN ABS(groundwater_level_m)
            END) AS avg_groundwater_depth_m
        FROM molit_ground_boreholes
        WHERE latitude BETWEEN ? AND ?
          AND longitude BETWEEN ? AND ?
        GROUP BY lat_bin, lon_bin
        HAVING COUNT(*) >= ?
        ORDER BY borehole_count DESC, latitude ASC, longitude ASC
        LIMIT ?
        """,
        (
            JINJU_BOUNDS["lat_min"],
            GRID_SIZE_DEGREES,
            JINJU_BOUNDS["lon_min"],
            GRID_SIZE_DEGREES,
            JINJU_BOUNDS["lat_min"],
            JINJU_BOUNDS["lat_max"],
            JINJU_BOUNDS["lon_min"],
            JINJU_BOUNDS["lon_max"],
            MIN_BOREHOLES_PER_TARGET,
            limit,
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def ensure_public_ground_regions(conn: sqlite3.Connection, limit: int = DEFAULT_TARGET_LIMIT) -> int:
    """Create operational analysis targets only from imported public borehole data.

    The production dashboard must not fall back to demo regions. If the regions
    table is empty but MOLIT borehole coordinates are present, this builds a
    small set of Jinju-area grid targets from actual borehole density.
    """

    if _table_count(conn, "regions") > 0:
        return 0
    if not _has_molit_ground_coordinates(conn):
        return 0

    candidates = _candidate_cells(conn, limit)
    inserted = 0
    for index, row in enumerate(candidates, start=1):
        region_id = REGION_ID_BASE + index - 1
        source_meta = {
            "source": "molit_ground_boreholes",
            "method": "jinju_borehole_grid",
            "grid_size_degrees": GRID_SIZE_DEGREES,
            "borehole_count": int(row["borehole_count"]),
            "avg_total_depth_m": row.get("avg_total_depth_m"),
            "avg_groundwater_depth_m": row.get("avg_groundwater_depth_m"),
        }
        conn.execute(
            """
            INSERT INTO regions(region_id, region_name, region_type, latitude, longitude, sido, sigungu, geom)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                region_id,
                f"진주 공공 지층 분석지점 {index}",
                "public_ground_cluster",
                float(row["latitude"]),
                float(row["longitude"]),
                "경상남도",
                "진주시",
                json.dumps(source_meta, ensure_ascii=False),
            ),
        )
        inserted += 1
    return inserted
