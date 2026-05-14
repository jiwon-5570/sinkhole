from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from math import asin, cos, radians, sin, sqrt
from statistics import mean
from typing import Any

import requests

from app.config.settings import settings
from app.db.core import connect, query_all
from app.services.addressing import nearest_road_address
from app.services.risk_scoring import clamp, risk_level, score_rule_based


USER_AGENT = "sinkhole-demo/0.1"
COORDINATE_PAIR_RE = re.compile(r"(^|[^\d.-])-?\d{1,3}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?($|[^\d.])")
FULL_COVERAGE_RADIUS_M = 1500.0
MAX_PROXY_RADIUS_M = 8000.0


@dataclass(frozen=True)
class CommercialLocation:
    location_name: str
    latitude: float
    longitude: float
    source: str


def _looks_like_coordinate_label(value: str | None) -> bool:
    return bool(COORDINATE_PAIR_RE.search(str(value or "").strip()))


def _resolve_location(location_name: str | None, latitude: float | None, longitude: float | None) -> CommercialLocation:
    if latitude is not None and longitude is not None:
        name = location_name if location_name and not _looks_like_coordinate_label(location_name) else nearest_road_address(latitude, longitude)
        return CommercialLocation(location_name=name, latitude=latitude, longitude=longitude, source="manual")

    if not location_name:
        raise ValueError("실제 분석 모드에서는 위치명 또는 도로명 주소가 필요합니다.")

    # Try Google Geocoding first if API key is available
    if settings.google_maps_api_key:
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": location_name, "key": settings.google_maps_api_key},
                timeout=settings.external_request_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                lat = result["geometry"]["location"]["lat"]
                lng = result["geometry"]["location"]["lng"]
                name = result.get("formatted_address") or location_name
                return CommercialLocation(location_name=name, latitude=lat, longitude=lng, source="google")
        except Exception:
            pass  # Fall back to Nominatim

    # Fallback to Nominatim
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": location_name, "format": "jsonv2", "limit": 1, "countrycodes": "kr", "accept-language": "ko"},
        headers={"User-Agent": USER_AGENT},
        timeout=settings.external_request_timeout_seconds,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        raise ValueError("입력한 위치를 찾을 수 없습니다.")

    row = rows[0]
    return CommercialLocation(
        location_name=row.get("display_name") or location_name,
        latitude=float(row["lat"]),
        longitude=float(row["lon"]),
        source="nominatim",
    )


def _fetch_weather(latitude: float, longitude: float) -> dict[str, Any]:
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
            "forecast_days": 7,
            "timezone": "Asia/Seoul",
        },
        timeout=settings.external_request_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()

    daily = payload.get("daily") or {}
    precipitation = [float(value) for value in (daily.get("precipitation_sum") or [])]
    temp_max = [float(value) for value in (daily.get("temperature_2m_max") or [])]
    temp_min = [float(value) for value in (daily.get("temperature_2m_min") or [])]
    avg_temp = mean([(hi + lo) / 2 for hi, lo in zip(temp_max, temp_min, strict=False)]) if temp_max and temp_min else 18.0

    return {
        "precipitation": precipitation,
        "temperature_avg": round(avg_temp, 1),
        "elevation": float(payload.get("elevation") or 0.0),
    }


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_m = 6_371_000.0
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    return radius_m * 2 * asin(sqrt(a))


def _nearest_analyzed_region(latitude: float, longitude: float) -> dict[str, Any] | None:
    conn = connect(settings.db_path)
    try:
        rows = query_all(
            conn,
            """
            SELECT
                r.region_id,
                r.region_name,
                r.sido,
                r.sigungu,
                r.latitude,
                r.longitude,
                a.analysis_date,
                a.total_risk_score,
                a.risk_level,
                a.priority_rank,
                f.past_sinkhole_count,
                f.gpr_detected_count,
                f.facility_aging_score,
                f.rainfall_score,
                f.groundwater_score,
                f.environment_score,
                f.construction_score
            FROM regions r
            JOIN risk_analysis_result a
              ON a.region_id = r.region_id
             AND a.analysis_date = (SELECT MAX(analysis_date) FROM risk_analysis_result)
            LEFT JOIN feature_dataset f
              ON f.region_id = r.region_id
             AND f.analysis_date = a.analysis_date
            WHERE r.latitude IS NOT NULL
              AND r.longitude IS NOT NULL
            """,
        )
    finally:
        conn.close()

    nearest: dict[str, Any] | None = None
    nearest_distance = float("inf")
    for row in rows:
        distance = _distance_m(latitude, longitude, float(row["latitude"]), float(row["longitude"]))
        if distance < nearest_distance:
            nearest = dict(row)
            nearest["distance_m"] = distance
            nearest_distance = distance
    return nearest


