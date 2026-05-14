from __future__ import annotations

from datetime import date, datetime
from math import cos, radians
import sqlite3

from app.db.core import query_one
from app.services.ground_layers import summarize_ground_layers_for_region, summarize_ground_layers_for_road


def today_str() -> str:
    return str(date.today())


def normalize_local_datetime(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", "T")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def resolve_analysis_date(analysis_date: str | None = None, client_local_datetime: str | None = None) -> str:
    if analysis_date:
        return str(analysis_date)
    normalized = normalize_local_datetime(client_local_datetime)
    if normalized:
        return normalized.split("T", 1)[0]
    return today_str()


def format_client_clock_label(
    client_local_datetime: str | None = None,
    client_timezone: str | None = None,
    client_utc_offset_minutes: int | None = None,
) -> str | None:
    normalized = normalize_local_datetime(client_local_datetime)
    if not normalized:
        return None

    date_part, time_part = normalized.split("T", 1)
    labels: list[str] = []
    if client_timezone:
        labels.append(str(client_timezone))
    if client_utc_offset_minutes is not None:
        offset_total = int(client_utc_offset_minutes)
        sign = "+" if offset_total >= 0 else "-"
        offset_abs = abs(offset_total)
        hh = offset_abs // 60
        mm = offset_abs % 60
        labels.append(f"UTC{sign}{hh:02d}:{mm:02d}")
    if labels:
        return f"{date_part} {time_part} ({', '.join(labels)})"
    return f"{date_part} {time_part}"


def _molit_groundwater_score_near(
    conn: sqlite3.Connection,
    latitude: float | None,
    longitude: float | None,
    *,
    radius_m: float = 1500.0,
) -> float:
    if latitude is None or longitude is None:
        return 0.0

    lat = float(latitude)
    lon = float(longitude)
    lat_delta = radius_m / 111320.0
    lon_delta = radius_m / max(111320.0 * cos(radians(lat)), 1.0)
    row = query_one(
        conn,
        """
        SELECT
            COUNT(*) AS count,
            AVG(ABS(groundwater_level_m)) AS avg_depth_m,
            SUM(CASE WHEN ABS(groundwater_level_m) <= 2 THEN 1 ELSE 0 END) AS shallow_count
        FROM molit_ground_boreholes
        WHERE latitude BETWEEN ? AND ?
          AND longitude BETWEEN ? AND ?
          AND groundwater_level_m IS NOT NULL
          AND ABS(groundwater_level_m) > 0.01
          AND ABS(groundwater_level_m) < 100
        """,
        (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta),
    )
    count = int((row or {}).get("count") or 0)
    if count <= 0:
        return 0.0

    avg_depth = float((row or {}).get("avg_depth_m") or 0.0)
    shallow_count = int((row or {}).get("shallow_count") or 0)
    shallow_ratio = shallow_count / count if count else 0.0
    depth_component = max(0.0, 8.0 - min(avg_depth, 8.0))
    density_component = min(1.0, count / 30.0)
    shallow_component = shallow_ratio * 2.0
    return round(min(8.0, depth_component + density_component + shallow_component), 2)


def _molit_groundwater_score_for_region(conn: sqlite3.Connection, region_id: int) -> float:
    row = query_one(conn, "SELECT latitude, longitude FROM regions WHERE region_id = ?", (region_id,))
    if not row:
        return 0.0
    return _molit_groundwater_score_near(conn, row.get("latitude"), row.get("longitude"))


def _molit_groundwater_score_for_road(conn: sqlite3.Connection, road_id: int) -> float:
    row = query_one(conn, "SELECT center_lat, center_lon FROM road_segments WHERE road_id = ?", (road_id,))
    if not row:
        return 0.0
    return _molit_groundwater_score_near(conn, row.get("center_lat"), row.get("center_lon"))


def _facility_status_aging_score(conn: sqlite3.Connection, region_id: int) -> float:
    status_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(facility_status)")}
    ratio_expr = "COALESCE(MAX(aging_ratio), 0)" if "aging_ratio" in status_columns else "0"
    row = query_one(
        conn,
        f"""
        SELECT
            COALESCE(SUM(total_count), 0) AS total_count,
            COALESCE(SUM(aging_count), 0) AS aging_count,
            {ratio_expr} AS max_aging_ratio
        FROM facility_status
        WHERE region_id = ?
        """,
        (region_id,),
    )
    if not row:
        return 0.0

    total_count = float(row.get("total_count") or 0.0)
    aging_count = float(row.get("aging_count") or 0.0)
    if total_count > 0:
        return round(min(100.0, max(0.0, aging_count / total_count * 100.0)), 2)

    ratio = float(row.get("max_aging_ratio") or 0.0)
    if ratio <= 0:
        return 0.0
    if ratio <= 1:
        ratio *= 100.0
    return round(min(100.0, max(0.0, ratio)), 2)


def _road_region_id(conn: sqlite3.Connection, road_id: int) -> int | None:
    row = query_one(conn, "SELECT region_id FROM road_segments WHERE road_id = ?", (road_id,))
    return int(row["region_id"]) if row and row.get("region_id") is not None else None


def _apply_ground_layer_adjustment(conn: sqlite3.Connection, row: dict, *, region_id: int | None = None, road_id: int | None = None) -> dict:
    data = dict(row)
    if region_id is not None:
        summary = summarize_ground_layers_for_region(conn, region_id)
    elif road_id is not None:
        summary = summarize_ground_layers_for_road(conn, road_id)
    else:
        summary = {"available": False, "score": 0.0}

    ground_layer_score = float(summary.get("score") or 0.0)
    base_environment_score = float(data.get("environment_score") or 0.0)
    data["ground_layer_score"] = round(ground_layer_score, 2)
    data["ground_layer_nearby_count"] = int(summary.get("nearby_count") or 0)
    data["ground_layer_summary"] = summary
    data["environment_score"] = min(6.0, base_environment_score + ground_layer_score)
    return data


def load_or_build_feature_row(conn: sqlite3.Connection, region_id: int, analysis_date: str) -> dict:
    row = query_one(
        conn,
        """
        SELECT *
        FROM feature_dataset
        WHERE region_id = ? AND analysis_date = ?
        """,
        (region_id, analysis_date),
    )
    if row:
        return _apply_ground_layer_adjustment(conn, row, region_id=region_id)

    past_sinkhole_count = query_one(
        conn, "SELECT COUNT(*) AS c FROM sinkhole_history WHERE region_id = ?", (region_id,)
    )["c"]
    gpr_detected_count = query_one(
        conn,
        "SELECT COALESCE(SUM(cavity_count), 0) AS s FROM gpr_inspection WHERE region_id = ?",
        (region_id,),
    )["s"]
    geophysics_signal = query_one(
        conn,
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN survey_method LIKE '%GPR%' OR survey_method LIKE '%레이다%' OR survey_method LIKE '%레이더%' THEN 0.25
                ELSE 0.10
            END
        ), 0) AS s
        FROM molit_aggregate_geophysics
        WHERE region_id = ?
        """,
        (region_id,),
    )["s"]
    gpr_detected_count = float(gpr_detected_count or 0) + min(2.0, float(geophysics_signal or 0))
    facility_aging_score = query_one(
        conn, "SELECT COALESCE(AVG(aging_score), 0) AS a FROM facility_safety WHERE region_id = ?", (region_id,)
    )["a"]

    # 새 데이터 반영: 점검 결과로 노후도 조정
    inspection_risk_avg = query_one(
        conn, "SELECT COALESCE(AVG(risk_score), 0) AS r FROM facility_inspection WHERE region_id = ?", (region_id,)
    )["r"]
    facility_aging_score = max(float(facility_aging_score), _facility_status_aging_score(conn, region_id))
    facility_aging_score += inspection_risk_avg * 0.1  # 점검 위험도 10% 가산

    rainfall_7d = query_one(
        conn,
        """
        SELECT COALESCE(SUM(rainfall), 0) AS s
        FROM weather_data
        WHERE region_id = ?
          AND record_date >= date(?, '-7 day')
          AND record_date <= date(?)
        """,
        (region_id, analysis_date, analysis_date),
    )["s"]
    rainfall_score = min(10.0, float(rainfall_7d) / 10.0)  # 100mm/7d -> 10점

    groundwater_var_7d = query_one(
        conn,
        """
        SELECT COALESCE(AVG(variation), 0) AS a
        FROM groundwater_data
        WHERE region_id = ?
          AND record_date >= date(?, '-7 day')
          AND record_date <= date(?)
        """,
        (region_id, analysis_date, analysis_date),
    )["a"]
    groundwater_score = min(8.0, float(groundwater_var_7d) * 4.0)  # variation 0~2 가정
    if groundwater_score <= 0:
        groundwater_score = _molit_groundwater_score_for_region(conn, region_id)

    env = query_one(
        conn,
        """
        SELECT COALESCE(building_density, 0) AS bd, COALESCE(road_density, 0) AS rd
        FROM environment_features
        WHERE region_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (region_id,),
    ) or {"bd": 0.0, "rd": 0.0}
    environment_score = min(6.0, (float(env["bd"]) + float(env["rd"])) * 3.0)  # 0~2 -> 0~6

    construction_scale = query_one(
        conn,
        """
        SELECT COALESCE(MAX(scale_score), 0) AS m
        FROM construction_events
        WHERE region_id = ?
        """,
        (region_id,),
    )["m"]
    construction_score = min(20.0, float(construction_scale))

    conn.execute(
        """
        INSERT OR REPLACE INTO feature_dataset(
            region_id, analysis_date, past_sinkhole_count, gpr_detected_count, facility_aging_score,
            rainfall_score, groundwater_score, environment_score, construction_score
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            analysis_date,
            int(past_sinkhole_count),
            int(gpr_detected_count),
            float(facility_aging_score),
            float(rainfall_score),
            float(groundwater_score),
            float(environment_score),
            float(construction_score),
        ),
    )

    stored = query_one(
        conn,
        "SELECT * FROM feature_dataset WHERE region_id = ? AND analysis_date = ?",
        (region_id, analysis_date),
    )
    return _apply_ground_layer_adjustment(conn, stored, region_id=region_id)


def load_or_build_road_feature_row(conn: sqlite3.Connection, road_id: int, analysis_date: str) -> dict:
    row = query_one(
        conn,
        "SELECT * FROM road_feature_dataset WHERE road_id = ? AND analysis_date = ?",
        (road_id, analysis_date),
    )
    if row:
        return _apply_ground_layer_adjustment(conn, row, road_id=road_id)

    past_sinkhole_count = query_one(
        conn, "SELECT COUNT(*) AS c FROM road_sinkhole_history WHERE road_id = ?", (road_id,)
    )["c"]
    gpr_detected_count = query_one(
        conn,
        "SELECT COALESCE(SUM(cavity_count), 0) AS s FROM road_gpr_inspection WHERE road_id = ?",
        (road_id,),
    )["s"]
    facility_aging_score = query_one(
        conn,
        "SELECT COALESCE(AVG(aging_score), 0) AS a FROM road_facility_safety WHERE road_id = ?",
        (road_id,),
    )["a"]

    inspection_risk_avg = query_one(
        conn,
        "SELECT COALESCE(AVG(risk_score), 0) AS r FROM facility_inspection WHERE region_id = (SELECT region_id FROM road_segments WHERE road_id = ?)",
        (road_id,),
    )["r"]
    parent_region_id = _road_region_id(conn, road_id)
    if parent_region_id is not None:
        facility_aging_score = max(float(facility_aging_score), _facility_status_aging_score(conn, parent_region_id))
    facility_aging_score += inspection_risk_avg * 0.1

    rainfall_7d = query_one(
        conn,
        """
        SELECT COALESCE(SUM(rainfall), 0) AS s
        FROM weather_data
        WHERE region_id = (SELECT region_id FROM road_segments WHERE road_id = ?)
          AND record_date >= date(?, '-7 day')
          AND record_date <= date(?)
        """,
        (road_id, analysis_date, analysis_date),
    )["s"]
    rainfall_score = min(10.0, float(rainfall_7d) / 10.0)

    groundwater_var_7d = query_one(
        conn,
        """
        SELECT COALESCE(AVG(variation), 0) AS a
        FROM groundwater_data
        WHERE region_id = (SELECT region_id FROM road_segments WHERE road_id = ?)
          AND record_date >= date(?, '-7 day')
          AND record_date <= date(?)
        """,
        (road_id, analysis_date, analysis_date),
    )["a"]
    groundwater_score = min(8.0, float(groundwater_var_7d) * 4.0)
    if groundwater_score <= 0:
        groundwater_score = _molit_groundwater_score_for_road(conn, road_id)

    env = query_one(
        conn,
        """
        SELECT COALESCE(building_density, 0) AS bd,
               COALESCE(road_density, 0) AS rd,
               COALESCE(drainage_quality, 0) AS dq,
               COALESCE(slope_grade, 0) AS sg
        FROM road_environment_features
        WHERE road_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (road_id,),
    ) or {"bd": 0.0, "rd": 0.0, "dq": 0.0, "sg": 0.0}
    environment_score = min(10.0, (float(env["bd"]) + float(env["rd"]) + float(env["dq"]) + float(env["sg"])) * 2.0)

    construction_scale = query_one(
        conn,
        "SELECT COALESCE(MAX(scale_score), 0) AS m FROM road_construction_events WHERE road_id = ?",
        (road_id,),
    )["m"]
    construction_score = min(20.0, float(construction_scale))

    conn.execute(
        """
        INSERT OR REPLACE INTO road_feature_dataset(
            road_id, analysis_date, past_sinkhole_count, gpr_detected_count, facility_aging_score,
            rainfall_score, groundwater_score, environment_score, construction_score
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            road_id,
            analysis_date,
            int(past_sinkhole_count),
            int(gpr_detected_count),
            float(facility_aging_score),
            float(rainfall_score),
            float(groundwater_score),
            float(environment_score),
            float(construction_score),
        ),
    )

    stored = query_one(
        conn,
        "SELECT * FROM road_feature_dataset WHERE road_id = ? AND analysis_date = ?",
        (road_id, analysis_date),
    )
    return _apply_ground_layer_adjustment(conn, stored, road_id=road_id)
