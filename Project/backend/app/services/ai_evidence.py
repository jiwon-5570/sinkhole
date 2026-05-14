from __future__ import annotations

import re
import sqlite3
from typing import Any

from app.db.core import query_all, query_one
from app.services.reasoning import FACTOR_LABELS


FACTOR_ORDER = (
    "past_sinkhole",
    "gpr",
    "facility",
    "rainfall",
    "groundwater",
    "environment",
    "construction",
)

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

DETAIL_TERMS = (
    "왜",
    "근거",
    "정확",
    "어느",
    "어떤",
    "데이터",
    "자료",
    "점수",
    "산정",
    "계산",
    "원인",
    "영향",
    "때문",
    "관련",
    "맞아",
)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value: Any, digits: int = 1) -> str:
    return f"{_num(value):.{digits}f}"


def _normalize(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(value), flags=re.UNICODE).lower()


def detect_factor_key(message: str) -> str | None:
    normalized = _normalize(message)
    matches: list[tuple[int, str]] = []
    for key, keywords in FACTOR_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = _normalize(keyword)
            if normalized_keyword and normalized_keyword in normalized:
                matches.append((len(normalized_keyword), key))
    if not matches:
        return None
    return sorted(matches, key=lambda item: item[0], reverse=True)[0][1]


def is_evidence_question(message: str) -> bool:
    normalized = _normalize(message)
    if not normalized:
        return False
    has_factor = detect_factor_key(message) is not None or any(
        _normalize(word) in normalized
        for word in ("위험기여요인", "기여요인", "기여도", "위험요인")
    )
    asks_detail = any(_normalize(word) in normalized for word in DETAIL_TERMS)
    return has_factor and asks_detail


def _join(items: list[str], *, empty: str) -> str:
    return "; ".join(items[:5]) if items else empty