def _coverage(distance_m: float | None) -> dict[str, Any]:
    if distance_m is None:
        return {
            "status": "insufficient",
            "label": "데이터 부족",
            "factor": 0.0,
            "message": "해당 좌표 주변에 비교할 수 있는 저장 분석 지점이 없습니다.",
        }
    if distance_m <= FULL_COVERAGE_RADIUS_M:
        return {
            "status": "near",
            "label": "근접 분석",
            "factor": 1.0,
            "message": "가까운 저장 분석 지점의 실제 공공데이터 기반 점수를 참조했습니다.",
        }
    if distance_m <= MAX_PROXY_RADIUS_M:
        span = MAX_PROXY_RADIUS_M - FULL_COVERAGE_RADIUS_M
        factor = 1.0 - ((distance_m - FULL_COVERAGE_RADIUS_M) / span) * 0.45
        return {
            "status": "proxy",
            "label": "근접 지점 보정",
            "factor": clamp(factor, 0.55, 1.0),
            "message": "선택 좌표 자체의 정밀 원천자료가 없어 가장 가까운 저장 분석 지점을 거리 보정해 추정했습니다.",
        }
    return {
        "status": "insufficient",
        "label": "데이터 부족",
        "factor": 0.0,
        "message": "선택 좌표가 저장 분석 지점에서 너무 멀어 강우 외 항목을 신뢰 있게 추정하지 않았습니다.",
    }


def build_commercial_analysis(location_name: str | None, latitude: float | None, longitude: float | None) -> dict[str, Any]:
    location = _resolve_location(location_name, latitude, longitude)
    weather = _fetch_weather(location.latitude, location.longitude)

    precipitation = weather["precipitation"]
    rainfall_sum = sum(precipitation)
    rainfall_score = clamp(rainfall_sum / 8.0, 0, 10)
    nearest_region = _nearest_analyzed_region(location.latitude, location.longitude)
    distance_m = float(nearest_region["distance_m"]) if nearest_region else None
    coverage = _coverage(distance_m)

    features = {
        "past_sinkhole_count": 0.0,
        "gpr_detected_count": 0.0,
        "facility_aging_score": 0.0,
        "rainfall_score": rainfall_score,
        "groundwater_score": 0.0,
        "environment_score": 0.0,
        "construction_score": 0.0,
    }
    priority_rank = None
    analysis_date = None
    reference_region = None

    if nearest_region and coverage["factor"] > 0:
        factor = float(coverage["factor"])
        features = {
            "past_sinkhole_count": float(nearest_region.get("past_sinkhole_count") or 0) * factor,
            "gpr_detected_count": float(nearest_region.get("gpr_detected_count") or 0) * factor,
            "facility_aging_score": float(nearest_region.get("facility_aging_score") or 0) * factor,
            "rainfall_score": rainfall_score,
            "groundwater_score": float(nearest_region.get("groundwater_score") or 0) * factor,
            "environment_score": float(nearest_region.get("environment_score") or 0) * factor,
            "construction_score": float(nearest_region.get("construction_score") or 0) * factor,
        }
        priority_rank = nearest_region.get("priority_rank") if coverage["status"] == "near" else None
        analysis_date = nearest_region.get("analysis_date")
        reference_region = {
            "region_id": nearest_region.get("region_id"),
            "region_name": nearest_region.get("region_name"),
            "sido": nearest_region.get("sido"),
            "sigungu": nearest_region.get("sigungu"),
            "latitude": nearest_region.get("latitude"),
            "longitude": nearest_region.get("longitude"),
            "distance_m": round(distance_m or 0.0, 1),
            "total_risk_score": round(float(nearest_region.get("total_risk_score") or 0.0), 2),
            "risk_level": nearest_region.get("risk_level"),
        }

    score, breakdown = score_rule_based(features)
    level = risk_level(score)
    location_payload = asdict(location)
    location_payload["road_address"] = location.location_name

    return {
        "mode": "commercial",
        "location": location_payload,
        "analysis": {
            "total_risk_score": round(score, 2),
            "risk_level": level,
            "priority_rank": priority_rank,
            "analysis_date": analysis_date,
        },
        "breakdown": {
            "past_sinkhole": breakdown.past_sinkhole,
            "gpr": breakdown.gpr,
            "facility": breakdown.facility,
            "rainfall": breakdown.rainfall,
            "groundwater": breakdown.groundwater,
            "environment": breakdown.environment,
            "construction": breakdown.construction,
            "total": breakdown.total,
        },
        "weather": {
            "rainfall_7d_total": round(rainfall_sum, 1),
            "rainfall_7d_daily": [round(value, 1) for value in precipitation],
            "temperature_avg": weather["temperature_avg"],
            "elevation": round(weather["elevation"], 1),
        },
        "features": {
            "past_sinkhole_count": features["past_sinkhole_count"],
            "gpr_detected_count": features["gpr_detected_count"],
            "facility_aging_score": features["facility_aging_score"],
            "rainfall_score": rainfall_score,
            "groundwater_score": features["groundwater_score"],
            "environment_score": features["environment_score"],
            "construction_score": features["construction_score"],
        },
        "data_coverage": {
            **coverage,
            "distance_m": round(distance_m, 1) if distance_m is not None else None,
            "reference_region": reference_region,
        },
        "note": (
            "선택 좌표 자체에 직접 매칭된 원천자료가 없을 때는 가까운 저장 분석 지점을 참조합니다. "
            "근접 지점이 없으면 강우 외 항목은 신뢰 있게 추정하지 않습니다."
        ),
    }


