from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

import requests
from fastapi import APIRouter, Depends

from app.config.settings import settings
from app.db.core import query_all, query_one
from app.main_deps import get_db
from app.models.schemas import AiChatRequest
from app.routes.analysis import analyze_region
from app.services.ai_evidence import (
    build_evidence_context,
    build_factor_evidence_answer,
    is_evidence_question,
)
from app.services.monitoring_points import active_monitoring_count, recent_monitoring_detection_count
from app.services.reasoning import FACTOR_LABELS
from app.utils.response import ok


router = APIRouter()


ACTION_BY_FACTOR = {
    "past_sinkhole": "과거 침하 지점 주변의 반복 침하 여부를 확인하고, 같은 구간은 점검 주기를 단축해야 합니다.",
    "gpr": "GPR 재탐사로 공동 위치와 규모를 다시 확인한 뒤 이상 신호가 큰 구간부터 보수해야 합니다.",
    "facility": "노후 관로와 지하시설물의 누수, 균열, 접합부 이상을 우선 점검해 시설물 노후도 점수를 낮춰야 합니다.",
    "rainfall": "강우 직후 배수 상태와 지표면 균열을 확인하고, 배수 불량 지점을 보수해야 합니다.",
    "groundwater": "지하수위 급변 구간은 수위 센서와 현장 점검을 연계해 지반 약화 가능성을 줄여야 합니다.",
    "environment": "도로와 건물 밀집도가 높은 구간은 교통 하중과 지하 매설물 집중도를 함께 관리해야 합니다.",
    "construction": "공사장 인접 구간은 굴착 깊이, 흙막이 상태, 진동 기록을 관리해 공사 영향 점수를 낮춰야 합니다.",
}

REGION_ROAD_ADDRESSES = {
    900001: "서울특별시 강동구 천호대로 1095 인근",
    900002: "서울특별시 강남구 테헤란로 152 인근",
    900003: "서울특별시 송파구 송파대로 167 인근",
    900004: "서울특별시 송파구 올림픽로 300 인근",
    900005: "서울특별시 송파구 중대로 135 인근",
    900006: "서울특별시 강서구 마곡중앙로 161 인근",
    900007: "서울특별시 영등포구 국회대로 608 인근",
    900008: "서울특별시 서초구 서초대로 396 인근",
    900009: "서울특별시 성동구 왕십리로 222 인근",
    900010: "서울특별시 마포구 월드컵북로 400 인근",
    900011: "서울특별시 용산구 한강대로 405 인근",
    900012: "서울특별시 구로구 디지털로 300 인근",
}

REGION_ADDRESS_ALIASES = {
    900001: "강동·하남권",
    900002: "강남권",
    900003: "송파·성남권",
    900004: "송파·광진권",
    900005: "송파·강동권",
    900006: "강서·마곡권",
    900007: "영등포·마포권",
    900008: "서초·강남권",
    900009: "성동·동대문권",
    900010: "마포·상암권",
    900011: "중구·용산권",
    900012: "구로·금천권",
}


FACTOR_KEYWORDS = {
    "past_sinkhole": ("과거", "사고", "침하 이력", "지반침하", "싱크홀 이력"),
    "gpr": ("gpr", "탐사", "공동", "물리탐사"),
    "facility": ("시설", "시설물", "노후", "노후도", "관로", "상수", "하수", "매설물"),
    "rainfall": ("강우", "강수", "비", "호우"),
    "groundwater": ("지하수", "수위", "관측공"),
    "environment": ("환경", "밀집", "건물", "도로 밀도", "지층", "토질"),
    "construction": ("공사", "굴착", "도로굴착", "시공", "지하안전"),
}

FACTOR_FEATURE_KEYS = {
    "past_sinkhole": "past_sinkhole_count",
    "gpr": "gpr_detected_count",
    "facility": "facility_aging_score",
    "rainfall": "rainfall_score",
    "groundwater": "groundwater_score",
    "environment": "environment_score",
    "construction": "construction_score",
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value: Any, digits: int = 1) -> str:
    return f"{_num(value):.{digits}f}"


def _normalize(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE).lower()


def _region_address(region: dict[str, Any] | None) -> str:
    if not region:
        return "주소 미확인"
    region_id = int(region.get("region_id") or 0)
    return REGION_ROAD_ADDRESSES.get(region_id) or str(region.get("region_name") or "주소 미확인")


def _region_alias(region: dict[str, Any] | None) -> str:
    if not region:
        return ""
    region_id = int(region.get("region_id") or 0)
    return REGION_ADDRESS_ALIASES.get(region_id) or str(region.get("region_name") or "")


def _address_label(region: dict[str, Any] | None) -> str:
    return _region_address(region)


def _replace_region_name(text: str, region: dict[str, Any] | None) -> str:
    name = str(region.get("region_name") or "") if region else ""
    if not name:
        return text
    return text.replace(name, _region_address(region))


def _replace_known_locations(text: str, rows: list[dict[str, Any]], target: dict[str, Any] | None = None) -> str:
    next_text = text.replace("road_address", "도로명 주소")
    seen: set[int] = set()
    candidates = [row for row in rows if row]
    if target:
        candidates.append(target)
    for row in candidates:
        region_id = int(row.get("region_id") or 0)
        if region_id in seen:
            continue
        seen.add(region_id)
        address = _region_address(row)
        names = {
            str(row.get("region_name") or ""),
            str(row.get("address_alias") or ""),
            _region_alias(row),
        }
        for name in sorted((item for item in names if item), key=len, reverse=True):
            next_text = next_text.replace(name, address)
        next_text = re.sub(rf"{re.escape(address)}\s*\(\s*{re.escape(address)}\s*\)", address, next_text)
        next_text = re.sub(rf"({re.escape(address)})(\s*,?\s*{re.escape(address)})+", r"\1", next_text)
    return next_text


def _with_address(row: dict[str, Any]) -> dict[str, Any]:
    next_row = dict(row)
    next_row["road_address"] = _region_address(next_row)
    next_row["address_alias"] = _region_alias(next_row)
    next_row["display_location"] = _address_label(next_row)
    return next_row


def _latest_analysis_date(conn: sqlite3.Connection) -> str | None:
    row = query_one(conn, "SELECT MAX(analysis_date) AS analysis_date FROM risk_analysis_result")
    return str(row["analysis_date"]) if row and row.get("analysis_date") else None


