from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.db.core import query_all, query_one
from app.main_deps import get_db
from app.services.addressing import region_road_address, road_road_address
from app.models.schemas import AnalyzeRiskRequest, AnalyzeRoadRiskRequest
from app.services.features import (
    format_client_clock_label,
    load_or_build_feature_row,
    load_or_build_road_feature_row,
    resolve_analysis_date,
    today_str,
)
from app.services.reasoning import build_reason_cards, load_region_reason_context, load_road_reason_context
from app.services.risk_scoring import risk_level, score_rule_based
from app.utils.response import fail, ok


router = APIRouter()


def _recompute_priority(conn: sqlite3.Connection, analysis_date: str) -> None:
    rows = query_all(
        conn,
        """
        SELECT id, total_risk_score
        FROM risk_analysis_result
        WHERE analysis_date = ?
        ORDER BY total_risk_score DESC, id ASC
        """,
        (analysis_date,),
    )
    for idx, row in enumerate(rows, start=1):
        conn.execute("UPDATE risk_analysis_result SET priority_rank = ? WHERE id = ?", (idx, row["id"]))


def analyze_region(conn: sqlite3.Connection, region_id: int, analysis_date: str | None = None) -> dict | None:
    analysis_date = analysis_date or today_str()

    region = query_one(conn, "SELECT * FROM regions WHERE region_id = ?", (region_id,))
    if not region:
        return None

    features = load_or_build_feature_row(conn, region_id, analysis_date)
    score, breakdown = score_rule_based(features)
    level = risk_level(score)

    existing = query_one(
        conn,
        """
        SELECT id
        FROM risk_analysis_result
        WHERE region_id = ? AND analysis_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (region_id, analysis_date),
    )
    if existing:
        conn.execute(
            """
            UPDATE risk_analysis_result
            SET total_risk_score = ?, risk_level = ?
            WHERE id = ?
            """,
            (float(score), level, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO risk_analysis_result(region_id, analysis_date, total_risk_score, risk_level, priority_rank)
            VALUES(?, ?, ?, ?, NULL)
            """,
            (region_id, analysis_date, float(score), level),
        )

    _recompute_priority(conn, analysis_date)
    result = query_one(
        conn,
        """
        SELECT id, region_id, analysis_date, total_risk_score, risk_level, priority_rank
        FROM risk_analysis_result
        WHERE region_id = ? AND analysis_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (region_id, analysis_date),
    )

    feature_data = {k: features[k] for k in features.keys() if k not in {"region_id", "analysis_date"}}
    breakdown_data = {
        "past_sinkhole": breakdown.past_sinkhole,
        "gpr": breakdown.gpr,
        "facility": breakdown.facility,
        "rainfall": breakdown.rainfall,
        "groundwater": breakdown.groundwater,
        "environment": breakdown.environment,
        "construction": breakdown.construction,
        "total": breakdown.total,
    }
    cause_rows, trend_rows = load_region_reason_context(conn, region_id)

    return {
        "region": {
            "region_id": region["region_id"],
            "region_name": region["region_name"],
            "latitude": region["latitude"],
            "longitude": region["longitude"],
            "sido": region["sido"],
            "sigungu": region["sigungu"],
            "road_address": region_road_address(region),
        },
        "analysis": result,
        "features": feature_data,
        "breakdown": breakdown_data,
        "reason_cards": build_reason_cards(
            str(region["region_name"]),
            result,
            breakdown_data,
            feature_data,
            cause_rows=cause_rows,
            trend_rows=trend_rows,
        ),
    }


def analyze_road(conn: sqlite3.Connection, road_id: int, analysis_date: str | None = None) -> dict | None:
    analysis_date = analysis_date or today_str()

    road = query_one(conn, "SELECT * FROM road_segments WHERE road_id = ?", (road_id,))
    if not road:
        return None

    features = load_or_build_road_feature_row(conn, road_id, analysis_date)
    score, breakdown = score_rule_based(features)
    level = risk_level(score)

    existing = query_one(
        conn,
        """
        SELECT id
        FROM road_risk_analysis_result
        WHERE road_id = ? AND analysis_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (road_id, analysis_date),
    )
    if existing:
        conn.execute(
            """
            UPDATE road_risk_analysis_result
            SET total_risk_score = ?, risk_level = ?
            WHERE id = ?
            """,
            (float(score), level, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO road_risk_analysis_result(road_id, analysis_date, total_risk_score, risk_level, priority_rank)
            VALUES(?, ?, ?, ?, NULL)
            """,
            (road_id, analysis_date, float(score), level),
        )

    rows = query_all(
        conn,
        """
        SELECT id, total_risk_score
        FROM road_risk_analysis_result
        WHERE analysis_date = ?
        ORDER BY total_risk_score DESC, id ASC
        """,
        (analysis_date,),
    )
    for idx, row in enumerate(rows, start=1):
        conn.execute("UPDATE road_risk_analysis_result SET priority_rank = ? WHERE id = ?", (idx, row["id"]))

    result = query_one(
        conn,
        """
        SELECT id, road_id, analysis_date, total_risk_score, risk_level, priority_rank
        FROM road_risk_analysis_result
        WHERE road_id = ? AND analysis_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (road_id, analysis_date),
    )

    feature_data = {k: features[k] for k in features.keys() if k not in {"road_id", "analysis_date"}}
    breakdown_data = {
        "past_sinkhole": breakdown.past_sinkhole,
        "gpr": breakdown.gpr,
        "facility": breakdown.facility,
        "rainfall": breakdown.rainfall,
        "groundwater": breakdown.groundwater,
        "environment": breakdown.environment,
        "construction": breakdown.construction,
        "total": breakdown.total,
    }
    cause_rows, trend_rows = load_road_reason_context(conn, road_id)

    return {
        "road": {
            "road_id": road["road_id"],
            "road_name": road["road_name"],
            "road_type": road["road_type"],
            "center_lat": road["center_lat"],
            "center_lon": road["center_lon"],
            "region_id": road["region_id"],
            "road_address": road_road_address(road),
        },
        "analysis": result,
        "features": feature_data,
        "breakdown": breakdown_data,
        "reason_cards": build_reason_cards(
            str(road["road_name"]),
            result,
            breakdown_data,
            feature_data,
            cause_rows=cause_rows,
            trend_rows=trend_rows,
        ),
    }


@router.post("/api/analyze-risk")
def analyze_risk(req: AnalyzeRiskRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    analysis_date = resolve_analysis_date(req.analysis_date, req.client_local_datetime)
    result = analyze_region(conn, req.region_id, analysis_date)
    if not result:
        return fail("데이터를 찾을 수 없습니다.", "NOT_FOUND")
    client_clock_label = format_client_clock_label(
        client_local_datetime=req.client_local_datetime,
        client_timezone=req.client_timezone,
        client_utc_offset_minutes=req.client_utc_offset_minutes,
    )
    if client_clock_label:
        result["analysis"]["client_local_time"] = client_clock_label
    return ok(result)


@router.post("/api/analyze-road-risk")
def analyze_road_risk(req: AnalyzeRoadRiskRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    analysis_date = resolve_analysis_date(req.analysis_date, req.client_local_datetime)
    result = analyze_road(conn, req.road_id, analysis_date)
    if not result:
        return fail("데이터를 찾을 수 없습니다.", "NOT_FOUND")
    client_clock_label = format_client_clock_label(
        client_local_datetime=req.client_local_datetime,
        client_timezone=req.client_timezone,
        client_utc_offset_minutes=req.client_utc_offset_minutes,
    )
    if client_clock_label:
        result["analysis"]["client_local_time"] = client_clock_label
    return ok(result)


@router.get("/api/analysis/{region_id}")
def get_latest_analysis(region_id: int, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = query_one(
        conn,
        """
        SELECT id, region_id, analysis_date, total_risk_score, risk_level, priority_rank
        FROM risk_analysis_result
        WHERE region_id = ?
        ORDER BY analysis_date DESC, id DESC
        LIMIT 1
        """,
        (region_id,),
    )
    if not row:
        return fail("분석 결과가 없습니다.", "NOT_FOUND")
    return ok(row)


@router.get("/api/top-risk-regions")
def top_risk_regions(top_n: int = 5, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = query_all(
        conn,
        """
        SELECT g.region_id, g.region_name, r.total_risk_score, r.risk_level, r.priority_rank, r.analysis_date
        FROM risk_analysis_result r
        JOIN regions g ON g.region_id = r.region_id
        WHERE r.analysis_date = (SELECT MAX(analysis_date) FROM risk_analysis_result)
        ORDER BY r.total_risk_score DESC
        LIMIT ?
        """,
        (top_n,),
    )
    return ok([{**row, "road_address": region_road_address(row)} for row in rows])


@router.get("/api/top-risk-roads")
def top_risk_roads(top_n: int = 5, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = query_all(
        conn,
        """
        SELECT rs.road_id, rs.region_id, rs.road_name, rs.center_lat, rs.center_lon,
               r.total_risk_score, r.risk_level, r.priority_rank, r.analysis_date
        FROM road_risk_analysis_result r
        JOIN road_segments rs ON rs.road_id = r.road_id
        WHERE r.analysis_date = (SELECT MAX(analysis_date) FROM road_risk_analysis_result)
        ORDER BY r.total_risk_score DESC
        LIMIT ?
        """,
        (top_n,),
    )
    return ok([{**row, "road_address": road_road_address(row)} for row in rows])
