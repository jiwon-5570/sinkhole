from __future__ import annotations

from datetime import date, datetime
import sqlite3

from app.db.core import query_one


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
        return row

    past_sinkhole_count = query_one(
        conn, "SELECT COUNT(*) AS c FROM sinkhole_history WHERE region_id = ?", (region_id,)
    )["c"]
    gpr_detected_count = query_one(
        conn,
        "SELECT COALESCE(SUM(cavity_count), 0) AS s FROM gpr_inspection WHERE region_id = ?",
        (region_id,),
    )["s"]
    facility_aging_score = query_one(
        conn, "SELECT COALESCE(AVG(aging_score), 0) AS a FROM facility_safety WHERE region_id = ?", (region_id,)
    )["a"]

    # 새 데이터 반영: 점검 결과로 노후도 조정
    inspection_risk_avg = query_one(
        conn, "SELECT COALESCE(AVG(risk_score), 0) AS r FROM facility_inspection WHERE region_id = ?", (region_id,)
    )["r"]
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

    return query_one(
        conn,
        "SELECT * FROM feature_dataset WHERE region_id = ? AND analysis_date = ?",
        (region_id, analysis_date),
    )


def load_or_build_road_feature_row(conn: sqlite3.Connection, road_id: int, analysis_date: str) -> dict:
    row = query_one(
        conn,
        "SELECT * FROM road_feature_dataset WHERE road_id = ? AND analysis_date = ?",
        (road_id, analysis_date),
    )
    if row:
        return row

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

    return query_one(
        conn,
        "SELECT * FROM road_feature_dataset WHERE road_id = ? AND analysis_date = ?",
        (road_id, analysis_date),
    )