def build_commercial_report(analysis_payload: dict[str, Any]) -> str:
    location = analysis_payload["location"]
    analysis = analysis_payload["analysis"]
    weather = analysis_payload["weather"]
    breakdown = analysis_payload["breakdown"]
    client_local_time = analysis.get("client_local_time")

    lines = [
        f"[\uc704\uce58] {location['location_name']}",
        f"[\ub3c4\ub85c\uba85 \uc8fc\uc18c] {location['location_name']}",
        f"[\ubd84\uc11d \uc2dc\uac01(\ub85c\uceec)] {client_local_time or '-'}",
        f"[\uc704\ud5d8\ub3c4] {analysis['total_risk_score']} / 100 ({analysis['risk_level']})",
        "",
        "[\uc2e4\uc2dc\uac04 \ub370\uc774\ud130 \uc694\uc57d]",
        f"- \ucd5c\uadfc 7\uc77c \ub204\uc801 \uac15\uc218\ub7c9: {weather['rainfall_7d_total']} mm",
        f"- \ud3c9\uade0 \uae30\uc628: {weather['temperature_avg']} \u00b0C",
        f"- \ud574\ubc1c \uace0\ub3c4: {weather['elevation']} m",
        "",
        "[\uae30\uc5ec \uc694\uc778]",
        f"- \uae30\uc0c1 \uc601\ud5a5: {breakdown['rainfall']:.1f}\uc810",
        f"- \ubcc0\ub3d9\uc131/\uc9c0\ud558\uc218 \uc9c0\ud45c: {breakdown['groundwater']:.1f}\uc810",
        f"- \ud658\uacbd \uc9c0\ud45c: {breakdown['environment']:.1f}\uc810",
        "",
        "[\uc124\uba85]",
        "\uacf5\uac1c \uc704\uce58/\uae30\uc0c1 \ub370\uc774\ud130\ub97c \uae30\ubc18\uc73c\ub85c \uc989\uc2dc \ubd84\uc11d\ud55c \uacb0\uacfc\uc785\ub2c8\ub2e4.",
        "\ud604\uc7a5 \uc870\uc0ac, \uc9c0\ubc18 \uc815\ubc00\uac80\uc0ac, \uc2dc\uc124\ubb3c \ub3c4\uba74 \ub370\uc774\ud130\uac00 \uc5f0\uacc4\ub418\uba74 \ubcf4\ub2e4 \uc815\ubc00\ud55c \uc0c1\uc6a9 \ubd84\uc11d\uc73c\ub85c \ud655\uc7a5\ud560 \uc218 \uc788\uc2b5\ub2c8\ub2e4.",
    ]
    return "\n".join(lines)