def _row_label(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return "-"


SOURCE_LABELS = {
    "ground_subsidence_accident": "국토교통부/국토안전관리원 지반침하 사고 공공데이터",
    "molit_ground_subsidence": "국토교통부 지반침하 공공데이터",
    "seoul_open_data": "서울 열린데이터광장 공공데이터",
}


def _source_label(value: Any) -> str:
    source = str(value or "").strip()
    return SOURCE_LABELS.get(source, source or "출처 미기록")


def _factor_values(factor_key: str, payload: dict[str, Any]) -> tuple[float, float]:
    features = payload.get("features") or {}
    breakdown = payload.get("breakdown") or {}
    feature_key = FACTOR_FEATURE_KEYS.get(factor_key, "")
    return _num(features.get(feature_key)), _num(breakdown.get(factor_key))


def _factor_formula_text(factor_key: str, feature_value: float, contribution: float) -> str:
    if factor_key == "past_sinkhole":
        return f"산식은 min(30, 과거 침하 건수 x 8)입니다. 원자료 {feature_value:.1f}건이 반영되어 {contribution:.1f}점입니다."
    if factor_key == "gpr":
        return f"산식은 min(30, GPR/탐사 지표 x 12)입니다. 원자료 {feature_value:.1f}건 상당이 반영되어 {contribution:.1f}점입니다."
    if factor_key == "facility":
        uncapped = feature_value * 0.25
        cap_text = "상한 15점에 걸려 15점으로 제한됐습니다" if uncapped > 15 else "상한에는 걸리지 않았습니다"
        return f"산식은 min(15, 시설물 노후도 원자료 지표 x 0.25)입니다. {feature_value:.1f} x 0.25 = {uncapped:.1f}점이고, {cap_text}."
    if factor_key == "rainfall":
        return f"최근 7일 강우 지표를 0~10점 범위로 반영합니다. 현재 원자료 {feature_value:.1f}점이 {contribution:.1f}점으로 반영됐습니다."
    if factor_key == "groundwater":
        return f"지하수 변동 또는 시추공 지하수위 대체 지표를 0~8점 범위로 반영합니다. 현재 원자료 {feature_value:.1f}점이 {contribution:.1f}점으로 반영됐습니다."
    if factor_key == "environment":
        return f"건물/도로 밀집도와 지층 보정값을 0~6점 범위로 반영합니다. 현재 원자료 {feature_value:.1f}점이 {contribution:.1f}점으로 반영됐습니다."
    if factor_key == "construction":
        uncapped = feature_value * 0.2
        cap_text = "상한 4점에 걸렸습니다" if uncapped > 4 else "상한에는 걸리지 않았습니다"
        return f"산식은 min(4, 공사 영향 원자료 지표 x 0.2)입니다. {feature_value:.1f} x 0.2 = {uncapped:.1f}점이고, {cap_text}."
    return f"원자료 {feature_value:.1f}, 기여점수 {contribution:.1f}점입니다."


def _facility_context(conn: sqlite3.Connection, region_id: int) -> dict[str, Any]:
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
    status_text = _join(
        [
            f"{_row_label(row, 'facility_name')}({row.get('facility_type') or '-'}, {row.get('address') or '주소 없음'}, 노후비율 {_fmt(row.get('aging_ratio'))})"
            for row in status_rows
        ],
        empty="facility_status에 세부 시설 행이 없습니다.",
    )
    inspection_text = _join(
        [
            f"{_row_label(row, 'facility_name')}({row.get('facility_type') or '-'}, {row.get('address') or '주소 없음'}, 점검 {row.get('inspection_date') or '-'}, 위험지표 {_fmt(row.get('risk_score'))})"
            for row in inspection_rows
        ],
        empty="facility_inspection에 점검 행이 없습니다.",
    )
    types = {str(row.get("facility_type") or "") for row in [*status_rows, *inspection_rows] if row.get("facility_type")}
    pipe_like = any(("관" in item or "상수" in item or "하수" in item) for item in types)
    return {
        "status": "confirmed" if status_rows or inspection_rows else "missing",
        "summary": (
            f"facility_status 집계는 {int(summary.get('row_count') or 0)}행, 총 {int(summary.get('total_count') or 0)}개 중 "
            f"노후 {int(summary.get('aging_count') or 0)}개, 평균 노후비율 {_fmt(summary.get('avg_aging_ratio'))}입니다. "
            f"노후 근거 행: {status_text}. 점검 위험도 상위 행: {inspection_text}."
        ),
        "limitation": (
            "현재 세부 행에는 관로로 확인되는 시설 유형도 포함되어 있어 관로 점검을 우선 검토할 수 있습니다."
            if pipe_like
            else "현재 확인된 세부 행은 주로 건축물/시설 단위입니다. 노후 관로가 직접 원인이라고 단정하지 말고, 관로 영향은 별도 상하수도/GPR 점검으로 확인해야 합니다."
        ),
        "rows": {"facility_status": status_rows, "facility_inspection": inspection_rows},
    }


def _past_sinkhole_context(conn: sqlite3.Connection, region_id: int) -> dict[str, Any]:
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
    count_row = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM sinkhole_history
        WHERE region_id = ?
        """,
        (region_id,),
    ) or {}
    cause_rows = query_all(
        conn,
        """
        SELECT
            COALESCE(NULLIF(TRIM(cause_type), ''), '미상') AS cause_type,
            COUNT(*) AS count
        FROM sinkhole_history
        WHERE region_id = ?
        GROUP BY COALESCE(NULLIF(TRIM(cause_type), ''), '미상')
        ORDER BY count DESC, cause_type ASC
        LIMIT 5
        """,
        (region_id,),
    )
    total_count = int(count_row.get("count") or 0)
    accident_list = _join(
        [
            (
                f"{row.get('occurrence_date') or '-'} {row.get('address') or '주소 없음'}"
                f" / 원인 {row.get('cause_type') or '미상'}"
                f" / 규모 {_fmt(row.get('damage_scale'))}"
                f" / 출처 {_source_label(row.get('source_name'))}"
            )
            for row in rows
        ],
        empty="sinkhole_history에 과거 침하 사고 행이 없습니다.",
    )
    cause_distribution = _join(
        [f"{row.get('cause_type')}: {int(row.get('count') or 0)}건" for row in cause_rows],
        empty="원인 분포를 계산할 과거 사고 데이터가 없습니다.",
    )
    return {
        "status": "confirmed" if rows else "missing",
        "summary": (
            f"총 {total_count}건이 sinkhole_history에 들어 있습니다. "
            f"주요 사고: {accident_list} 원인 분포: {cause_distribution}"
        ),
        "impact": (
            "과거 사고는 같은 생활권 또는 도로축에서 이미 지반 약화, 매설물 손상, 되메우기 불량, "
            "배수 불량 같은 취약 조건이 관측됐다는 신호입니다. 그래서 현재 공동이 확정됐다는 뜻은 아니지만, "
            "비슷한 관로·굴착복구부·도로 구조가 반복되는 구간에서는 토사 유실 통로가 다시 생기거나 "
            "기존 보수부 주변이 약해질 가능성을 높이는 반복 취약성 지표로 반영합니다."
        ),
        "management": (
            "과거 사고 주소를 기준으로 주변 관로 CCTV/GPR 탐사, 포장 처짐·균열 현장 점검, "
            "과거 복구부 보수 이력 확인을 우선 진행해야 합니다. 원인이 하수관·상수관·기타 매설물 손상이면 "
            "해당 매설물 관리기관의 보수 완료 여부를 확인하고, 되메우기·굴착 관련 원인이면 굴착복구 품질과 "
            "추가 침하 여부를 재점검해야 점수를 낮출 수 있습니다."
        ),
        "inference_note": (
            "위 영향 설명은 과거 사고 위치와 원인 유형을 근거로 한 데이터 기반 추정입니다. "
            "현재 같은 지점에 공동이나 누수가 존재한다는 확정 판단은 현장조사 또는 최신 탐지 데이터가 있어야 합니다."
        ),
        "limitation": "과거 사고는 반복 위험의 근거지만, 현재 같은 위치에서 침하가 진행 중이라는 뜻은 아닙니다.",
        "accident_count": total_count,
        "accident_list": accident_list,
        "cause_distribution": cause_distribution,
        "rows": rows,
    }


def _gpr_context(conn: sqlite3.Connection, region_id: int) -> dict[str, Any]:
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
    direct = _join(
        [
            f"{row.get('inspection_date') or '-'} {row.get('address') or '주소 없음'} / 공동 {int(row.get('cavity_count') or 0)}건 / 심도 {_fmt(row.get('depth_estimate'))}m"
            for row in gpr_rows
        ],
        empty="gpr_inspection에 직접 공동 탐지 행이 없습니다.",
    )
    aggregate = _join(
        [
            f"{row.get('survey_point_name') or row.get('address') or '위치명 없음'} / 방법 {row.get('survey_method') or '-'} / 연장 {_fmt(row.get('survey_length_m'))}m"
            for row in geo_rows
        ],
        empty="molit_aggregate_geophysics에 보조 탐사 행이 없습니다.",
    )
    return {
        "status": "confirmed" if gpr_rows else "estimated" if geo_rows else "missing",
        "summary": f"직접 GPR 근거: {direct}. 보조 물리탐사 근거: {aggregate}.",
        "limitation": "직접 공동 탐지 행이 없고 보조 탐사만 있으면 공동이 확인됐다고 말하지 않고 탐사 가능성 지표로만 봅니다.",
        "rows": {"gpr_inspection": gpr_rows, "molit_aggregate_geophysics": geo_rows},
    }


def _rainfall_context(conn: sqlite3.Connection, region_id: int, analysis_date: str | None) -> dict[str, Any]:
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
    return {
        "status": "confirmed" if rows else "missing",
        "summary": _join(
            [f"{row.get('record_date')}: {row.get('rainfall') or 0}mm(관측소 {row.get('stations') or '-'})" for row in rows],
            empty="weather_data에 분석일 기준 최근 7일 강우 행이 없습니다.",
        ),
        "limitation": "강우는 실제 침하 확정 근거가 아니라 단기 지반 약화 가능성을 올리는 보조 변수입니다. 관측소명이 대상 지역과 맞지 않으면 데이터 매핑 점검이 필요합니다.",
        "rows": rows,
    }


def _groundwater_context(conn: sqlite3.Connection, region_id: int, target: dict[str, Any] | None) -> dict[str, Any]:
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
        return {
            "status": "confirmed",
            "summary": _join(
                [
                    f"{row.get('record_date') or '-'} {row.get('station_name') or '-'} / 수위 {_fmt(row.get('groundwater_level'))} / 변동 {_fmt(row.get('variation'))}"
                    for row in rows
                ],
                empty="",
            ),
            "limitation": "지하수 관측값이 있을 때는 최근 변동폭을 우선 반영합니다.",
            "rows": rows,
        }

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
    return {
        "status": "estimated" if borehole_rows else "missing",
        "summary": _join(
            [
                f"{row.get('borehole_code') or '-'} {row.get('address') or row.get('project_name') or '주소 없음'} / 지하수위 {_fmt(row.get('groundwater_level_m'))}m / 굴진심도 {_fmt(row.get('total_depth_m'))}m"
                for row in borehole_rows
            ],
            empty="groundwater_data와 근접 시추공 지하수위 행이 없습니다.",
        ),
        "limitation": "직접 지하수 관측값이 없으면 국토교통부 시추공 지하수위로 대체 추정합니다. 이 경우는 확정 관측이 아니라 대체 지표입니다.",
        "rows": {"groundwater_data": rows, "molit_ground_boreholes": borehole_rows},
    }


def _environment_context(conn: sqlite3.Connection, region_id: int, features: dict[str, Any]) -> dict[str, Any]:
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
    ground_layer = features.get("ground_layer_summary") or {}
    layer_text = (
        f"지층 보정은 근접 지층 {int(ground_layer.get('nearby_count') or 0)}건, 지층 점수 {_fmt(ground_layer.get('score'))}점입니다."
        if ground_layer
        else "지층 보정 정보는 현재 payload에 없습니다."
    )
    return {
        "status": "confirmed" if rows else "estimated" if ground_layer else "missing",
        "summary": _join(
            [
                f"{row.get('land_use_type') or '-'} / 건물밀도 {_fmt(row.get('building_density'))} / 도로밀도 {_fmt(row.get('road_density'))}"
                for row in rows
            ],
            empty="environment_features에 환경 밀집도 행이 없습니다.",
        ) + f". {layer_text}",
        "limitation": "환경 점수는 개별 사고 원인 확정이 아니라 밀집도와 지층 취약성의 배경 위험 지표입니다.",
        "rows": {"environment_features": rows, "ground_layer_summary": ground_layer},
    }


def _construction_context(conn: sqlite3.Connection, region_id: int) -> dict[str, Any]:
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
    return {
        "status": "confirmed" if rows else "missing",
        "summary": _join(
            [
                f"{row.get('construction_type') or '-'} / 시작 {row.get('start_date') or '-'} / 규모지표 {_fmt(row.get('scale_score'))} / 주소 {row.get('address') or '주소 없음'} / 출처 {row.get('source_name') or '-'}"
                for row in rows
            ],
            empty="construction_events에 공사 행이 없습니다.",
        ),
        "limitation": "공사 행은 굴착·지하안전평가·건축허가 등 공사 영향 가능성을 뜻하며, 실제 지반침하 원인 확정은 현장 확인이 필요합니다.",
        "rows": rows,
    }


def query_factor_evidence(
    conn: sqlite3.Connection,
    factor_key: str,
    target: dict[str, Any],
    payload: dict[str, Any],
    analysis_date: str | None,
) -> dict[str, Any]:
    region_id = int(target.get("region_id") or 0)
    features = payload.get("features") or {}
    feature_value, contribution = _factor_values(factor_key, payload)
    if factor_key == "facility":
        context = _facility_context(conn, region_id)
    elif factor_key == "past_sinkhole":
        context = _past_sinkhole_context(conn, region_id)
    elif factor_key == "gpr":
        context = _gpr_context(conn, region_id)
    elif factor_key == "rainfall":
        context = _rainfall_context(conn, region_id, analysis_date)
    elif factor_key == "groundwater":
        context = _groundwater_context(conn, region_id, target)
    elif factor_key == "environment":
        context = _environment_context(conn, region_id, features)
    elif factor_key == "construction":
        context = _construction_context(conn, region_id)
    else:
        context = {
            "status": "missing",
            "summary": "해당 위험 기여요인의 세부 근거 조회 로직이 없습니다.",
            "limitation": "근거 로직이 없으면 임의로 설명하지 않습니다.",
            "rows": [],
        }
    return {
        "factor_key": factor_key,
        "label": FACTOR_LABELS.get(factor_key, factor_key),
        "feature_value": feature_value,
        "contribution": contribution,
        "formula": _factor_formula_text(factor_key, feature_value, contribution),
        **context,
    }


def build_evidence_context(
    conn: sqlite3.Connection,
    target: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    analysis_date: str | None,
) -> dict[str, Any]:
    if not target or not payload:
        return {}
    return {
        key: query_factor_evidence(conn, key, target, payload, analysis_date)
        for key in FACTOR_ORDER
    }


def build_factor_evidence_answer(
    conn: sqlite3.Connection,
    message: str,
    target: dict[str, Any] | None,
    payload: dict[str, Any] | None,
    analysis_date: str | None,
    target_label: str,
) -> str:
    if not target or not payload:
        return "위험 기여요인을 설명할 대상 지역을 찾지 못했습니다. 지역명이나 도로명 주소를 함께 질문해 주세요."

    factor_key = detect_factor_key(message)
    if factor_key is None:
        context = build_evidence_context(conn, target, payload, analysis_date)
        lines = [
            f"{item['label']}: 원자료 {item['feature_value']:.1f}, 기여 {item['contribution']:.1f}점, 근거상태 {item['status']}"
            for item in context.values()
        ]
        return (
            f"{target_label}의 위험 기여요인은 다음과 같습니다.\n"
            + "\n".join(f"- {line}" for line in lines)
            + "\n세부 근거가 필요하면 '시설물 노후도 근거', '공사 영향 근거', '지하수 점수 근거'처럼 항목명을 지정해 주세요. "
            "없는 원천 데이터는 만들지 않고, 대체 지표는 추정이라고 분리해 답합니다."
        )

    item = query_factor_evidence(conn, factor_key, target, payload, analysis_date)
    if factor_key == "past_sinkhole":
        return (
            f"{target_label}의 {item['label']} 기여점수는 {item['contribution']:.1f}점입니다. "
            f"{item['formula']}\n\n"
            f"공공데이터 근거: {item['accident_count']}건의 과거 지반침하 사고가 반영됐습니다. "
            f"상세 이력은 {item['accident_list']}입니다. 원인 분포는 {item['cause_distribution']}입니다.\n\n"
            f"싱크홀 위험에 미치는 영향: {item['impact']}\n\n"
            f"관리 및 점수 저감 방향: {item['management']}\n\n"
            f"주의: {item['limitation']} 확인되지 않은 사고나 원인은 만들지 않습니다.\n\n"
            f"추측: {item['inference_note']}"
        )
    return (
        f"{target_label}의 {item['label']} 기여점수는 {item['contribution']:.1f}점입니다. {item['formula']}\n\n"
        f"실제 데이터 근거: {item['summary']}\n\n"
        f"주의: {item['limitation']} 이 답변은 현재 DB에 들어온 공공데이터와 파일데이터만 근거로 하며, 확인되지 않은 시설명이나 원인은 만들지 않습니다."
    )
