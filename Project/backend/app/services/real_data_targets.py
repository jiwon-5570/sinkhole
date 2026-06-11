from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.db.core import query_one


SEOUL_METRO_BOUNDS = {
    "lat_min": 37.30,
    "lat_max": 37.70,
    "lon_min": 126.75,
    "lon_max": 127.25,
}

SEOUL_METRO_TARGET_LABELS = (
    ("강동·하남권", "서울특별시", "강동구"),
    ("강남권", "서울특별시", "강남구"),
    ("송파·성남권", "서울특별시", "송파구"),
    ("송파·광진권", "서울특별시", "송파구"),
    ("송파·강동권", "서울특별시", "송파구"),
    ("강서·마곡권", "서울특별시", "강서구"),
    ("영등포·마포권", "서울특별시", "영등포구"),
    ("서초·강남권", "서울특별시", "서초구"),
    ("성동·동대문권", "서울특별시", "성동구"),
    ("마포·상암권", "서울특별시", "마포구"),
    ("중구·용산권", "서울특별시", "용산구"),
    ("구로·금천권", "서울특별시", "구로구"),
)

REGION_ID_BASE = 900001
GRID_SIZE_DEGREES = 0.05
DEFAULT_TARGET_LIMIT = len(SEOUL_METRO_TARGET_LABELS)
MIN_BOREHOLES_PER_TARGET = 100
ROAD_AXIS_HALF_SPAN_DEGREES = 0.0045


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
            SEOUL_METRO_BOUNDS["lat_min"],
            SEOUL_METRO_BOUNDS["lat_max"],
            SEOUL_METRO_BOUNDS["lon_min"],
            SEOUL_METRO_BOUNDS["lon_max"],
        ),
    )
    return int((row or {}).get("count") or 0) > 0


def _is_replaceable_generated_regions(conn: sqlite3.Connection) -> bool:
    region_count = _table_count(conn, "regions")
    if region_count <= 0:
        return True
    non_generated = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM regions
        WHERE COALESCE(region_type, '') != 'public_ground_cluster'
        """,
    )
    if int((non_generated or {}).get("count") or 0) > 0:
        return False
    metro = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM regions
        WHERE geom LIKE '%seoul_metro_borehole_grid%'
        """,
    )
    return int((metro or {}).get("count") or 0) < min(DEFAULT_TARGET_LIMIT, region_count)


