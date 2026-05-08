from __future__ import annotations

from datetime import date, timedelta
import sqlite3


DEMO_REGIONS = [
    {
        "region_id": 101,
        "region_name": "\uacbd\ub0a8 \uc9c4\uc8fc\uc2dc \uacbd\uc0c1\uad6d\ub9bd\ub300\ud559\uad50 \uac00\uc88c\ucea0\ud37c\uc2a4",
        "region_type": "campus",
        "latitude": 35.1525,
        "longitude": 128.1049,
        "sido": "\uacbd\uc0c1\ub0a8\ub3c4",
        "sigungu": "\uc9c4\uc8fc\uc2dc",
        "sinkhole_count": 5,
        "gpr_counts": [3, 2],
        "aging_score": 88.0,
        "building_density": 0.92,
        "road_density": 0.84,
        "land_use_type": "\uad50\uc721",
        "construction_scale": 18.0,
        "rainfall_pattern": [20, 18, 17, 15, 12, 10, 9],
        "groundwater_variation": 1.28,
        "cause_types": ["\ub9e4\uc124\ubc30\uad00 \uc190\uc0c1", "\uad74\ucc29 \uc601\ud5a5", "\uc9c0\ubc18 \uc57d\ud654"],
    },
    {
        "region_id": 102,
        "region_name": "\uacbd\ub0a8 \uc9c4\uc8fc\uc2dc \uc9c4\uc8fc\uc5ed \uc77c\ub300",
        "region_type": "urban_core",
        "latitude": 35.1801,
        "longitude": 128.1074,
        "sido": "\uacbd\uc0c1\ub0a8\ub3c4",
        "sigungu": "\uc9c4\uc8fc\uc2dc",
        "sinkhole_count": 4,
        "gpr_counts": [2, 1],
        "aging_score": 73.0,
        "building_density": 0.88,
        "road_density": 0.79,
        "land_use_type": "\uc0c1\uc5c5",
        "construction_scale": 13.0,
        "rainfall_pattern": [14, 13, 11, 10, 9, 8, 7],
        "groundwater_variation": 1.02,
        "cause_types": ["\ud558\uc218\uad00 \uc190\uc0c1", "\ub3c4\uc2dc \uad74\ucc29"],
    },
    {
        "region_id": 103,
        "region_name": "\uacbd\ub0a8 \uc9c4\uc8fc\uc2dc \ud601\uc2e0\ub3c4\uc2dc",
        "region_type": "district",
        "latitude": 35.1815,
        "longitude": 128.1698,
        "sido": "\uacbd\uc0c1\ub0a8\ub3c4",
        "sigungu": "\uc9c4\uc8fc\uc2dc",
        "sinkhole_count": 2,
        "gpr_counts": [1],
        "aging_score": 54.0,
        "building_density": 0.63,
        "road_density": 0.61,
        "land_use_type": "\ud63c\ud569",
        "construction_scale": 6.0,
        "rainfall_pattern": [8, 8, 7, 6, 5, 4, 4],
        "groundwater_variation": 0.66,
        "cause_types": ["\uc9c0\ubc18 \uc57d\ud654"],
    },
    {
        "region_id": 104,
        "region_name": "\uacbd\ub0a8 \uc9c4\uc8fc\uc2dc \uc9c4\uc591\ud638 \uc785\uad6c",
        "region_type": "waterfront",
        "latitude": 35.1730,
        "longitude": 128.0418,
        "sido": "\uacbd\uc0c1\ub0a8\ub3c4",
        "sigungu": "\uc9c4\uc8fc\uc2dc",
        "sinkhole_count": 1,
        "gpr_counts": [0],
        "aging_score": 39.0,
        "building_density": 0.44,
        "road_density": 0.38,
        "land_use_type": "\uc790\uc5f0",
        "construction_scale": 2.0,
        "rainfall_pattern": [5, 4, 4, 3, 3, 2, 2],
        "groundwater_variation": 0.31,
        "cause_types": ["\ubc30\uc218 \ubd88\ub7c9"],
    },
    {
        "region_id": 105,
        "region_name": "\uacbd\ub0a8 \uc0ac\ucc9c\uc2dc \uc0ac\ucc9c\uacf5\ud56d \uc778\uadfc",
        "region_type": "airport",
        "latitude": 35.0880,
        "longitude": 128.0725,
        "sido": "\uacbd\uc0c1\ub0a8\ub3c4",
        "sigungu": "\uc0ac\ucc9c\uc2dc",
        "sinkhole_count": 0,
        "gpr_counts": [0],
        "aging_score": 23.0,
        "building_density": 0.25,
        "road_density": 0.27,
        "land_use_type": "\uad50\ud1b5",
        "construction_scale": 0.0,
        "rainfall_pattern": [2, 2, 1, 1, 1, 0, 0],
        "groundwater_variation": 0.12,
        "cause_types": ["\uc5c6\uc74c"],
    },
]


