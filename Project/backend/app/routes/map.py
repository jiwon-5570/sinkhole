from __future__ import annotations

from fastapi import APIRouter, Depends, Query
import re
import sqlite3
import requests

from app.config.settings import settings
from app.db.core import query_all
from app.main_deps import get_db
from app.services.addressing import nearest_road_address, region_road_address
from app.utils.response import fail, ok


router = APIRouter()

GEOCODE_TIMEOUT_SECONDS = min(settings.external_request_timeout_seconds, 4.0)
LOCAL_PLACE_ALIASES = (
    {
        "keywords": ("강남역", "강남대로396", "강남대로 396"),
        "address": "서울특별시 강남구 강남대로 396 인근",
        "latitude": 37.497952,
        "longitude": 127.027619,
    },
    {
        "keywords": ("서울역", "한강대로405", "한강대로 405"),
        "address": "서울특별시 용산구 한강대로 405 인근",
        "latitude": 37.554648,
        "longitude": 126.972559,
    },
    {
        "keywords": ("송파대로167", "송파대로 167", "가든파이브"),
        "address": "서울특별시 송파구 송파대로 167 인근",
        "latitude": 37.47778953708737,
        "longitude": 127.1241653228494,
    },
)


def _normalize_address_text(value: str | None) -> str:
    text = str(value or "").strip().replace("인근", "")
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", text).lower()


def _address_tokens(value: str) -> list[str]:
    ignored = {"서울", "서울특별시", "수도권", "인근", "대한민국"}
    return [
        token
        for token in re.split(r"[\s,()·\-/]+", value.strip())
        if len(token) >= 2 and token not in ignored
    ]


def _local_forward_geocode(query: str, conn: sqlite3.Connection) -> dict | None:
    query_norm = _normalize_address_text(query)
    if not query_norm:
        return None

    for alias in LOCAL_PLACE_ALIASES:
        if any(_normalize_address_text(keyword) in query_norm for keyword in alias["keywords"]):
            return {
                "address": alias["address"],
                "latitude": float(alias["latitude"]),
                "longitude": float(alias["longitude"]),
                "source": "local_alias",
            }

    rows = query_all(
        conn,
        """
        SELECT region_id, region_name, latitude, longitude, sido, sigungu
        FROM regions
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """,
    )
    tokens = _address_tokens(query)
    best_row: dict | None = None
    best_score = 0

    for row in rows:
        address = region_road_address(row)
        candidates = [
            address,
            address.replace(" 인근", ""),
            str(row.get("region_name") or ""),
            " ".join(str(row.get(key) or "") for key in ("sido", "sigungu")).strip(),
        ]
        row_score = 0
        for candidate in candidates:
            candidate_norm = _normalize_address_text(candidate)
            if not candidate_norm:
                continue
            if query_norm == candidate_norm:
                row_score = max(row_score, 1000)
            elif query_norm in candidate_norm or candidate_norm in query_norm:
                row_score = max(row_score, 800 + min(len(query_norm), len(candidate_norm)))
            else:
                row_score = max(
                    row_score,
                    sum(20 for token in tokens if _normalize_address_text(token) in candidate_norm),
                )

        if row_score > best_score:
            best_score = row_score
            best_row = row

    if not best_row or best_score < 40:
        return None

    address = region_road_address(best_row)
    return {
        "address": address,
        "latitude": float(best_row["latitude"]),
        "longitude": float(best_row["longitude"]),
        "region_id": best_row.get("region_id"),
        "region_name": best_row.get("region_name"),
        "source": "local",
    }


@router.get("/api/geocode/search")
def forward_geocode(
    q: str = Query(..., min_length=2),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    query = q.strip()
    if not query:
        return fail("주소를 입력해 주세요.", "GEOCODE_EMPTY")

    local_result = _local_forward_geocode(query, conn)
    if local_result:
        return ok(local_result)

    if settings.google_maps_api_key:
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "address": query,
                    "language": "ko",
                    "region": "kr",
                    "components": "country:KR",
                    "bounds": "37.30,126.75|37.70,127.25",
                    "key": settings.google_maps_api_key,
                },
                timeout=GEOCODE_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") == "OK" and payload.get("results"):
                result = payload["results"][0]
                location = result.get("geometry", {}).get("location", {})
                latitude = float(location.get("lat"))
                longitude = float(location.get("lng"))
                return ok({
                    "address": result.get("formatted_address") or query,
                    "latitude": latitude,
                    "longitude": longitude,
                    "source": "google",
                })
        except Exception:
            pass

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 1,
                "countrycodes": "kr",
                "addressdetails": 1,
                "accept-language": "ko",
            },
            headers={"User-Agent": "sinkhole-demo/0.1"},
            timeout=GEOCODE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if payload:
            result = payload[0]
            return ok({
                "address": result.get("display_name") or query,
                "latitude": float(result["lat"]),
                "longitude": float(result["lon"]),
                "source": "nominatim",
            })
    except Exception:
        pass

    return fail("입력한 위치를 찾을 수 없습니다. 도로명 주소를 더 구체적으로 입력해 주세요.", "GEOCODE_NOT_FOUND")


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