def _recent_detection_count(conn: sqlite3.Connection) -> int:
    recent_sinkholes = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM sinkhole_history
        WHERE occurrence_date IS NOT NULL
          AND date(occurrence_date) >= date('now', 'localtime', '-1 day')
        """,
    )
    return int((recent_sinkholes or {}).get("count") or 0) + recent_monitoring_detection_count(conn)


def _summary(conn: sqlite3.Connection, analysis_date: str | None) -> dict[str, Any]:
    if not analysis_date:
        return {
            "region_count": 0,
            "high_risk_count": 0,
            "very_high_risk_count": 0,
            "average_risk_score": 0,
            "monitoring_point_count": active_monitoring_count(conn),
            "recent_detection_count": _recent_detection_count(conn),
        }
    row = query_one(
        conn,
        """
        SELECT
            COUNT(*) AS region_count,
            COALESCE(SUM(CASE WHEN total_risk_score >= 60 THEN 1 ELSE 0 END), 0) AS high_risk_count,
            COALESCE(SUM(CASE WHEN total_risk_score >= 80 THEN 1 ELSE 0 END), 0) AS very_high_risk_count,
            COALESCE(AVG(total_risk_score), 0) AS average_risk_score
        FROM risk_analysis_result
        WHERE analysis_date = ?
        """,
        (analysis_date,),
    )
    summary = dict(row or {"region_count": 0, "high_risk_count": 0, "very_high_risk_count": 0, "average_risk_score": 0})
    summary["monitoring_point_count"] = active_monitoring_count(conn)
    summary["recent_detection_count"] = _recent_detection_count(conn)
    return summary


def _top_regions(conn: sqlite3.Connection, analysis_date: str | None, limit: int = 5) -> list[dict[str, Any]]:
    if not analysis_date:
        return []
    return [_with_address(row) for row in query_all(
        conn,
        """
        SELECT g.region_id, g.region_name, g.latitude, g.longitude,
               r.total_risk_score, r.risk_level, r.priority_rank, r.analysis_date
        FROM risk_analysis_result r
        JOIN regions g ON g.region_id = r.region_id
        WHERE r.analysis_date = ?
        ORDER BY r.total_risk_score DESC, r.id ASC
        LIMIT ?
        """,
        (analysis_date, limit),
    )]


def _all_regions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_with_address(row) for row in query_all(conn, "SELECT region_id, region_name, latitude, longitude FROM regions ORDER BY region_id")]


def _match_region(conn: sqlite3.Connection, text: str) -> dict[str, Any] | None:
    normalized = _normalize(text)
    if not normalized:
        return None
    regions = _all_regions(conn)
    for region in regions:
        name = str(region.get("region_name") or "")
        address = str(region.get("road_address") or "")
        alias = str(region.get("address_alias") or "")
        if _normalize(name) and _normalize(name) in normalized:
            return region
        if _normalize(address) and _normalize(address) in normalized:
            return region
        if _normalize(alias) and _normalize(alias) in normalized:
            return region
    tokens = [token for token in re.split(r"[\s,./?]+", text) if len(token) >= 2]
    for region in regions:
        search_key = _normalize(" ".join(
            [
                str(region.get("region_name") or ""),
                str(region.get("road_address") or ""),
                str(region.get("address_alias") or ""),
            ]
        ))
        if any(_normalize(token) and _normalize(token) in search_key for token in tokens):
            return region
    return None


def _target_region(conn: sqlite3.Connection, req: AiChatRequest, top_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    history_text = " ".join(item.content for item in req.history[-6:])
    matched = _match_region(conn, f"{req.message} {history_text}")
    if matched:
        return matched
    return top_rows[0] if top_rows else None


def _top_factors(payload: dict[str, Any], limit: int = 3) -> list[tuple[str, float]]:
    breakdown = payload.get("breakdown") or {}
    items = [
        (key, _num(value))
        for key, value in breakdown.items()
        if key != "total" and _num(value) > 0
    ]
    return sorted(items, key=lambda item: item[1], reverse=True)[:limit]


def _factor_text(factors: list[tuple[str, float]]) -> str:
    if not factors:
        return "현재 유의미하게 튀는 단일 요인은 없지만, 종합 점수 기준으로 관리가 필요합니다"
    return ", ".join(f"{FACTOR_LABELS.get(key, key)} {_fmt(value)}점" for key, value in factors)


def _action_text(factors: list[tuple[str, float]]) -> str:
    actions = [ACTION_BY_FACTOR[key] for key, _ in factors if key in ACTION_BY_FACTOR]
    if not actions:
        actions = ["정기 모니터링을 유지하고, 강우 직후와 공사 발생 시점에는 재평가를 수행해야 합니다."]
    return " ".join(actions[:3])


def _factor_key_from_message(message: str) -> str | None:
    normalized = _normalize(message)
    for key, keywords in FACTOR_KEYWORDS.items():
        if any(_normalize(keyword) in normalized for keyword in keywords):
            return key
    return None


def _is_factor_detail_question(message: str) -> bool:
    normalized = _normalize(message)
    if not normalized:
        return False
    has_factor = _factor_key_from_message(message) is not None or any(
        _normalize(word) in normalized for word in ("위험기여요인", "기여요인", "기여도", "위험요인")
    )
    asks_detail = any(
        _normalize(word) in normalized
        for word in ("왜", "근거", "정확", "어느", "어떤", "데이터", "자료", "점수", "산정", "계산", "원인", "영향", "때문", "관련", "맞아")
    )
    return has_factor and asks_detail


def _factor_formula_text(factor_key: str, feature_value: float, contribution: float) -> str:
    if factor_key == "past_sinkhole":
        return f"산식은 min(30, 과거 침하 건수 x 8)입니다. 현재 원자료 지표 {feature_value:.1f}건이 반영되어 기여점수는 {contribution:.1f}점입니다."
    if factor_key == "gpr":
        return f"산식은 min(30, GPR/탐사 지표 x 12)입니다. 현재 원자료 지표 {feature_value:.1f}건 상당이 반영되어 기여점수는 {contribution:.1f}점입니다."
    if factor_key == "facility":
        uncapped = feature_value * 0.25
        cap_text = "상한 15점에 걸렸기 때문에 15점으로 제한됐습니다" if uncapped > 15 else "상한에는 걸리지 않았습니다"
        return f"산식은 min(15, 시설물 노후도 원자료 지표 x 0.25)입니다. 현재 원자료 지표 {feature_value:.1f}점 x 0.25 = {uncapped:.1f}점이고, {cap_text}."
    if factor_key == "rainfall":
        return f"산식은 최근 7일 강우 지표를 0~10점 범위로 반영합니다. 현재 강우 원자료 지표 {feature_value:.1f}점이 그대로 기여점수 {contribution:.1f}점으로 들어갔습니다."
    if factor_key == "groundwater":
        return f"산식은 지하수 변동 또는 시추공 지하수위 대체 지표를 0~8점 범위로 반영합니다. 현재 원자료 지표 {feature_value:.1f}점이 기여점수 {contribution:.1f}점으로 들어갔습니다."
    if factor_key == "environment":
        return f"산식은 건물/도로 밀집도와 지층 보정값을 0~6점 범위로 반영합니다. 현재 환경 원자료 지표 {feature_value:.1f}점이 기여점수 {contribution:.1f}점으로 들어갔습니다."
    if factor_key == "construction":
        uncapped = feature_value * 0.2
        cap_text = "상한 4점에 걸렸습니다" if uncapped > 4 else "상한에는 걸리지 않았습니다"
        return f"산식은 min(4, 공사 영향 원자료 지표 x 0.2)입니다. 현재 원자료 지표 {feature_value:.1f}점 x 0.2 = {uncapped:.1f}점이고, {cap_text}."
    return f"현재 원자료 지표 {feature_value:.1f}, 기여점수 {contribution:.1f}점입니다."


def _row_label(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return "-"


def _join_evidence(items: list[str], *, empty: str) -> str:
    return "; ".join(items[:5]) if items else empty


def _facility_evidence(conn: sqlite3.Connection, region_id: int) -> tuple[str, str]:
    status_rows = query_all(
        conn,
        """
        SELECT facility_name, facility_type, address, aging_ratio, aging_count, total_count, source_name
        FROM facility_status
        WHERE region_id = ?
        ORDER BY COALESCE(aging_ratio, 0) DESC, COALESCE(aging_count, 0) DESC, id ASC
        LIMIT 5
        """,
        (region_id,),
    )
    inspection_rows = query_all(
        conn,
        """
        SELECT facility_name, facility_type, address, inspection_date, diagnosis_result, risk_score, source_name
        FROM facility_inspection
        WHERE region_id = ?
        ORDER BY COALESCE(risk_score, 0) DESC, inspection_date DESC, id ASC
        LIMIT 5
        """,
        (region_id,),
    )
    summary = query_one(
        conn,
        """
        SELECT
            COUNT(*) AS row_count,
            COALESCE(SUM(total_count), 0) AS total_count,
            COALESCE(SUM(aging_count), 0) AS aging_count,
            COALESCE(AVG(aging_ratio), 0) AS avg_aging_ratio
        FROM facility_status
        WHERE region_id = ?
        """,
        (region_id,),
    ) or {}
    status_text = _join_evidence(
        [
            f"{_row_label(row, 'facility_name')}({row.get('facility_type') or '-'}, {row.get('address') or '주소 없음'}, 노후비율 {_fmt(row.get('aging_ratio'))})"
            for row in status_rows
        ],
        empty="facility_status에 이 지역의 세부 시설 행이 없습니다.",
    )
    inspection_text = _join_evidence(
        [
            f"{_row_label(row, 'facility_name')}({row.get('facility_type') or '-'}, {row.get('address') or '주소 없음'}, 점검 {row.get('inspection_date') or '-'}, 위험지표 {_fmt(row.get('risk_score'))})"
            for row in inspection_rows
        ],
        empty="facility_inspection에 이 지역의 점검 행이 없습니다.",
    )
    types = {str(row.get("facility_type") or "") for row in [*status_rows, *inspection_rows] if row.get("facility_type")}
    pipe_like = any(("관" in item or "상수" in item or "하수" in item) for item in types)
    limitation = (
        "현재 세부 행에는 관로로 확인되는 시설 유형도 포함되어 있어 관로 점검을 우선 검토할 수 있습니다."
        if pipe_like
        else "현재 확인된 세부 행은 주로 건축물/시설 단위입니다. 따라서 노후 관로가 원인이라고 단정하면 안 되고, 관로 영향은 별도 상하수도/GPR 점검으로 확인해야 합니다."
    )
    basis = (
        f"facility_status 집계는 {int(summary.get('row_count') or 0)}행, 총 {int(summary.get('total_count') or 0)}개 중 "
        f"노후 {int(summary.get('aging_count') or 0)}개, 평균 노후비율 {_fmt(summary.get('avg_aging_ratio'))}입니다. "
        f"노후 근거 행: {status_text}. 점검 위험도 상위 행: {inspection_text}."
    )
    return basis, limitation


def _past_sinkhole_evidence(conn: sqlite3.Connection, region_id: int) -> tuple[str, str]:
    rows = query_all(
        conn,
        """
        SELECT occurrence_date, cause_type, damage_scale, address, source_name
        FROM sinkhole_history
        WHERE region_id = ?
        ORDER BY occurrence_date DESC, COALESCE(damage_scale, 0) DESC
        LIMIT 5
        """,
        (region_id,),
    )
    text = _join_evidence(
        [
            f"{row.get('occurrence_date') or '-'} {row.get('address') or '주소 없음'} / 원인 {row.get('cause_type') or '미상'} / 규모 {_fmt(row.get('damage_scale'))}"
            for row in rows
        ],
        empty="sinkhole_history에 이 지역의 과거 침하 사고 행이 없습니다.",
    )
    return text, "과거 사고는 반복 위험의 근거지만, 현재 같은 위치에서 침하가 진행 중이라는 뜻은 아닙니다."


def _gpr_evidence(conn: sqlite3.Connection, region_id: int) -> tuple[str, str]:
    gpr_rows = query_all(
        conn,
        """
        SELECT inspection_date, cavity_count, depth_estimate, inspection_method, address, source_name
        FROM gpr_inspection
        WHERE region_id = ?
        ORDER BY COALESCE(cavity_count, 0) DESC, inspection_date DESC
        LIMIT 5
        """,
        (region_id,),
    )
    geo_rows = query_all(
        conn,
        """
        SELECT survey_method, survey_point_name, address, survey_length_m, source_name
        FROM molit_aggregate_geophysics
        WHERE region_id = ?
        ORDER BY COALESCE(survey_length_m, 0) DESC, id ASC
        LIMIT 5
        """,
        (region_id,),
    )
    gpr_text = _join_evidence(
        [
            f"{row.get('inspection_date') or '-'} {row.get('address') or '주소 없음'} / 공동 {int(row.get('cavity_count') or 0)}건 / 심도 {_fmt(row.get('depth_estimate'))}m"
            for row in gpr_rows
        ],
        empty="gpr_inspection에 직접 공동 탐지 행이 없습니다.",
    )
    geo_text = _join_evidence(
        [
            f"{row.get('survey_point_name') or row.get('address') or '위치명 없음'} / 방법 {row.get('survey_method') or '-'} / 연장 {_fmt(row.get('survey_length_m'))}m"
            for row in geo_rows
        ],
        empty="molit_aggregate_geophysics에 보조 탐사 행이 없습니다.",
    )
    return f"직접 GPR 근거: {gpr_text}. 보조 물리탐사 근거: {geo_text}.", "직접 공동 탐지 행이 없고 보조 탐사만 있으면 공동이 확인됐다고 말하지 않고 탐사 가능성 지표로만 봅니다."


def _rainfall_evidence(conn: sqlite3.Connection, region_id: int, analysis_date: str | None) -> tuple[str, str]:
    rows = query_all(
        conn,
        """
        SELECT record_date, ROUND(SUM(rainfall), 2) AS rainfall, GROUP_CONCAT(DISTINCT station_name) AS stations
        FROM weather_data
        WHERE region_id = ?
          AND record_date >= date(?, '-7 day')
          AND record_date <= date(?)
        GROUP BY record_date
        ORDER BY record_date DESC
        LIMIT 7
        """,
        (region_id, analysis_date or "", analysis_date or ""),
    )
    text = _join_evidence(
        [
            f"{row.get('record_date')}: {row.get('rainfall') or 0}mm(관측소 {row.get('stations') or '-'})"
            for row in rows
        ],
        empty="weather_data에 분석일 기준 최근 7일 강우 행이 없습니다.",
    )
    return text, "강우는 실제 침하 확정 근거가 아니라 단기 지반 약화 가능성을 올리는 보조 변수입니다. 관측소명이 대상 지역과 맞지 않으면 데이터 매핑 점검이 필요합니다."


def _groundwater_evidence(conn: sqlite3.Connection, region_id: int, target: dict[str, Any] | None) -> tuple[str, str]:
    rows = query_all(
        conn,
        """
        SELECT record_date, groundwater_level, variation, station_name, source_name
        FROM groundwater_data
        WHERE region_id = ?
        ORDER BY record_date DESC
        LIMIT 5
        """,
        (region_id,),
    )
    if rows:
        text = _join_evidence(
            [
                f"{row.get('record_date') or '-'} {row.get('station_name') or '-'} / 수위 {_fmt(row.get('groundwater_level'))} / 변동 {_fmt(row.get('variation'))}"
                for row in rows
            ],
            empty="",
        )
        return text, "지하수 관측값이 있을 때는 최근 변동폭을 우선 반영합니다."

    lat = _num((target or {}).get("latitude"), None)
    lon = _num((target or {}).get("longitude"), None)
    borehole_rows: list[dict[str, Any]] = []
    if lat is not None and lon is not None:
        borehole_rows = query_all(
            conn,
            """
            SELECT borehole_code, project_name, address, groundwater_level_m, total_depth_m, source_name
            FROM molit_ground_boreholes
            WHERE latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND groundwater_level_m IS NOT NULL
            ORDER BY ((latitude - ?) * (latitude - ?)) + ((longitude - ?) * (longitude - ?)) ASC
            LIMIT 5
            """,
            (lat, lat, lon, lon),
        )
    text = _join_evidence(
        [
            f"{row.get('borehole_code') or '-'} {row.get('address') or row.get('project_name') or '주소 없음'} / 지하수위 {_fmt(row.get('groundwater_level_m'))}m / 굴진심도 {_fmt(row.get('total_depth_m'))}m"
            for row in borehole_rows
        ],
        empty="groundwater_data와 근접 시추공 지하수위 행이 없습니다.",
    )
    return text, "직접 지하수 관측값이 없으면 국토교통부 시추공 지하수위로 대체 추정합니다. 이 경우는 확정 관측이 아니라 대체 지표입니다."


def _environment_evidence(conn: sqlite3.Connection, region_id: int, features: dict[str, Any]) -> tuple[str, str]:
    rows = query_all(
        conn,
        """
        SELECT building_density, road_density, land_use_type
        FROM environment_features
        WHERE region_id = ?
        ORDER BY id DESC
        LIMIT 5
        """,
        (region_id,),
    )
    text = _join_evidence(
        [
            f"{row.get('land_use_type') or '-'} / 건물밀도 {_fmt(row.get('building_density'))} / 도로밀도 {_fmt(row.get('road_density'))}"
            for row in rows
        ],
        empty="environment_features에 이 지역의 환경 밀집도 행이 없습니다.",
    )
    ground_layer = features.get("ground_layer_summary") or {}
    layer_text = (
        f"지층 보정은 근접 지층 {int(ground_layer.get('nearby_count') or 0)}건, 지층 점수 {_fmt(ground_layer.get('score'))}점입니다."
        if ground_layer
        else "지층 보정 정보는 현재 payload에 없습니다."
    )
    return f"{text}. {layer_text}", "환경 점수는 개별 사고 원인 확정이 아니라 밀집도와 지층 취약성의 배경 위험 지표입니다."


def _construction_evidence(conn: sqlite3.Connection, region_id: int) -> tuple[str, str]:
    rows = query_all(
        conn,
        """
        SELECT construction_type, start_date, scale_score, source_name, address
        FROM construction_events
        WHERE region_id = ?
        ORDER BY COALESCE(scale_score, 0) DESC, start_date DESC, id ASC
        LIMIT 5
        """,
        (region_id,),
    )
    text = _join_evidence(
        [
            f"{row.get('construction_type') or '-'} / 시작 {row.get('start_date') or '-'} / 규모지표 {_fmt(row.get('scale_score'))} / 주소 {row.get('address') or '주소 없음'} / 출처 {row.get('source_name') or '-'}"
            for row in rows
        ],
        empty="construction_events에 이 지역의 공사 행이 없습니다.",
    )
    return text, "공사 행은 굴착·지하안전평가·건축허가 등 공사 영향 가능성을 뜻하며, 실제 지반침하 원인 확정은 현장 확인이 필요합니다."


def _factor_evidence(conn: sqlite3.Connection, factor_key: str, target: dict[str, Any], features: dict[str, Any], analysis_date: str | None) -> tuple[str, str]:
    region_id = int(target.get("region_id") or 0)
    if factor_key == "facility":
        return _facility_evidence(conn, region_id)
    if factor_key == "past_sinkhole":
        return _past_sinkhole_evidence(conn, region_id)
    if factor_key == "gpr":
        return _gpr_evidence(conn, region_id)
    if factor_key == "rainfall":
        return _rainfall_evidence(conn, region_id, analysis_date)
    if factor_key == "groundwater":
        return _groundwater_evidence(conn, region_id, target)
    if factor_key == "environment":
        return _environment_evidence(conn, region_id, features)
    if factor_key == "construction":
        return _construction_evidence(conn, region_id)
    return "해당 위험 기여요인의 세부 근거 조회 로직이 아직 없습니다.", "근거 로직이 없으면 임의로 설명하지 않습니다."


def _all_factor_evidence_answer(target: dict[str, Any] | None, payload: dict[str, Any] | None) -> str:
    if not target or not payload:
        return "위험 기여요인을 설명할 대상 지역을 찾지 못했습니다. 지역명이나 도로명 주소를 함께 질문해 주세요."
    features = payload.get("features") or {}
    breakdown = payload.get("breakdown") or {}
    lines = []
    for key in ("past_sinkhole", "gpr", "facility", "rainfall", "groundwater", "environment", "construction"):
        feature_value = _num(features.get(FACTOR_FEATURE_KEYS.get(key, "")))
        contribution = _num(breakdown.get(key))
        lines.append(f"{FACTOR_LABELS.get(key, key)}: 원자료 {feature_value:.1f}, 기여 {contribution:.1f}점")
    return (
        f"{_address_label(target)}의 위험 기여요인은 다음과 같습니다.\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\n세부 근거가 필요하면 '시설물 노후도 근거', '공사 영향 근거', '지하수 점수 근거'처럼 항목명을 지정해 주세요. "
        "없는 원천 데이터는 추정과 사실을 구분해 답하겠습니다."
    )


def _factor_evidence_answer(
    message: str,
    target: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    conn: sqlite3.Connection,
    analysis_date: str | None,
) -> str:
    if not target or not payload:
        return "위험 기여요인을 설명할 대상 지역을 찾지 못했습니다. 지역명이나 도로명 주소를 함께 질문해 주세요."
    factor_key = _factor_key_from_message(message)
    if factor_key is None:
        return _all_factor_evidence_answer(target, payload)

    features = payload.get("features") or {}
    breakdown = payload.get("breakdown") or {}
    feature_key = FACTOR_FEATURE_KEYS.get(factor_key, "")
    feature_value = _num(features.get(feature_key))
    contribution = _num(breakdown.get(factor_key))
    formula = _factor_formula_text(factor_key, feature_value, contribution)
    evidence, limitation = _factor_evidence(conn, factor_key, target, features, analysis_date)
    label = FACTOR_LABELS.get(factor_key, factor_key)
    return (
        f"{_address_label(target)}의 {label} 기여점수는 {contribution:.1f}점입니다. {formula}\n\n"
        f"실제 데이터 근거: {evidence}\n\n"
        f"주의: {limitation} 이 답변은 현재 DB에 들어온 공공데이터와 파일데이터만 근거로 하며, 확인되지 않은 시설명이나 원인은 만들지 않습니다."
    )


def _region_payload(conn: sqlite3.Connection, region_id: int, analysis_date: str | None) -> dict[str, Any] | None:
    if not region_id:
        return None
    return analyze_region(conn, int(region_id), analysis_date)


def _contains(message: str, words: tuple[str, ...]) -> bool:
    return any(word in message for word in words)


def _purpose_answer(summary: dict[str, Any], top_rows: list[dict[str, Any]], analysis_date: str | None) -> str:
    leader = top_rows[0] if top_rows else None
    leader_text = (
        f"현재 우선 관리 대상은 도로명 주소 기준 {_address_label(leader)}이며, 위험도는 {_fmt(leader['total_risk_score'])}점입니다."
        if leader
        else "아직 우선 관리 대상을 산정할 분석 결과가 없습니다."
    )
    return (
        "이 프로그램의 목적은 지반침하와 싱크홀 위험을 지역별로 점수화해서, 현장 점검 우선순위와 관리 방안을 빠르게 정하는 것입니다. "
        f"최신 분석일은 {analysis_date or '-'}이고, 등록된 분석 대상 {int(summary['region_count'])}개 중 "
        f"고위험 이상은 {int(summary['high_risk_count'])}개, 평균 위험도는 {_fmt(summary['average_risk_score'])}점입니다. "
        f"{leader_text} 저는 이 데이터를 기준으로 위험 지역, 원인, 점수 저감 조치, 보고서 작성 방향을 설명할 수 있습니다."
    )


def _overview_answer(summary: dict[str, Any], top_rows: list[dict[str, Any]], analysis_date: str | None) -> str:
    top_text = ", ".join(
        f"{idx}. {_address_label(row)} {_fmt(row['total_risk_score'])}점({row['risk_level']})"
        for idx, row in enumerate(top_rows[:3], start=1)
    ) or "상위 위험 지역 데이터 없음"
    return (
        f"현재 시스템에 등록된 분석 대상 기준 최신 분석일은 {analysis_date or '-'}입니다. "
        f"전체 {int(summary['region_count'])}개 지역의 평균 위험도는 {_fmt(summary['average_risk_score'])}점이고, "
        f"고위험 이상 지역은 {int(summary['high_risk_count'])}개입니다. "
        f"상위 위험 지역은 {top_text} 순서입니다. "
        "운영 관점에서는 상위 1~2개 지역을 우선 점검 대상으로 두고, 강우 이후 재평가와 GPR/시설물 점검을 묶어서 관리하는 것이 좋습니다."
    )


def _top_region_answer(top_rows: list[dict[str, Any]], analysis_date: str | None, payload: dict[str, Any] | None) -> str:
    if not top_rows:
        return "현재 분석 결과가 없어 가장 위험한 지역을 판단할 수 없습니다. 먼저 위험도 분석을 실행해야 합니다."
    top = top_rows[0]
    factors = _top_factors(payload or {})
    reason = _factor_text(factors)
    return (
        f"현재 프로그램에 등록된 서울/수도권 중심 분석 대상 기준으로 가장 싱크홀 발생 위험도가 높은 곳은 "
        f"도로명 주소 기준 {_address_label(top)}입니다. 최신 분석일 {analysis_date or top.get('analysis_date') or '-'} 기준 "
        f"위험도는 {_fmt(top['total_risk_score'])}/100점, 등급은 {top['risk_level']}, 우선순위는 {top['priority_rank']}위입니다. "
        f"주요 근거는 {reason}입니다. 서울/수도권 중심으로 현재 시스템 DB에 들어온 분석 대상 기준의 판단입니다."
    )


def _reason_answer(target: dict[str, Any] | None, payload: dict[str, Any] | None) -> str:
    if not target or not payload:
        return "설명할 대상 지역을 찾지 못했습니다. 예를 들어 '강남권 위험 이유 알려줘'처럼 지역명을 함께 물어보면 더 정확히 답할 수 있습니다."
    analysis = payload.get("analysis") or {}
    factors = _top_factors(payload)
    reason_card = _replace_region_name((payload.get("reason_cards") or [{}])[0].get("body") or "", target)
    return (
        f"{_address_label(target)} 위치가 위험하게 나온 이유는 총점 {_fmt(analysis.get('total_risk_score'))}점, "
        f"등급 {analysis.get('risk_level') or '-'}으로 산정됐기 때문입니다. "
        f"점수를 가장 많이 올린 항목은 { _factor_text(factors) }입니다. "
        f"{reason_card} "
        "즉, 한 가지 원인만 보는 것이 아니라 과거 이력, GPR 공동 탐지, 시설물 노후도, 강우·지하수·공사 영향을 합쳐서 판단한 결과입니다."
    )


def _management_answer(target: dict[str, Any] | None, payload: dict[str, Any] | None) -> str:
    if not target or not payload:
        return "관리 방안을 설명할 대상 지역을 찾지 못했습니다. 현재는 상위 위험 지역을 기준으로 답변하는 방식이 가장 정확합니다."
    analysis = payload.get("analysis") or {}
    factors = _top_factors(payload)
    breakdown = payload.get("breakdown") or {}
    features = payload.get("features") or {}
    cards = payload.get("reason_cards") or []
    top_factor_names = [FACTOR_LABELS.get(key, key) for key, _ in factors]
    data_basis = [
        f"과거 지반침하 {int(_num(features.get('past_sinkhole_count'), 0))}건",
        f"GPR/탐사 지표 {_fmt(features.get('gpr_detected_count'))}",
        f"시설물 노후도 {_fmt(features.get('facility_aging_score'))}",
        f"강우 {_fmt(features.get('rainfall_score'))}",
        f"지하수 {_fmt(features.get('groundwater_score'))}",
        f"환경 {_fmt(features.get('environment_score'))}",
        f"공사 영향 {_fmt(features.get('construction_score'))}",
    ]
    first_card = str((cards[0] if cards else {}).get("body") or "")
    if len(first_card) > 180:
        first_card = first_card[:180].rstrip() + "..."
    return (
        f"{_address_label(target)}의 점수를 낮추려면 점수 기여도가 큰 항목부터 처리해야 합니다. "
        f"현재 점수는 {_fmt(analysis.get('total_risk_score'))}/100점, 등급은 {analysis.get('risk_level') or '-'}이고 "
        f"우선순위가 높은 원인은 {', '.join(top_factor_names) or '뚜렷한 단일 요인 없음'}입니다.\n\n"
        "1. 1차 현장 확인: 과거 침하 지점과 현재 공사/굴착 구간을 지도에서 겹쳐 보고, 도로 균열, 함몰, 포장 처짐, 배수 불량을 먼저 확인합니다.\n"
        "2. 지중 원인 점검: GPR 또는 물리탐사 자료가 있는 구간은 공동 의심 구간을 우선 재탐사하고, 자료가 없는 구간은 지하매설물 위치 확인 후 표본 탐사를 잡습니다.\n"
        "3. 시설물 보수: 시설물 점수가 크면 상하수관, 맨홀, 노후 관로 이음부, 누수 흔적을 먼저 조사하고 누수/파손 발견 시 관로 보수와 되메움 다짐을 같이 진행합니다.\n"
        "4. 강우·지하수 대응: 비가 온 뒤 24~72시간 동안 배수 상태와 지하수 변동을 확인하고, 물고임이나 토사 유실 흔적이 있으면 임시 차수와 배수 정비를 우선합니다.\n"
        "5. 재평가 기준: 보수 후 같은 날짜 기준으로 재분석해 과거 사고 외의 가변 항목, 특히 시설물·공사·강우·지하수 기여도가 내려갔는지 확인합니다.\n\n"
        f"현재 공공데이터 근거값은 {', '.join(data_basis)}입니다. "
        f"{first_card} "
        "따라서 단순히 전체 점수를 낮추는 것이 아니라, 위 항목 중 실제 현장에서 확인되는 원인을 제거한 뒤 재분석하는 방식이 가장 신뢰도 높습니다."
    )


def _monitoring_answer(summary: dict[str, Any]) -> str:
    monitoring_count = int(summary.get("monitoring_point_count") or 0)
    return (
        f"현재 실제 센서 원본 기준으로 집계된 모니터링 지점은 {monitoring_count}개입니다. "
        "아직 센서 또는 현장 탐지 이벤트 원본 데이터가 연동되지 않았으므로 임의 모니터링 수치를 만들지 않습니다. "
        "운영 단계에서는 장비 ID, 수집 시각, 위치가 확인된 이벤트만 모니터링 지점과 최근 탐지 건수에 반영해야 합니다."
    )


TERM_DEFINITIONS = {
    "기타매설물 손상": (
        "상수관, 하수관처럼 별도 원인 항목으로 분류된 시설이 아니라 통신관, 전력관, 가스관, 공동구 부속관로, "
        "기타 지하 매설 시설이 공사나 노후화 등으로 손상되어 주변 토사가 유실된 경우를 뜻합니다. "
        "지반침하 사고 데이터의 원인 분류값이며, 이 값이 많으면 해당 구간은 지하매설물 위치 확인과 굴착 관리가 중요합니다."
    ),
    "상수관 손상": "상수도관이 파손되거나 누수되어 토사가 물과 함께 빠져나가면서 지반이 약해지는 경우입니다.",
    "하수관 손상": "하수관 균열, 이음부 파손, 누수로 주변 토사가 관로 안이나 빈 공간으로 유실되는 경우입니다.",
    "굴착공사 부실": "굴착 중 흙막이, 되메우기, 다짐, 배수 관리가 부족해 지반이 약해진 경우입니다.",
    "다짐 불량": "굴착 후 되메운 흙을 충분히 다지지 않아 시간이 지나며 침하가 발생할 수 있는 상태입니다.",
    "공동": "지하에 생긴 빈 공간입니다. GPR 탐사에서 공동이 발견되면 지반침하 위험 신호로 봅니다.",
    "GPR": "Ground Penetrating Radar의 약자로, 지표면에서 전자파를 쏴 지하 공동이나 이상 구간을 찾는 탐사 방식입니다.",
    "지하수": "지반 내부의 물입니다. 수위가 급격히 변하거나 지반 내 물 흐름이 커지면 토사 유실과 침하 가능성이 커질 수 있습니다.",
}


SOURCE_DESCRIPTIONS = {
    "ground_subsidence_accident": "국토교통부/국토안전관리원 전국지반침하정보표준데이터",
    "kalis_public_facility_safety": "국토안전관리원 공공시설물 안전관리 데이터",
    "kalis_public_facility_diagnosis": "국토안전관리원 공공시설물 진단/점검 데이터",
    "molit_underground_safety": "국토교통부 지하안전영향평가 관련 데이터",
    "kma_asos_hourly_rainfall": "기상청 ASOS 시간 단위 강우 데이터",
    "molit_ground_boreholes": "국토교통부 지반정보 시추공 데이터",
    "seoul_open_data": "서울열린데이터광장 지하수, 강우, 하수관로 수위, 도로굴착 데이터",
    "seoul_groundwater_observations": "서울열린데이터광장 보조지하수 관측망 관측정보",
    "seoul_rainfall": "서울열린데이터광장 강우량 정보",
    "seoul_sewer_levels": "서울열린데이터광장 하수관로 수위 현황",
    "seoul_road_excavation": "서울열린데이터광장 도로굴착 공사 현황",
}


def _matched_term(message: str) -> str | None:
    normalized = _normalize(message)
    if not normalized:
        return None
    for term in sorted(TERM_DEFINITIONS, key=len, reverse=True):
        if _normalize(term) in normalized:
            return term
    return None


def _is_definition_question(message: str) -> bool:
    lower = message.lower()
    return bool(_matched_term(message)) and _contains(
        lower,
        ("뜻", "의미", "무슨", "뭐야", "설명", "정의", "말이야"),
    )


def _term_answer(message: str, conn: sqlite3.Connection) -> str | None:
    term = _matched_term(message)
    if not term:
        return None

    cause_count = 0
    try:
        cause_row = query_one(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM sinkhole_history
            WHERE cause_type = ?
            """,
            (term,),
        )
        cause_count = int((cause_row or {}).get("c") or 0)
    except Exception:
        cause_count = 0

    suffix = (
        f" 현재 DB의 과거 지반침하 이력에는 이 원인으로 분류된 사고가 {cause_count}건 들어 있습니다."
        if cause_count
        else " 현재 선택된 분석 DB에서는 이 원인명 자체가 없거나, 아직 해당 원인으로 집계된 사고가 없습니다."
    )
    return f"'{term}'은 {TERM_DEFINITIONS[term]}{suffix}"