DEMO_ROADS = [
    {
        "road_id": 1001,
        "region_id": 101,
        "road_name": "\uac00\uc88c\ucea0\ud37c\uc2a4 \ub3d9\uc9c4\ub85c",
        "road_type": "campus_arterial",
        "start_lat": 35.1509,
        "start_lon": 128.1009,
        "end_lat": 35.1542,
        "end_lon": 128.1081,
        "length_m": 780.0,
        "sinkhole_count": 3,
        "gpr_counts": [2, 1],
        "aging_score": 82.0,
        "building_density": 0.90,
        "road_density": 0.82,
        "land_use_type": "\uad50\uc721",
        "drainage_quality": 0.74,
        "slope_grade": 0.36,
        "construction_scale": 15.0,
        "cause_types": ["\ub9e4\uc124\ubc30\uad00 \uc190\uc0c1", "\uad74\ucc29 \uc601\ud5a5", "\uc9c0\ubc18 \uc57d\ud654"],
    },
    {
        "road_id": 1002,
        "region_id": 101,
        "road_name": "\uac00\uc88c\ucea0\ud37c\uc2a4 \uc11c\ubb38\ub85c",
        "road_type": "local",
        "start_lat": 35.1518,
        "start_lon": 128.0978,
        "end_lat": 35.1534,
        "end_lon": 128.1030,
        "length_m": 520.0,
        "sinkhole_count": 2,
        "gpr_counts": [1],
        "aging_score": 67.0,
        "building_density": 0.78,
        "road_density": 0.68,
        "land_use_type": "\uad50\uc721",
        "drainage_quality": 0.56,
        "slope_grade": 0.42,
        "construction_scale": 8.0,
        "cause_types": ["\ubc30\uc218 \ubd88\ub7c9", "\uc9c0\ubc18 \uc57d\ud654"],
    },
    {
        "road_id": 1003,
        "region_id": 102,
        "road_name": "\uc9c4\uc8fc\uc5ed \uc911\uc559\ub85c",
        "road_type": "arterial",
        "start_lat": 35.1779,
        "start_lon": 128.1044,
        "end_lat": 35.1820,
        "end_lon": 128.1106,
        "length_m": 690.0,
        "sinkhole_count": 2,
        "gpr_counts": [2],
        "aging_score": 76.0,
        "building_density": 0.91,
        "road_density": 0.84,
        "land_use_type": "\uc0c1\uc5c5",
        "drainage_quality": 0.69,
        "slope_grade": 0.28,
        "construction_scale": 12.0,
        "cause_types": ["\ud558\uc218\uad00 \uc190\uc0c1", "\ub3c4\uc2dc \uad74\ucc29"],
    },
    {
        "road_id": 1004,
        "region_id": 102,
        "road_name": "\uc9c4\uc8fc\uc5ed \ud658\uc2b9\ub85c",
        "road_type": "transit",
        "start_lat": 35.1795,
        "start_lon": 128.1017,
        "end_lat": 35.1810,
        "end_lon": 128.1084,
        "length_m": 610.0,
        "sinkhole_count": 1,
        "gpr_counts": [1],
        "aging_score": 62.0,
        "building_density": 0.82,
        "road_density": 0.80,
        "land_use_type": "\uc0c1\uc5c5",
        "drainage_quality": 0.52,
        "slope_grade": 0.25,
        "construction_scale": 5.0,
        "cause_types": ["\ud558\uc218\uad00 \uc190\uc0c1"],
    },
    {
        "road_id": 1005,
        "region_id": 103,
        "road_name": "\ud601\uc2e0\ub3c4\uc2dc \uc21c\ud658\ub85c",
        "road_type": "collector",
        "start_lat": 35.1798,
        "start_lon": 128.1658,
        "end_lat": 35.1830,
        "end_lon": 128.1730,
        "length_m": 740.0,
        "sinkhole_count": 1,
        "gpr_counts": [1],
        "aging_score": 48.0,
        "building_density": 0.61,
        "road_density": 0.58,
        "land_use_type": "\ud63c\ud569",
        "drainage_quality": 0.41,
        "slope_grade": 0.34,
        "construction_scale": 4.0,
        "cause_types": ["\uc9c0\ubc18 \uc57d\ud654"],
    },
    {
        "road_id": 1006,
        "region_id": 104,
        "road_name": "\uc9c4\uc591\ud638 \uc9c4\uc785\ub85c",
        "road_type": "waterfront",
        "start_lat": 35.1715,
        "start_lon": 128.0388,
        "end_lat": 35.1748,
        "end_lon": 128.0450,
        "length_m": 590.0,
        "sinkhole_count": 1,
        "gpr_counts": [0],
        "aging_score": 36.0,
        "building_density": 0.40,
        "road_density": 0.35,
        "land_use_type": "\uc790\uc5f0",
        "drainage_quality": 0.47,
        "slope_grade": 0.52,
        "construction_scale": 2.0,
        "cause_types": ["\ubc30\uc218 \ubd88\ub7c9"],
    },
    {
        "road_id": 1007,
        "region_id": 105,
        "road_name": "\uc0ac\ucc9c\uacf5\ud56d \uc811\uadfc\ub85c",
        "road_type": "airport_access",
        "start_lat": 35.0856,
        "start_lon": 128.0690,
        "end_lat": 35.0902,
        "end_lon": 128.0760,
        "length_m": 760.0,
        "sinkhole_count": 0,
        "gpr_counts": [0],
        "aging_score": 24.0,
        "building_density": 0.26,
        "road_density": 0.29,
        "land_use_type": "\uad50\ud1b5",
        "drainage_quality": 0.22,
        "slope_grade": 0.18,
        "construction_scale": 0.0,
        "cause_types": ["\uc5c6\uc74c"],
    },
]


