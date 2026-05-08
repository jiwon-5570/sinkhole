from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.db.core import query_all
from app.main_deps import get_db
from app.models.schemas import WhatIfRequest
from app.services.simulation_engine import normalize_scenario, rank_simulation_results, simulate_region
from app.utils.response import ok


router = APIRouter()


@router.post("/api/simulate-risk")
def simulate_risk(req: WhatIfRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    scenario = normalize_scenario(req)
    params: list[object] = []
    target_filter = ""
    if req.target_region_id is not None:
        target_filter = " AND f.region_id = ?"
        params.append(req.target_region_id)

    rows = query_all(
        conn,
        f"""
        WITH latest_feature_date AS (
            SELECT MAX(analysis_date) AS analysis_date
            FROM feature_dataset
        )
        SELECT
            f.region_id,
            g.region_name,
            f.analysis_date,
            f.past_sinkhole_count,
            f.gpr_detected_count,
            f.facility_aging_score,
            f.rainfall_score,
            f.groundwater_score,
            f.environment_score,
            f.construction_score,
            r.total_risk_score AS original_score,
            r.risk_level AS original_level,
            r.priority_rank
        FROM feature_dataset f
        JOIN latest_feature_date l ON l.analysis_date = f.analysis_date
        JOIN regions g ON g.region_id = f.region_id
        JOIN risk_analysis_result r
          ON r.region_id = f.region_id
         AND r.analysis_date = f.analysis_date
        WHERE 1 = 1{target_filter}
        ORDER BY g.region_id
        """,
        tuple(params),
    )

    data = rank_simulation_results([simulate_region(row, scenario) for row in rows])
    return ok(
        {
            "scenario": scenario.as_dict(),
            "count": len(data),
            "results": data,
        }
    )