def _source_counts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = query_all(
        conn,
        """
        SELECT source_name, COUNT(*) AS c
        FROM raw_source_records
        GROUP BY source_name
        ORDER BY c DESC
        """
    )
    normalized = []
    for row in rows:
        name = str(row.get("source_name") or "")
        normalized.append(
            {
                "source_name": name,
                "label": SOURCE_DESCRIPTIONS.get(name, name),
                "count": int(row.get("c") or 0),
            }
        )
    return normalized


def _data_answer(message: str, conn: sqlite3.Connection) -> str:
    source_counts = _source_counts(conn)
    source_text = ", ".join(f"{row['label']} {row['count']}건" for row in source_counts[:5]) or "원천 레코드 없음"

    table_counts = {
        "과거 지반침하": conn.execute("SELECT COUNT(*) FROM sinkhole_history").fetchone()[0],
        "시설물 점검": conn.execute("SELECT COUNT(*) FROM facility_inspection").fetchone()[0],
        "시설물 현황": conn.execute("SELECT COUNT(*) FROM facility_status").fetchone()[0],
        "강우": conn.execute("SELECT COUNT(*) FROM weather_data").fetchone()[0],
        "지하수": conn.execute("SELECT COUNT(*) FROM groundwater_data").fetchone()[0],
        "공사 영향": conn.execute("SELECT COUNT(*) FROM construction_events").fetchone()[0],
    }
    table_text = ", ".join(f"{name} {count}건" for name, count in table_counts.items())

    if _contains(message, ("출처", "어디서", "사이트", "api", "API")):
        return (
            "현재 점수에 쓰는 자료 출처는 공공데이터포털, 서울열린데이터광장, 기상청 ASOS, 국토교통부 지반정보, "
            "국토안전관리원 시설물 데이터입니다. "
            f"원천 수집 레코드 상위 항목은 {source_text}입니다. "
            "과거 사고는 국토교통부/국토안전관리원 전국지반침하정보표준데이터가 `sinkhole_history`에 반영됩니다."
        )

    return (
        f"현재 DB에 반영된 주요 정규 데이터는 {table_text}입니다. "
        f"원천 레코드 기준 상위 수집 자료는 {source_text}입니다. "
        "점수 계산은 이 정규 테이블에서 지역별 특징값을 만들고, 과거 사고, GPR, 시설물, 강우, 지하수, 환경, 공사 영향 항목으로 합산합니다."
    )


