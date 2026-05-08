from __future__ import annotations

from fastapi import APIRouter, Depends
import sqlite3

from app.db.core import query_all
from app.main_deps import get_db
from app.models.schemas import CompareRegionsRequest
from app.services.features import load_or_build_feature_row, resolve_analysis_date
from app.utils.response import ok


router = APIRouter()


@router.post("/api/compare-regions")
def compare_regions(req: CompareRegionsRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    analysis_date = resolve_analysis_date(req.analysis_date, req.client_local_datetime)
    out = []
    for region_id in req.region_ids:
        region = query_all(
            conn,
            "SELECT region_id, region_name, latitude, longitude FROM regions WHERE region_id = ?",
            (region_id,),
        )
        if not region:
            continue
        features = load_or_build_feature_row(conn, region_id, analysis_date)
        out.append({"region": region[0], "features": features})
    return ok(out)
