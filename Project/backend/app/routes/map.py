from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import sqlite3
import requests

from app.config.settings import settings
from app.db.core import query_all
from app.main_deps import get_db
from app.services.addressing import nearest_road_address
from app.utils.response import ok


router = APIRouter()


@router.get("/api/geocode/reverse")
def reverse_geocode(lat: float = Query(...), lng: float = Query(...)) -> dict:
    fallback_address = nearest_road_address(lat, lng)

    if settings.google_maps_api_key:
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "latlng": f"{lat},{lng}",
                    "language": "ko",
                    "key": settings.google_maps_api_key,
                },
                timeout=settings.external_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "OK" and payload.get("results"):
                result = payload["results"][0]
                return ok({
                    "address": result.get("formatted_address") or fallback_address,
                    "latitude": lat,
                    "longitude": lng,
                    "source": "google",
                })
        except Exception:
            pass

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lng,
                "format": "jsonv2",
                "zoom": 18,
                "addressdetails": 1,
                "accept-language": "ko",
            },
            headers={"User-Agent": "sinkhole-demo/0.1"},
            timeout=settings.external_request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return ok({
            "address": payload.get("display_name") or fallback_address,
            "latitude": lat,
            "longitude": lng,
            "source": "nominatim",
        })
    except Exception:
        return ok({
            "address": fallback_address,
            "latitude": lat,
            "longitude": lng,
            "source": "coordinates",
        })


@router.get("/api/map/risk-layer")
def risk_layer(
    date: str | None = Query(default=None),
    layer_type: str | None = Query(default="total_risk"),
    risk_level: str | None = Query(default=None),
    sido: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    where = []
    params = []
    if date:
        where.append("r.analysis_date = ?")
        params.append(date)
    if risk_level:
        where.append("r.risk_level = ?")
        params.append(risk_level)
    if sido:
        where.append("g.sido = ?")
        params.append(sido)

    sql = """
    SELECT
        g.region_id,
        g.region_name,
        g.latitude,
        g.longitude,
        r.total_risk_score AS risk_score,
        r.risk_level
    FROM risk_analysis_result r
    JOIN regions g ON g.region_id = r.region_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.total_risk_score DESC"
    return ok(query_all(conn, sql, tuple(params)))


@router.get("/api/map/gpr-layer")
def gpr_layer(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    detected_only: bool | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    where = []
    params = []
    if date_from:
        where.append("i.inspection_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("i.inspection_date <= ?")
        params.append(date_to)
    if detected_only:
        where.append("i.cavity_detected = 1")

    sql = """
    SELECT
        i.id,
        i.region_id,
        i.inspection_date,
        CASE WHEN i.cavity_detected = 1 THEN 1 ELSE 0 END AS cavity_detected,
        i.cavity_count,
        g.latitude,
        g.longitude
    FROM gpr_inspection i
    JOIN regions g ON g.region_id = i.region_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY i.inspection_date DESC"
    return ok(query_all(conn, sql, tuple(params)))


@router.get("/api/map/hotspots")
def hotspots(
    top_n: int = Query(default=10, ge=1, le=200),
    risk_level: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    where = []
    params = []
    if risk_level:
        where.append("r.risk_level = ?")
        params.append(risk_level)

    sql = """
    SELECT
        g.region_id,
        g.region_name,
        g.latitude,
        g.longitude,
        r.total_risk_score AS risk_score,
        r.risk_level,
        r.priority_rank
    FROM risk_analysis_result r
    JOIN regions g ON g.region_id = r.region_id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY r.total_risk_score DESC LIMIT ?"
    params.append(top_n)
    return ok(query_all(conn, sql, tuple(params)))