def _fallback_answer(summary: dict[str, Any], top_rows: list[dict[str, Any]], analysis_date: str | None) -> str:
    leader = top_rows[0] if top_rows else None
    if leader:
        return (
            f"현재 데이터 기준으로는 도로명 주소 기준 {_address_label(leader)}이 {_fmt(leader['total_risk_score'])}점으로 가장 우선 관리 대상입니다. "
            f"최신 분석일은 {analysis_date or '-'}이고, 서울/수도권 평균 위험도는 {_fmt(summary['average_risk_score'])}점입니다. "
            "질문을 조금 더 구체적으로 주시면 위험한 이유, 관리 방법, 점수 낮추는 방법, 보고서 작성 방향 중 하나로 바로 설명하겠습니다."
        )
    return "현재 분석 결과가 아직 충분하지 않습니다. 먼저 위험도 분석을 실행한 뒤 다시 질문해 주세요."


def _local_chat_answer(
    message: str,
    summary: dict[str, Any],
    top_rows: list[dict[str, Any]],
    analysis_date: str | None,
    target: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    conn: sqlite3.Connection | None = None,
) -> str:
    lower = message.lower()
    if conn is not None and _is_definition_question(message):
        answer = _term_answer(message, conn)
        if answer:
            return answer
    if _contains(lower, ("목적", "뭐하는", "무슨 프로그램", "사용 목적", "시스템 설명")):
        return _purpose_answer(summary, top_rows, analysis_date)
    elif conn is not None and is_evidence_question(message):
        return build_factor_evidence_answer(conn, message, target, payload, analysis_date, _address_label(target))
    elif _contains(lower, ("전체", "현황", "요약", "상황", "현재 상태")) and not _contains(lower, ("이유", "왜")):
        return _overview_answer(summary, top_rows, analysis_date)
    elif _contains(lower, ("어디", "가장", "최고", "높은 곳", "위험지역", "위험 지역")) and not _contains(lower, ("이유", "왜", "원인", "근거")):
        return _top_region_answer(top_rows, analysis_date, payload)
    elif _contains(lower, ("관리", "대응", "낮추", "줄이", "조치", "개선", "점수", "보수", "정비", "어디서부터", "어떻게 해야")):
        return _management_answer(target, payload)
    elif _contains(lower, ("이유", "왜", "원인", "근거", "판단")):
        return _reason_answer(target, payload)
    elif conn is not None and _contains(lower, ("자료", "데이터", "출처", "원천", "공공데이터", "api", "api키", "테이블", "정규데이터")):
        return _data_answer(message, conn)
    elif _contains(lower, ("모니터링", "센서", "탐지")):
        return _monitoring_answer(summary)
    return _fallback_answer(summary, top_rows, analysis_date)