def _clear_demo_tables(conn: sqlite3.Connection) -> None:
    for table in [
        "ai_report",
        "road_risk_analysis_result",
        "road_feature_dataset",
        "road_construction_events",
        "road_environment_features",
        "road_facility_safety",
        "road_gpr_inspection",
        "road_sinkhole_history",
        "road_segments",
        "risk_analysis_result",
        "feature_dataset",
        "underground_safety",
        "facility_status",
        "facility_inspection",
        "construction_events",
        "environment_features",
        "groundwater_data",
        "weather_data",
        "facility_safety",
        "gpr_inspection",
        "sinkhole_history",
        "regions",
    ]:
        conn.execute(f"DELETE FROM {table}")


def _seed_demo_roads(conn: sqlite3.Connection, today: date) -> None:
    for road in DEMO_ROADS:
        center_lat = (float(road["start_lat"]) + float(road["end_lat"])) / 2
        center_lon = (float(road["start_lon"]) + float(road["end_lon"])) / 2
        geometry = (
            f"LINESTRING({road['start_lon']} {road['start_lat']}, "
            f"{road['end_lon']} {road['end_lat']})"
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO road_segments(
                road_id, region_id, road_name, road_type,
                start_lat, start_lon, end_lat, end_lon, center_lat, center_lon,
                length_m, geometry
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                road["road_id"],
                road["region_id"],
                road["road_name"],
                road["road_type"],
                road["start_lat"],
                road["start_lon"],
                road["end_lat"],
                road["end_lon"],
                round(center_lat, 6),
                round(center_lon, 6),
                road["length_m"],
                geometry,
            ),
        )

        existing_factors = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM road_sinkhole_history WHERE road_id = ?) +
                (SELECT COUNT(*) FROM road_gpr_inspection WHERE road_id = ?) +
                (SELECT COUNT(*) FROM road_facility_safety WHERE road_id = ?) +
                (SELECT COUNT(*) FROM road_environment_features WHERE road_id = ?) +
                (SELECT COUNT(*) FROM road_construction_events WHERE road_id = ?)
            """,
            (road["road_id"], road["road_id"], road["road_id"], road["road_id"], road["road_id"]),
        ).fetchone()[0]
        if existing_factors:
            continue

        for idx in range(int(road["sinkhole_count"])):
            cause_types = road["cause_types"]
            conn.execute(
                """
                INSERT INTO road_sinkhole_history(road_id, occurrence_date, section_start, section_end, cause_type, damage_scale)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    road["road_id"],
                    str(today - timedelta(days=150 * (idx + 1))),
                    f"{idx * 100}m",
                    f"{(idx + 1) * 100}m",
                    cause_types[idx % len(cause_types)],
                    round(2.0 + idx * 0.9, 1),
                ),
            )

        for idx, cavity_count in enumerate(road["gpr_counts"], start=1):
            conn.execute(
                """
                INSERT INTO road_gpr_inspection(road_id, inspection_date, cavity_detected, cavity_count, depth_estimate)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    road["road_id"],
                    str(today - timedelta(days=idx * 18)),
                    1 if cavity_count > 0 else 0,
                    cavity_count,
                    round(1.4 + idx * 0.6, 1),
                ),
            )

        conn.execute(
            """
            INSERT INTO road_facility_safety(road_id, facility_type, aging_score, inspection_count)
            VALUES(?, ?, ?, ?)
            """,
            (
                road["road_id"],
                "\uc9c0\ud558 \uc2dc\uc124\ubb3c",
                road["aging_score"],
                max(1, int(road["sinkhole_count"]) + 1),
            ),
        )

        conn.execute(
            """
            INSERT INTO road_environment_features(
                road_id, building_density, road_density, land_use_type, drainage_quality, slope_grade
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                road["road_id"],
                road["building_density"],
                road["road_density"],
                road["land_use_type"],
                road["drainage_quality"],
                road["slope_grade"],
            ),
        )

        if road["construction_scale"] > 0:
            conn.execute(
                """
                INSERT INTO road_construction_events(
                    road_id, construction_type, start_date, end_date, scale_score, impact_score
                )
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    road["road_id"],
                    "\ub3c4\ub85c \uad74\ucc29 \ubc0f \uc9c0\ud558\ub9e4\uc124 \uacf5\uc0ac",
                    str(today - timedelta(days=45)),
                    str(today + timedelta(days=20)),
                    road["construction_scale"],
                    min(20.0, float(road["construction_scale"]) * 1.1),
                ),
            )


def seed_if_empty(conn: sqlite3.Connection, *, force: bool = False) -> None:
    existing_count = conn.execute("SELECT COUNT(*) FROM regions").fetchone()[0]
    if existing_count and not force:
        demo_region_count = conn.execute(
            "SELECT COUNT(*) FROM regions WHERE region_id IN (101, 102, 103, 104, 105)"
        ).fetchone()[0]
        road_count = conn.execute("SELECT COUNT(*) FROM road_segments").fetchone()[0]
        if demo_region_count == len(DEMO_REGIONS) and road_count == 0:
            _seed_demo_roads(conn, date.today())
        return

    _clear_demo_tables(conn)
    today = date.today()

    for demo in DEMO_REGIONS:
        conn.execute(
            """
            INSERT INTO regions(region_id, region_name, region_type, latitude, longitude, sido, sigungu, geom)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                demo["region_id"],
                demo["region_name"],
                demo["region_type"],
                demo["latitude"],
                demo["longitude"],
                demo["sido"],
                demo["sigungu"],
                None,
            ),
        )

        for idx in range(demo["sinkhole_count"]):
            cause_types = demo["cause_types"]
            conn.execute(
                """
                INSERT INTO sinkhole_history(region_id, occurrence_date, cause_type, damage_scale)
                VALUES(?, ?, ?, ?)
                """,
                (
                    demo["region_id"],
                    str(today - timedelta(days=180 * (idx + 1))),
                    cause_types[idx % len(cause_types)],
                    round(2.5 + idx * 1.1, 1),
                ),
            )

        for idx, cavity_count in enumerate(demo["gpr_counts"], start=1):
            conn.execute(
                """
                INSERT INTO gpr_inspection(region_id, inspection_date, cavity_detected, cavity_count, depth_estimate)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    demo["region_id"],
                    str(today - timedelta(days=idx * 21)),
                    1 if cavity_count > 0 else 0,
                    cavity_count,
                    round(1.8 + idx * 0.7, 1),
                ),
            )

        conn.execute(
            """
            INSERT INTO facility_safety(region_id, facility_type, aging_score, inspection_count)
            VALUES(?, ?, ?, ?)
            """,
            (
                demo["region_id"],
                "\uc9c0\ud558 \uc2dc\uc124\ubb3c",
                demo["aging_score"],
                max(1, int(demo["sinkhole_count"] + 2)),
            ),
        )

        rainfall_pattern = demo["rainfall_pattern"]
        for offset in range(30):
            day = today - timedelta(days=offset)
            rainfall = rainfall_pattern[offset] if offset < len(rainfall_pattern) else max(rainfall_pattern[-1] - 0.2 * (offset - 6), 0)
            conn.execute(
                """
                INSERT INTO weather_data(region_id, record_date, rainfall, temperature, humidity)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    demo["region_id"],
                    str(day),
                    round(float(rainfall), 1),
                    round(17.0 - offset * 0.03, 1),
                    round(60.0 + min(offset, 10) * 0.3, 1),
                ),
            )
            conn.execute(
                """
                INSERT INTO groundwater_data(region_id, record_date, groundwater_level, variation)
                VALUES(?, ?, ?, ?)
                """,
                (
                    demo["region_id"],
                    str(day),
                    round(2.4 + demo["groundwater_variation"] * 1.8 + offset * 0.01, 2),
                    round(demo["groundwater_variation"], 2),
                ),
            )

        conn.execute(
            """
            INSERT INTO environment_features(region_id, building_density, road_density, land_use_type)
            VALUES(?, ?, ?, ?)
            """,
            (
                demo["region_id"],
                demo["building_density"],
                demo["road_density"],
                demo["land_use_type"],
            ),
        )

        if demo["construction_scale"] > 0:
            conn.execute(
                """
                INSERT INTO construction_events(region_id, construction_type, start_date, scale_score)
                VALUES(?, ?, ?, ?)
                """,
                (
                    demo["region_id"],
                    "\ub3c4\uc2ec \uad74\ucc29 \uacf5\uc0ac",
                    str(today - timedelta(days=75)),
                    demo["construction_scale"],
                ),
            )

    _seed_demo_roads(conn, today)
