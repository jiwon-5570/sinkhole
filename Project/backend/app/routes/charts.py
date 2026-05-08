from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from app.db.core import query_all
from app.main_deps import get_db
from app.utils.response import ok


router = APIRouter()


@router.get("/api/charts/risk-distribution")
def risk_distribution(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = query_all(
        conn,
        """
        SELECT risk_level, COUNT(*) AS count
        FROM risk_analysis_result
        WHERE analysis_date = (SELECT MAX(analysis_date) FROM risk_analysis_result)
        GROUP BY risk_level
        ORDER BY count DESC
        """,
    )
    return ok(rows)


@router.get("/api/charts/risk-trend")
def risk_trend(region_id: int = Query(...), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = query_all(
        conn,
        """
        SELECT analysis_date, total_risk_score, risk_level
        FROM risk_analysis_result
        WHERE region_id = ?
        ORDER BY analysis_date ASC, id ASC
        LIMIT 365
        """,
        (region_id,),
    )
    return ok(rows)


@router.get("/api/charts/factor-importance")
def factor_importance(region_id: int = Query(...), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    row = query_all(
        conn,
        """
        SELECT
            past_sinkhole_count,
            gpr_detected_count,
            facility_aging_score,
            rainfall_score,
            groundwater_score,
            environment_score,
            construction_score
        FROM feature_dataset
        WHERE region_id = ?
        ORDER BY analysis_date DESC
        LIMIT 1
        """,
        (region_id,),
    )
    if not row:
        return ok([])

    f = row[0]
    items = [
        {"name": "과거 사고", "value": float(f["past_sinkhole_count"] or 0)},
        {"name": "GPR/탐사", "value": float(f["gpr_detected_count"] or 0)},
        {"name": "시설물", "value": float(f["facility_aging_score"] or 0)},
        {"name": "강우", "value": float(f["rainfall_score"] or 0)},
        {"name": "지하수", "value": float(f["groundwater_score"] or 0)},
        {"name": "환경", "value": float(f["environment_score"] or 0)},
        {"name": "공사(보조)", "value": float(f["construction_score"] or 0)},
    ]
    return ok(items)


@router.get("/api/charts/top-priority")
def top_priority(top_n: int = 10, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = query_all(
        conn,
        """
        SELECT g.region_id, g.region_name, r.total_risk_score, r.risk_level, r.priority_rank
        FROM risk_analysis_result r
        JOIN regions g ON g.region_id = r.region_id
        WHERE r.analysis_date = (SELECT MAX(analysis_date) FROM risk_analysis_result)
        ORDER BY r.priority_rank ASC
        LIMIT ?
        """,
        (top_n,),
    )
    return ok(rows)


@router.get("/api/charts/sinkhole-cause-distribution")
def sinkhole_cause_distribution(region_id: int = Query(...), conn: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = query_all(
        conn,
        """
        SELECT
            COALESCE(cause_type, '미상') AS cause_type,
            COUNT(*) AS count,
            ROUND(COALESCE(AVG(damage_scale), 0), 2) AS avg_damage_scale
        FROM sinkhole_history
        WHERE region_id = ?
        GROUP BY COALESCE(cause_type, '미상')
        ORDER BY count DESC, avg_damage_scale DESC, cause_type ASC
        LIMIT 10
        """,
        (region_id,),
    )
    return ok(rows)


@router.get("/api/charts/sinkhole-occurrence-trend")
def sinkhole_occurrence_trend(
    region_id: int = Query(...),
    months: int = Query(24, ge=3, le=60),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    rows = query_all(
        conn,
        """
        SELECT
            strftime('%Y-%m', occurrence_date) AS month,
            COUNT(*) AS count,
            ROUND(COALESCE(AVG(damage_scale), 0), 2) AS avg_damage_scale
        FROM sinkhole_history
        WHERE region_id = ?
          AND occurrence_date IS NOT NULL
          AND date(occurrence_date) >= date('now', ?)
        GROUP BY strftime('%Y-%m', occurrence_date)
        ORDER BY month ASC
        """,
        (region_id, f"-{months} months"),
    )
    return ok(rows)