def _requires_verified_local_answer(message: str) -> bool:
    lower = message.lower()
    if _is_definition_question(message):
        return True
    if is_evidence_question(message):
        return True
    if _contains(lower, ("관리", "대응", "낮추", "줄이", "조치", "개선", "점수", "보수", "정비", "어디서부터", "어떻게 해야")):
        return True
    return _contains(
        lower,
        (
            "모니터링",
            "센서",
            "탐지",
            "최근 건수",
            "데이터 출처",
            "자료",
            "공공데이터",
            "원본 데이터",
            "정규데이터",
            "테이블",
            "api",
            "api키",
            "가짜",
            "데모",
        ),
    )


def _chat_context(
    summary: dict[str, Any],
    top_rows: list[dict[str, Any]],
    analysis_date: str | None,
    target: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    local_answer: str,
    evidence_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = payload.get("analysis") if payload else None
    features = payload.get("features") if payload else None
    breakdown = payload.get("breakdown") if payload else None
    reason_cards = payload.get("reason_cards") if payload else []
    return {
        "program_scope": "현재 시스템 DB에 등록된 서울/수도권 중심 분석 대상 기준입니다. 대한민국 전체 결과로 표현하면 안 됩니다.",
        "latest_analysis_date": analysis_date,
        "summary": {
            "region_count": int(summary.get("region_count") or 0),
            "high_risk_count": int(summary.get("high_risk_count") or 0),
            "very_high_risk_count": int(summary.get("very_high_risk_count") or 0),
            "average_risk_score": round(_num(summary.get("average_risk_score")), 1),
            "monitoring_point_count": int(summary.get("monitoring_point_count") or 0),
            "recent_detection_count": int(summary.get("recent_detection_count") or 0),
        },
        "top_regions": [
            {
                "road_address": _region_address(row),
                "risk_score": round(_num(row.get("total_risk_score")), 1),
                "risk_level": row.get("risk_level"),
                "priority_rank": row.get("priority_rank"),
            }
            for row in top_rows[:5]
        ],
        "target_region": (
            {
                "road_address": _region_address(target),
                "analysis": analysis,
                "features": features,
                "breakdown": breakdown,
                "reason_cards": reason_cards,
            }
            if target and payload
            else None
        ),
        "evidence_context": evidence_context or {},
        "safe_local_answer": local_answer,
    }


def _gemini_prompt(req: AiChatRequest, context: dict[str, Any]) -> str:
    history = [
        {"role": item.role, "content": item.content}
        for item in req.history[-8:]
        if item.content.strip()
    ]
    return f"""
당신은 지반침하/싱크홀 위험관리 대시보드의 AI 직원입니다.
사용자에게 한국어로, 현장 직원처럼 구체적이고 침착하게 답하세요.

반드시 지킬 규칙:
- 아래 제공된 CONTEXT 데이터만 근거로 답하세요. 없는 사실, 대한민국 전체 실시간 데이터, 외부 최신 뉴스는 지어내지 마세요.
- 위험 기여요인의 세부 근거를 물으면 확인된 원천 데이터와 추정을 분리하세요. 특정 시설명, 주소, 사고 원인이 CONTEXT에 없으면 없다고 말하고 만들지 마세요.
- 위치를 말할 때는 내부 키 이름을 말하지 말고, 지역명/시설명 대신 도로명 주소 문자열만 사용하세요.
- 사용자가 대한민국 전체를 물어도 "현재 시스템에 등록된 서울/수도권 중심 분석 대상 기준"이라고 분명히 말하세요.
- 위험한 이유를 물으면 점수, 등급, 주요 기여 요인을 함께 설명하세요.
- 관리 방법을 물으면 점수를 낮추기 위한 실행 조치를 말하세요.
- 질문이 범위를 벗어나면 싱크홀 위험관리 데이터 기준으로 답할 수 있는 질문을 안내하세요.
- 답변은 2~5문장으로 작성하고, 필요할 때만 짧은 번호 목록을 쓰세요.

CONTEXT:
{json.dumps(context, ensure_ascii=False, indent=2)}

RECENT_CHAT:
{json.dumps(history, ensure_ascii=False, indent=2)}

USER_QUESTION:
{req.message.strip()}
""".strip()


def _answer_with_gemini(req: AiChatRequest, context: dict[str, Any]) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    response = requests.post(
        endpoint,
        json={
            "contents": [{"parts": [{"text": _gemini_prompt(req, context)}]}],
            "generationConfig": {
                "temperature": 0.25,
                "topP": 0.9,
                "maxOutputTokens": 700,
            },
        },
        timeout=min(float(settings.gemini_timeout_seconds or 12.0), 12.0),
    )
    response.raise_for_status()
    payload = response.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    parts = ((candidates[0].get("content") or {}).get("parts") or [])
    text = "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
    if not text:
        raise RuntimeError("Gemini returned empty content")
    return text


@router.post("/api/ai-chat")
def ai_chat(req: AiChatRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    message = req.message.strip()
    analysis_date = _latest_analysis_date(conn)
    summary = _summary(conn, analysis_date)
    top_rows = _top_regions(conn, analysis_date, 5)
    target = _target_region(conn, req, top_rows)
    payload = _region_payload(conn, int(target["region_id"]), analysis_date) if target else None
    evidence_context = build_evidence_context(conn, target, payload, analysis_date)
    local_answer = _local_chat_answer(message, summary, top_rows, analysis_date, target, payload, conn)

    engine = "local_fallback"
    fallback_reason = None
    if _requires_verified_local_answer(message):
        answer = local_answer
        engine = "local_verified"
    else:
        try:
            context = _chat_context(summary, top_rows, analysis_date, target, payload, local_answer, evidence_context)
            answer = _answer_with_gemini(req, context)
            answer = _replace_known_locations(answer, top_rows, target)
            engine = "gemini"
        except Exception as exc:
            answer = local_answer
            fallback_reason = exc.__class__.__name__

    return ok(
        {
            "answer": answer,
            "engine": engine,
            "fallback_reason": fallback_reason,
            "context": {
                "analysis_date": analysis_date,
                "target_region": _with_address(target) if target else None,
                "top_regions": top_rows[:3],
                "average_risk_score": round(_num(summary["average_risk_score"]), 1),
                "evidence_factors": list(evidence_context.keys()),
            },
        "quick_questions": [
            "현재 가장 위험한 지역이 어디야?",
            "그 지역이 위험한 이유가 뭐야?",
            "현재 가장 위험한 지역의 점수를 낮추려면 공공데이터 근거를 바탕으로 어디서부터 어떤 보수·점검을 해야 해?",
            "전체 현황을 요약해줘.",
        ],
        }
    )
