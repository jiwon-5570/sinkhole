from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from statistics import mean, pstdev
from typing import Any

import requests

from app.config.settings import settings
from app.services.addressing import nearest_road_address
from app.services.risk_scoring import RiskBreakdown, clamp, risk_level


USER_AGENT = "sinkhole-demo/0.1"
COORDINATE_PAIR_RE = re.compile(r"(^|[^\d.-])-?\d{1,3}(?:\.\d+)?\s*,\s*-?\d{1,3}(?:\.\d+)?($|[^\d.])")


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


def _coordinate_environment_score(latitude: float, longitude: float) -> float:
    lat_component = abs(latitude - round(latitude)) * 10
    lon_component = abs(longitude - round(longitude)) * 10
    return clamp((lat_component + lon_component) / 3, 0, 6)


def build_commercial_analysis(location_name: str | None, latitude: float | None, longitude: float | None) -> dict[str, Any]:
    location = _resolve_location(location_name, latitude, longitude)
    weather = _fetch_weather(location.latitude, location.longitude)

    precipitation = weather["precipitation"]
    rainfall_sum = sum(precipitation)
    rainfall_score = clamp(rainfall_sum / 8.0, 0, 10)
    rainfall_volatility = pstdev(precipitation) if len(precipitation) > 1 else 0.0
    # 실제 원본 데이터가 없는 항목은 임의 기본점수를 넣지 않는다.
    groundwater_score = 0.0
    facility_score = 0.0
    environment_score = 0.0
    past_sinkhole_score = 0.0
    gpr_score = 0.0
    construction_score = 0.0

    breakdown = RiskBreakdown(
        past_sinkhole=past_sinkhole_score,
        gpr=gpr_score,
        facility=facility_score,
        rainfall=rainfall_score,
        groundwater=groundwater_score,
        environment=environment_score,
        construction=construction_score,
    )
    score = clamp(breakdown.total)
    level = risk_level(score)
    location_payload = asdict(location)
    location_payload["road_address"] = location.location_name

    return {
        "mode": "commercial",
        "location": location_payload,
        "analysis": {
            "total_risk_score": round(score, 2),
            "risk_level": level,
            "priority_rank": None,
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
            "past_sinkhole_count": 0,
            "gpr_detected_count": 0,
            "facility_aging_score": 0.0,
            "rainfall_score": rainfall_score,
            "groundwater_score": 0.0,
            "environment_score": 0.0,
            "construction_score": 0.0,
        },
        "note": "실시간 위치 분석은 현재 연동 가능한 실제 기상 데이터만 반영합니다. 과거 사고, GPR, 시설물, 지하수, 공사 데이터는 원본 데이터가 없으면 0점으로 처리합니다.",
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