def _clear_generated_regions(conn: sqlite3.Connection) -> None:
    ids = [
        int(row["region_id"])
        for row in conn.execute(
            """
            SELECT region_id
            FROM regions
            WHERE COALESCE(region_type, '') = 'public_ground_cluster'
            """
        ).fetchall()
    ]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    road_ids = [
        int(row["road_id"])
        for row in conn.execute(f"SELECT road_id FROM road_segments WHERE region_id IN ({placeholders})", ids).fetchall()
    ]
    if road_ids:
        road_placeholders = ",".join("?" for _ in road_ids)
        conn.execute(f"DELETE FROM road_risk_analysis_result WHERE road_id IN ({road_placeholders})", road_ids)
        conn.execute(f"DELETE FROM road_feature_dataset WHERE road_id IN ({road_placeholders})", road_ids)
    for table_name in (
        "risk_analysis_result",
        "feature_dataset",
        "sinkhole_history",
        "gpr_inspection",
        "facility_safety",
        "facility_inspection",
        "facility_status",
        "facility_accidents",
        "underground_safety",
        "weather_data",
        "groundwater_data",
        "environment_features",
        "construction_events",
        "road_segments",
    ):
        conn.execute(f"DELETE FROM {table_name} WHERE region_id IN ({placeholders})", ids)
    conn.execute(f"DELETE FROM regions WHERE region_id IN ({placeholders})", ids)


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
            SEOUL_METRO_BOUNDS["lat_min"],
            GRID_SIZE_DEGREES,
            SEOUL_METRO_BOUNDS["lon_min"],
            GRID_SIZE_DEGREES,
            SEOUL_METRO_BOUNDS["lat_min"],
            SEOUL_METRO_BOUNDS["lat_max"],
            SEOUL_METRO_BOUNDS["lon_min"],
            SEOUL_METRO_BOUNDS["lon_max"],
            MIN_BOREHOLES_PER_TARGET,
            limit,
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def _generated_public_regions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT region_id, region_name, latitude, longitude
        FROM regions
        WHERE COALESCE(region_type, '') = 'public_ground_cluster'
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY region_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _ensure_public_ground_roads(conn: sqlite3.Connection) -> int:
    inserted = 0
    for region in _generated_public_regions(conn):
        region_id = int(region["region_id"])
        existing = query_one(
            conn,
            "SELECT COUNT(*) AS count FROM road_segments WHERE region_id = ?",
            (region_id,),
        )
        if int((existing or {}).get("count") or 0) > 0:
            continue

        latitude = float(region["latitude"])
        longitude = float(region["longitude"])
        axes = (
            (
                1,
                "inspection east-west axis",
                latitude,
                longitude - ROAD_AXIS_HALF_SPAN_DEGREES,
                latitude,
                longitude + ROAD_AXIS_HALF_SPAN_DEGREES,
            ),
            (
                2,
                "inspection north-south axis",
                latitude - ROAD_AXIS_HALF_SPAN_DEGREES,
                longitude,
                latitude + ROAD_AXIS_HALF_SPAN_DEGREES,
                longitude,
            ),
        )
        for axis_index, road_name, start_lat, start_lon, end_lat, end_lon in axes:
            road_id = region_id * 10 + axis_index
            geometry = {
                "source": "molit_ground_boreholes",
                "method": "public_ground_cluster_axis",
                "region_id": region_id,
                "axis": axis_index,
            }
            before_changes = conn.total_changes
            conn.execute(
                """
                INSERT OR IGNORE INTO road_segments(
                    road_id, region_id, road_name, road_type,
                    start_lat, start_lon, end_lat, end_lon,
                    center_lat, center_lon, length_m, geometry
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    road_id,
                    region_id,
                    road_name,
                    "public_ground_inspection_axis",
                    start_lat,
                    start_lon,
                    end_lat,
                    end_lon,
                    latitude,
                    longitude,
                    1000.0,
                    json.dumps(geometry, ensure_ascii=False),
                ),
            )
            if conn.total_changes > before_changes:
                inserted += 1
    return inserted


def ensure_public_ground_regions(conn: sqlite3.Connection, limit: int = DEFAULT_TARGET_LIMIT) -> int:
    """Create operational analysis targets only from imported public borehole data.

    The production dashboard must not fall back to demo regions. If the regions
    table is empty or still contains only generated public-ground targets, this
    builds Seoul/metropolitan grid targets from actual MOLIT borehole density.
    """

    if not _has_molit_ground_coordinates(conn):
        return 0

    if not _is_replaceable_generated_regions(conn):
        non_generated = query_one(
            conn,
            """
            SELECT COUNT(*) AS count
            FROM regions
            WHERE COALESCE(region_type, '') != 'public_ground_cluster'
            """,
        )
        if int((non_generated or {}).get("count") or 0) > 0:
            return 0
        return _ensure_public_ground_roads(conn)

    _clear_generated_regions(conn)
    candidates = _candidate_cells(conn, limit)
    inserted = 0
    for index, row in enumerate(candidates, start=1):
        region_id = REGION_ID_BASE + index - 1
        area_label, sido, sigungu = SEOUL_METRO_TARGET_LABELS[(index - 1) % len(SEOUL_METRO_TARGET_LABELS)]
        source_meta = {
            "source": "molit_ground_boreholes",
            "method": "seoul_metro_borehole_grid",
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
                f"서울/수도권 공공 지층 분석지점 {index} - {area_label}",
                "public_ground_cluster",
                float(row["latitude"]),
                float(row["longitude"]),
                sido,
                sigungu,
                json.dumps(source_meta, ensure_ascii=False),
            ),
        )
        inserted += 1
    return inserted + _ensure_public_ground_roads(conn)
