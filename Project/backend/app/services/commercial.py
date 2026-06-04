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
from app.services.ai_evidence import build_evidence_context
from app.services.reasoning import FACTOR_FEATURES, FACTOR_LABELS
from app.services.risk_scoring import FACTOR_MAX_SCORES, clamp, risk_level, score_rule_based


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
            JOIN (
                SELECT *
                FROM (
                    SELECT
                        r.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY r.region_id
                            ORDER BY r.analysis_date DESC, r.id DESC
                        ) AS latest_rank
                    FROM risk_analysis_result r
                )
                WHERE latest_rank = 1
            ) a
              ON a.region_id = r.region_id
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


def _compact_text(value: Any, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return "세부 근거 없음"
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _commercial_evidence_context(analysis_payload: dict[str, Any]) -> dict[str, Any]:
    coverage = analysis_payload.get("data_coverage") or {}
    reference = coverage.get("reference_region") or {}
    try:
        region_id = int(reference.get("region_id") or 0)
    except (TypeError, ValueError):
        region_id = 0
    if region_id <= 0:
        return {}

    location = analysis_payload.get("location") or {}
    target = {
        **reference,
        "region_id": region_id,
        # 직접 선택 좌표와 가장 가까운 시추공/지하수 근거를 설명할 수 있게 좌표는 선택 위치를 우선 사용합니다.
        "latitude": location.get("latitude") or reference.get("latitude"),
        "longitude": location.get("longitude") or reference.get("longitude"),
    }
    conn = connect(settings.db_path)
    try:
        return build_evidence_context(conn, target, analysis_payload, analysis_payload.get("analysis", {}).get("analysis_date"))
    finally:
        conn.close()


def _contains_pipe_keyword(row: dict[str, Any]) -> bool:
    text = " ".join(str(row.get(key) or "") for key in ("facility_name", "facility_type", "description", "accident_type"))
    return any(keyword in text for keyword in ("하수", "상수", "관로", "관거", "맨홀", "매설", "배수", "우수"))


def _first_value(row: dict[str, Any], *keys: str, default: str = "-") -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _facility_age_text(row: dict[str, Any], fmt) -> str:
    for key in ("age_years", "facility_age", "elapsed_years", "building_age", "years_old", "pipe_age_years"):
        value = row.get(key)
        if value not in (None, ""):
            return f"{fmt(value, 0)}년 경과"
    aging_ratio = row.get("aging_ratio")
    aging_count = row.get("aging_count")
    total_count = row.get("total_count")
    if aging_ratio not in (None, "") or aging_count not in (None, "") or total_count not in (None, ""):
        return f"노후비율 {fmt(aging_ratio)}, 노후 {fmt(aging_count, 0)}/{fmt(total_count, 0)}개"
    return "연식/노후 수량 세부 필드 없음"


def _management_evidence_text(factor_key: str, evidence: dict[str, Any], fmt) -> str:
    rows = evidence.get("rows")
    if factor_key == "facility" and isinstance(rows, dict):
        status_rows = rows.get("facility_status") or []
        inspection_rows = rows.get("facility_inspection") or []
        accident_rows = rows.get("facility_accidents") or []
        pipe_row = next((row for row in [*status_rows, *inspection_rows, *accident_rows] if _contains_pipe_keyword(row)), None)
        if pipe_row:
            facility_name = _first_value(pipe_row, "facility_name", "facility_type", default="관로/지하시설물")
            facility_type = _first_value(pipe_row, "facility_type", "accident_type")
            address = _first_value(pipe_row, "address", "road_address", "location")
            age_text = _facility_age_text(pipe_row, fmt)
            inspection_date = _first_value(pipe_row, "inspection_date", "occurrence_date", default="점검일 미상")
            risk_score = fmt(pipe_row.get("risk_score")) if pipe_row.get("risk_score") not in (None, "") else "-"
            return (
                f"{address} 인근에 {facility_name}({facility_type}) 원자료가 있으며 {age_text}로 확인됩니다. "
                f"점검/사고 기준일은 {inspection_date}, 점검 위험지표는 {risk_score}입니다. "
                "따라서 해당 시설의 누수·균열·접합부 이탈 여부를 우선 확인하고 결함이 확인되면 보수 대상에 올립니다."
            )
        if status_rows:
            row = status_rows[0]
            facility_name = _first_value(row, "facility_name", "facility_type", default="시설물")
            facility_type = _first_value(row, "facility_type")
            address = _first_value(row, "address", "road_address", "location")
            return (
                f"{address}의 {facility_name}({facility_type}) 원자료에서 {_facility_age_text(row, fmt)}가 확인됩니다. "
                "노후 시설 비율이 점수에 반영되므로 시설물 대장과 현장 상태를 대조해 보수 우선순위를 정합니다."
            )
        if inspection_rows:
            row = inspection_rows[0]
            facility_name = _first_value(row, "facility_name", "facility_type", default="시설물")
            facility_type = _first_value(row, "facility_type")
            address = _first_value(row, "address", "road_address", "location")
            return (
                f"{address}의 {facility_name}({facility_type}) 점검 행에서 점검일 {row.get('inspection_date') or '-'}, "
                f"판정 {row.get('diagnosis_result') or '-'}, 위험지표 {fmt(row.get('risk_score'))}가 확인됩니다. "
                "판정 결과가 낮거나 위험지표가 높으면 정밀점검과 보수 계획을 먼저 배정합니다."
            )
        if accident_rows:
            row = accident_rows[0]
            facility_name = _first_value(row, "facility_name", "facility_type", default="시설물")
            address = _first_value(row, "address", "road_address", "location")
            return (
                f"{row.get('occurrence_date') or '-'} {address}의 {facility_name} 사고 행이 있으며 "
                f"유형은 {row.get('accident_type') or '-'}, 위험지표는 {fmt(row.get('risk_score'))}입니다. "
                "동일 시설 또는 인접 관로의 반복 손상 가능성을 확인합니다."
            )

    if factor_key == "past_sinkhole" and isinstance(rows, list) and rows:
        row = rows[0]
        return (
            f"{row.get('occurrence_date') or '-'} {row.get('address') or '주소 미상'}에서 "
            f"원인 {row.get('cause_type') or '미상'}, 규모 {fmt(row.get('damage_scale'))}, "
            f"출처 {row.get('source_name') or '-'}의 과거 지반침하 이력이 확인됩니다. "
            "같은 생활권의 반복 이력은 포장 하부 공동, 되메우기 불량, 관로 누수 가능성을 우선 확인해야 하는 근거입니다."
        )

    if factor_key == "gpr" and isinstance(rows, dict):
        direct_rows = rows.get("gpr_inspection") or []
        geophysics_rows = rows.get("molit_aggregate_geophysics") or []
        if direct_rows:
            row = direct_rows[0]
            return (
                f"{row.get('inspection_date') or '-'} {row.get('address') or '주소 미상'} GPR 점검에서 "
                f"공동 {fmt(row.get('cavity_count'), 0)}건, 추정심도 {fmt(row.get('depth_estimate'))}m가 기록됐습니다. "
                "공동 위치와 포장 상태를 재확인한 뒤 공동 충전 또는 굴착 보수 여부를 결정합니다."
            )
        if geophysics_rows:
            row = geophysics_rows[0]
            return (
                f"{row.get('survey_point_name') or row.get('address') or '위치명 미상'}에서 "
                f"{row.get('survey_method') or '-'} 방식 물리탐사, 연장 {fmt(row.get('survey_length_m'))}m 행이 확인됩니다. "
                "직접 공동 탐지값은 아니므로 공동 확정이 아니라 탐사 필요 근거로 해석하고, 의심 구간은 GPR 재탐사를 배정합니다."
            )

    if factor_key == "rainfall" and isinstance(rows, list) and rows:
        total = sum(float(row.get("rainfall") or 0.0) for row in rows)
        latest = rows[0]
        return (
            f"weather_data 최근 {len(rows)}일 행 기준 누적 {total:.1f}mm이며, "
            f"최근 행은 {latest.get('record_date') or '-'} {latest.get('rainfall') or 0}mm"
            f"(관측소 {latest.get('stations') or '-'})입니다. "
            "강우 후 24~72시간은 토사 유실과 배수 불량이 드러나는 기간이므로 포장 침하와 배수 상태를 집중 확인합니다."
        )

    if factor_key == "groundwater":
        if isinstance(rows, list) and rows:
            row = rows[0]
            return (
                f"{row.get('record_date') or '-'} {row.get('station_name') or '-'} 관측 행에서 "
                f"지하수위 {fmt(row.get('groundwater_level'))}, 변동 {fmt(row.get('variation'))}이 확인됩니다. "
                "급격한 수위 변화는 토립자 이동 또는 누수 가능성과 함께 점검합니다."
            )
        if isinstance(rows, dict):
            borehole_rows = rows.get("molit_ground_boreholes") or []
            if borehole_rows:
                row = borehole_rows[0]
                return (
                    f"근접 시추공 {row.get('borehole_code') or '-'}({row.get('address') or row.get('project_name') or '주소 미상'})의 "
                    f"지하수위 {fmt(row.get('groundwater_level_m'))}m, 굴진심도 {fmt(row.get('total_depth_m'))}m를 대체 지표로 사용했습니다. "
                    "직접 관측값이 아니므로 현장 수위 관측 또는 인접 관측망 확인을 병행합니다."
                )

    if factor_key == "environment" and isinstance(rows, dict):
        env_rows = rows.get("environment_features") or []
        ground_layer = rows.get("ground_layer_summary") or {}
        parts = []
        if env_rows:
            row = env_rows[0]
            parts.append(
                f"{row.get('land_use_type') or '-'} 환경 행의 건물밀도 {fmt(row.get('building_density'))}, 도로밀도 {fmt(row.get('road_density'))}"
            )
        if ground_layer:
            parts.append(
                f"근접 지층 {fmt(ground_layer.get('nearby_count'), 0)}건, 지층 점수 {fmt(ground_layer.get('score'))}"
            )
        if parts:
            return "; ".join(parts) + "가 확인됩니다. 지반 취약층과 밀집 개발 조건이 겹치면 배수·관로·공사 영향을 함께 점검합니다."

    if factor_key == "construction" and isinstance(rows, list) and rows:
        row = rows[0]
        return (
            f"{row.get('address') or '주소 미상'}의 {row.get('construction_type') or '-'} 공사 행이 있으며 "
            f"시작일 {row.get('start_date') or '-'}, 규모지표 {fmt(row.get('scale_score'))}, 출처 {row.get('source_name') or '-'}입니다. "
            "굴착 깊이, 흙막이, 되메우기 다짐, 배수 관리 기록을 확인해야 점수 저감 근거로 인정됩니다."
        )

    return _compact_text(evidence.get("summary"), 260)


def build_commercial_report(analysis_payload: dict[str, Any]) -> str:
    location = analysis_payload["location"]
    analysis = analysis_payload["analysis"]
    weather = analysis_payload["weather"]
    breakdown = analysis_payload["breakdown"]
    features = analysis_payload.get("features") or {}
    coverage = analysis_payload.get("data_coverage") or {}
    reference = coverage.get("reference_region") or {}
    reason_cards = analysis_payload.get("reason_cards") or []
    client_local_time = analysis.get("client_local_time")
    score = float(analysis.get("total_risk_score") or 0.0)
    level = str(analysis.get("risk_level") or "-")
    location_name = str(location.get("location_name") or "-")
    latitude = location.get("latitude")
    longitude = location.get("longitude")
    distance_m = coverage.get("distance_m")
    distance_text = f"{float(distance_m) / 1000:.2f}km" if distance_m is not None else "-"
    coverage_status = str(coverage.get("status") or "")
    inference_note = (
        "이 위치의 일부 점수는 선택 좌표에 직접 붙은 정밀 원천자료가 아니라 근접 분석 지점 기반 추정입니다."
        if coverage_status in {"proxy", "insufficient"} else
        "이 위치는 저장 분석 지점과 가까워 공공데이터 기반 분석값을 직접 참조했습니다. 다만 좌표 단위 현장조사 결과는 아닙니다."
    )
    if coverage_status == "insufficient":
        inference_note = "근접 공공데이터 분석 지점이 부족하여 강우 등 즉시 확인 가능한 항목 중심으로만 산정했습니다."

    factor_rows = [
        (key, FACTOR_LABELS.get(key, key), float(breakdown.get(key) or 0.0))
        for key in FACTOR_LABELS
        if key != "total"
    ]
    top_factors = [row for row in sorted(factor_rows, key=lambda item: item[2], reverse=True) if row[2] > 0][:4]
    evidence_context = _commercial_evidence_context(analysis_payload)

    def fmt(value: Any, digits: int = 1) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "-"
        if abs(number - round(number)) < 0.0001:
            return str(int(round(number)))
        return f"{number:.{digits}f}"

    def factor_line(key: str, label: str, contribution: float) -> str:
        feature_key, unit = FACTOR_FEATURES.get(key, ("", ""))
        raw_value = features.get(feature_key)
        max_score = FACTOR_MAX_SCORES.get(key, 100.0)
        return f"- {label}: {contribution:.1f}/{max_score:.0f}점, 원자료 {fmt(raw_value)}{unit}"

    def action_for_factor(key: str, label: str) -> str:
        evidence = evidence_context.get(key) or {}
        status = str(evidence.get("status") or "missing")
        evidence_text = _management_evidence_text(key, evidence, fmt)
        if status == "missing":
            return (
                f"- {label}: 근거: 참조 지점 DB에서 이 요인의 세부 원자료 행이 확인되지 않았습니다. "
                f"따라서 특정 시설을 바로 보수 대상으로 단정하지 말고, 현장 점검과 원자료 보강 후 조치합니다. "
                f"관리안: {generic_action_for_factor(key)}"
            )
        qualifier = "추정 근거" if status == "estimated" else "실제 원자료 근거"
        return (
            f"- {label}: {qualifier}: {evidence_text} "
            f"관리안: {generic_action_for_factor(key)} "
            f"제한: {_compact_text(evidence.get('limitation'), 160)}"
        )

    def generic_action_for_factor(key: str) -> str:
        actions = {
            "past_sinkhole": "과거 침하 이력이 반영된 구간은 반복 침하 흔적, 포장 보수부, 맨홀 주변 단차를 우선 확인합니다.",
            "gpr": "GPR/탐사 점수가 높으면 공동 후보 위치를 재탐사하고 공동 규모 확인 후 보수 우선순위를 지정합니다.",
            "facility": "확인된 노후 시설물의 균열·누수·배수 상태를 점검하고, 관로·맨홀은 실제 관로 원자료나 현장조사로 확인된 경우에만 보수 대상으로 지정합니다.",
            "rainfall": "강우 점수가 높으면 강우 후 24~72시간 동안 배수 불량, 토사 유출, 포장 침하를 집중 순찰합니다.",
            "groundwater": "지하수 점수가 높으면 지하수위 변동, 양수, 누수 가능성을 함께 확인하고 관측값 갱신 주기를 줄입니다.",
            "environment": "환경/지층 점수가 높으면 취약 지층, 도로·건물 밀집, 지하매설물 집중 구간을 정밀 조사 대상으로 둡니다.",
            "construction": "공사 영향 점수가 높으면 굴착 깊이, 되메우기 품질, 흙막이, 배수, 진동 관리 상태를 확인합니다.",
        }
        return actions.get(key, "해당 요인의 원자료를 갱신하고 현장 확인 결과로 재산정합니다.")

    if score >= 80:
        decision = "즉시 현장 확인과 관계기관 공유가 필요한 최우선 관리 대상입니다."
    elif score >= 60:
        decision = "단기 점검 대상으로 지정하고 강우·공사 일정과 연동한 집중 모니터링이 필요합니다."
    elif score >= 30:
        decision = "상시 관리 대상입니다. 상위 기여 요인이 증가하면 우선순위를 올려야 합니다."
    else:
        decision = "현재 점수만으로 긴급 위험 신호는 낮지만 신규 공사, 강우, 지하수 변동은 계속 확인해야 합니다."

    reference_lines = []
    if reference:
        reference_lines = [
            f"- 참조 분석 지점: {reference.get('region_name') or '-'}",
            f"- 참조 지점 위험도: {fmt(reference.get('total_risk_score'))}/100점, 등급 {reference.get('risk_level') or '-'}",
            f"- 선택 위치와 참조 지점 거리: {distance_text}",
        ]
    else:
        reference_lines = [
            "- 참조 분석 지점: 없음",
            "- 선택 좌표 주변에 충분히 가까운 저장 분석 지점이 없어 비강우 항목은 제한적으로만 반영했습니다.",
        ]

    reason_lines = []
    for card in reason_cards[:5]:
        title = str(card.get("title") or "근거").strip()
        badge = str(card.get("badge") or "-").strip()
        body = str(card.get("body") or "").strip()
        if body:
            reason_lines.append(f"- {title}({badge}): {body}")
    if not reason_lines:
        reason_lines.append("- 상세 AI 근거 카드가 없어 점수 기여도와 데이터 적용 범위 중심으로 해석합니다.")

    action_lines = [action_for_factor(key, label) for key, label, _ in top_factors]
    if not action_lines:
        action_lines.append("- 현재 두드러진 상승 요인이 없으므로 정기 모니터링과 데이터 갱신을 유지합니다.")

    lines = [
        "[보고서 형식] 직접 선택 위치 상세 분석 리포트",
        "",
        "1. 분석 개요",
        f"- 대상 위치: {location_name}",
        f"- 도로명 주소: {location_name}",
        f"- 좌표: {fmt(latitude, 5)}, {fmt(longitude, 5)}",
        f"- 위치 해석 방식: {location.get('source') or '-'}",
        f"- 분석 시각(로컬): {client_local_time or '-'}",
        f"- 참조 분석일: {analysis.get('analysis_date') or '-'}",
        "- 분석 성격: 이 결과는 선택 위치 주변의 공공데이터 기반 위험도와 실시간 강우 정보를 결합한 사전 점검 우선순위 지표입니다.",
        "",
        "2. 종합 판단",
        f"- 종합 위험도: {score:.1f}/100점",
        f"- 위험 등급: {level}",
        f"- 운영 판단: {decision}",
        f"- 데이터 적용 범위: {coverage.get('label') or '-'}",
        f"- 추정 여부: {inference_note}",
        "",
        "3. 데이터 적용 범위와 한계",
        *reference_lines,
        f"- 적용 방식: {coverage.get('message') or '-'}",
        f"- 거리 보정 계수: {fmt(coverage.get('factor'), 2)}",
        "- 주의 사항: 직접 시추, GPR, 관로 CCTV, 현장 계측 결과가 없는 위치는 확정 위험 원인으로 단정하지 않습니다.",
        "",
        "4. 실시간·공공데이터 요약",
        f"- 최근 7일 누적 강수량: {fmt(weather.get('rainfall_7d_total'))}mm",
        f"- 7일 일별 강수량: {', '.join(f'{fmt(value)}mm' for value in weather.get('rainfall_7d_daily') or []) or '-'}",
        f"- 평균 기온: {fmt(weather.get('temperature_avg'))}도",
        f"- 해발 고도: {fmt(weather.get('elevation'))}m",
        f"- 과거 침하 원자료: {fmt(features.get('past_sinkhole_count'))}건",
        f"- GPR/탐사 원자료: {fmt(features.get('gpr_detected_count'))}건 상당",
        f"- 시설물 노후도 원자료: {fmt(features.get('facility_aging_score'))}점",
        f"- 지하수 원자료: {fmt(features.get('groundwater_score'))}점",
        f"- 환경/지층 원자료: {fmt(features.get('environment_score'))}점",
        f"- 공사 영향 원자료: {fmt(features.get('construction_score'))}점",
        "",
        "5. 점수 산정 결과",
        *[factor_line(key, label, contribution) for key, label, contribution in factor_rows],
        "",
        "6. 주요 위험 근거",
        *reason_lines,
        "",
        "7. 관리 방안 및 점수 저감 방법",
        *action_lines,
        "- 공통 조치: 현장 확인 결과를 데이터에 반영한 뒤 리포트를 다시 생성해 점수 변화를 확인합니다.",
        "- 모니터링: 반복 확인이 필요한 위치는 모니터링 지점으로 등록해 해제 전까지 자동 갱신 대상으로 관리합니다.",
        "",
        "8. 현장 점검 체크리스트",
        "- 포장 침하, 균열, 보수부 재침하, 맨홀 주변 단차 확인",
        "- 하수관·상수관 접합부 누수, 배수 불량, 토사 유출 흔적 확인",
        "- 주변 굴착 공사 복구 상태, 되메우기 품질, 흙막이·배수 관리 상태 확인",
        "- 강우 후 24~72시간 내 동일 지점 재점검",
        "- 필요 시 GPR 재탐사, 관로 CCTV, 추가 시추 또는 지반조사 검토",
        "",
        "9. 데이터 출처와 해석 한계",
        "- 강우/기상: 실시간 위치 기반 기상 API",
        "- 참조 위험도: 시스템 DB에 저장된 서울/수도권 공공데이터 기반 분석 지점",
        "- 시설물·사고·GPR·지하수·환경·공사 항목: 참조 지점의 공공데이터 feature를 거리 조건에 따라 반영",
        "- 한계: 직접 선택 좌표 자체의 지하 공동, 관로 결함, 지층 상태가 별도 조사로 확인된 것은 아닙니다. 이 문서는 사전 점검 우선순위 판단용입니다.",
    ]
    return "\n".join(lines)
