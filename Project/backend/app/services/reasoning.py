from __future__ import annotations

import sqlite3
from typing import Any

from app.db.core import query_all


FACTOR_LABELS = {
    "past_sinkhole": "과거 침하 이력",
    "gpr": "GPR/공동 탐사",
    "facility": "시설물 노후도",
    "rainfall": "강우 영향",
    "groundwater": "지하수 변동",
    "environment": "환경 밀집도",
    "construction": "공사 영향",
}

FACTOR_FEATURES = {
    "past_sinkhole": ("past_sinkhole_count", "건"),
    "gpr": ("gpr_detected_count", "건"),
    "facility": ("facility_aging_score", "점"),
    "rainfall": ("rainfall_score", "점"),
    "groundwater": ("groundwater_score", "점"),
    "environment": ("environment_score", "점"),
    "construction": ("construction_score", "점"),
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value: Any, digits: int = 1) -> str:
    return f"{_num(value):.{digits}f}"


def _risk_band_sentence(score: float, level: str) -> str:
    if score >= 80:
        band = "80점 이상인 '매우 높음' 구간"
    elif score >= 60:
        band = "60점 이상 80점 미만인 '높음' 구간"
    elif score >= 30:
        band = "30점 이상 60점 미만인 '보통' 구간"
    else:
        band = "30점 미만인 '낮음' 구간"
    return f"최종 점수 {_fmt(score)}점은 {band}에 해당하므로 위험 등급은 '{level}'으로 판단됩니다."


def _top_factors(breakdown: dict[str, Any], limit: int = 3) -> list[tuple[str, float]]:
    items = [
        (key, _num(value))
        for key, value in breakdown.items()
        if key != "total" and _num(value) > 0
    ]
    return sorted(items, key=lambda item: item[1], reverse=True)[:limit]


def _join(items: list[str]) -> str:
    if not items:
        return "유의미한 상승 요인 없음"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f", {items[-1]}"


def _driver_sentence(top_factors: list[tuple[str, float]], features: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, score in top_factors:
        label = FACTOR_LABELS.get(key, key)
        feature_key, unit = FACTOR_FEATURES.get(key, ("", ""))
        raw_value = features.get(feature_key) if feature_key else None
        if raw_value is None:
            parts.append(f"{label} {_fmt(score)}점")
        else:
            parts.append(f"{label} {_fmt(score)}점(원자료 {_fmt(raw_value)}{unit})")
    return _join(parts)


def _feature_sentence(features: dict[str, Any]) -> str:
    values = [
        f"과거 침하 {_fmt(features.get('past_sinkhole_count'), 0)}건",
        f"GPR 탐지 {_fmt(features.get('gpr_detected_count'), 0)}건",
        f"시설물 노후도 {_fmt(features.get('facility_aging_score'))}점",
        f"강우 {_fmt(features.get('rainfall_score'))}점",
        f"지하수 {_fmt(features.get('groundwater_score'))}점",
        f"환경 {_fmt(features.get('environment_score'))}점",
        f"공사 {_fmt(features.get('construction_score'))}점",
    ]
    return ", ".join(values)


def _cause_sentence(cause_rows: list[dict[str, Any]] | None) -> str:
    if not cause_rows:
        return "과거 원인 분포 데이터는 충분하지 않아 현재 점수 기여 요인을 중심으로 판단했습니다."

    total = sum(int(row.get("count") or 0) for row in cause_rows)
    top = cause_rows[0]
    cause = str(top.get("cause_type") or "미상")
    count = int(top.get("count") or 0)
    ratio = (count / total * 100) if total else 0.0
    return f"과거 침하 이력 {total}건 중 '{cause}' 유형이 {count}건({ratio:.1f}%)으로 가장 많이 관측되어, 해당 유형을 우선 원인 후보로 봅니다."


def _trend_sentence(trend_rows: list[dict[str, Any]] | None) -> str:
    if not trend_rows or len(trend_rows) < 2:
        return "동일 대상의 누적 분석 이력이 적어 추세보다는 최신 단일 분석값의 영향이 큽니다."

    rows = trend_rows[-2:]
    prev = _num(rows[0].get("total_risk_score"))
    latest = _num(rows[1].get("total_risk_score"))
    diff = latest - prev
    if abs(diff) < 0.5:
        movement = "거의 유지"
    elif diff > 0:
        movement = f"{diff:.1f}점 상승"
    else:
        movement = f"{abs(diff):.1f}점 하락"
    return f"직전 분석 대비 위험 점수는 {movement}했으며, 최신 점수 {_fmt(latest)}점을 기준으로 현재 등급을 해석했습니다."


def _weather_sentence(weather: dict[str, Any] | None) -> str:
    if not weather:
        return ""
    rainfall = _num(weather.get("rainfall_7d_total"))
    temp = weather.get("temperature_avg")
    elevation = weather.get("elevation")
    details = [f"최근 7일 누적 강수량 {_fmt(rainfall)}mm"]
    if temp is not None:
        details.append(f"평균 기온 {_fmt(temp)}°C")
    if elevation is not None:
        details.append(f"해발 고도 {_fmt(elevation)}m")
    return "실시간 위치 분석에서는 " + ", ".join(details) + " 데이터를 함께 반영했습니다."


def _recommendation(score: float, level: str, top_factors: list[tuple[str, float]]) -> str:
    top_keys = {key for key, _ in top_factors}
    actions: list[str] = []
    if "gpr" in top_keys:
        actions.append("GPR 재탐사 또는 공동 위치 정밀 확인")
    if "facility" in top_keys:
        actions.append("노후 관로와 지하시설물 상태 점검")
    if "past_sinkhole" in top_keys:
        actions.append("과거 발생 지점 주변의 반복 침하 여부 확인")
    if "rainfall" in top_keys or "groundwater" in top_keys:
        actions.append("강우 이후 지하수 변동과 배수 상태 모니터링")
    if not actions:
        actions.append("정기 모니터링 유지")

    urgency = "즉시 우선 점검 대상으로 관리하는 것이 적절합니다" if score >= 80 or level == "매우 높음" else "정기 점검 계획에 반영하는 것이 적절합니다"
    return f"{_join(actions)}을 권고하며, 현재 수준에서는 {urgency}."


def build_reason_cards(
    subject_name: str,
    analysis: dict[str, Any],
    breakdown: dict[str, Any],
    features: dict[str, Any] | None = None,
    *,
    cause_rows: list[dict[str, Any]] | None = None,
    trend_rows: list[dict[str, Any]] | None = None,
    weather: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    features = features or {}
    score = _num(analysis.get("total_risk_score") or breakdown.get("total"))
    level = str(analysis.get("risk_level") or "")
    top = _top_factors(breakdown)
    driver_text = _driver_sentence(top, features)
    weather_text = _weather_sentence(weather)

    return [
        {
            "title": "AI 종합 판단",
            "badge": f"{_fmt(score)}점 / {level or '등급 미정'}",
            "body": f"{subject_name}의 위험 판단은 전체 점수, 위험 등급, 원자료 지표, 기여도 분해를 함께 비교한 결과입니다. {driver_text}이 현재 위험도를 가장 크게 끌어올렸습니다.",
            "meta": [
                {"label": "분석일", "value": str(analysis.get("analysis_date") or "-")},
                {"label": "상위 원인", "value": ", ".join(FACTOR_LABELS.get(key, key) for key, _ in top) or "-"},
            ],
        },
        {
            "title": "위험 등급 결정 원인",
            "badge": level or "등급 미정",
            "body": f"{_risk_band_sentence(score, level or '등급 미정')} 특히 상위 기여 요인이 동시에 높게 나타나 단일 요인보다 복합 위험으로 해석됩니다.",
            "meta": [
                {"label": "등급 기준", "value": "낮음<30, 보통<60, 높음<80, 매우 높음>=80"},
            ],
        },
        {
            "title": "점수 상승 요인",
            "badge": "주요 기여도",
            "body": f"점수 산정에서 가장 큰 항목은 {driver_text}입니다. 원자료 기준으로는 {_feature_sentence(features)}이 확인되어 최종 점수에 누적 반영됐습니다.",
            "meta": [
                {"label": FACTOR_LABELS.get(key, key), "value": f"{value:.1f}점"}
                for key, value in top
            ],
        },
        {
            "title": "과거 데이터와 추세",
            "badge": "근거 데이터",
            "body": f"{_cause_sentence(cause_rows)} {_trend_sentence(trend_rows)} {weather_text}".strip(),
            "meta": [
                {"label": "데이터 범위", "value": "과거 침하, GPR, 시설물, 강우, 지하수, 환경, 공사"},
            ],
        },
        {
            "title": "점검 판단",
            "badge": "권고",
            "body": _recommendation(score, level, top),
            "meta": [
                {"label": "판단 방식", "value": "규칙 기반 점수 + 원인 기여도 + 이력 데이터 종합"},
            ],
        },
    ]


def load_region_reason_context(conn: sqlite3.Connection, region_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cause_rows = query_all(
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
        LIMIT 5
        """,
        (region_id,),
    )
    trend_rows = query_all(
        conn,
        """
        SELECT analysis_date, total_risk_score, risk_level
        FROM risk_analysis_result
        WHERE region_id = ?
        ORDER BY analysis_date ASC, id ASC
        LIMIT 12
        """,
        (region_id,),
    )
    return cause_rows, trend_rows


def load_road_reason_context(conn: sqlite3.Connection, road_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cause_rows = query_all(
        conn,
        """
        SELECT
            COALESCE(cause_type, '미상') AS cause_type,
            COUNT(*) AS count,
            ROUND(COALESCE(AVG(damage_scale), 0), 2) AS avg_damage_scale
        FROM road_sinkhole_history
        WHERE road_id = ?
        GROUP BY COALESCE(cause_type, '미상')
        ORDER BY count DESC, avg_damage_scale DESC, cause_type ASC
        LIMIT 5
        """,
        (road_id,),
    )
    trend_rows = query_all(
        conn,
        """
        SELECT analysis_date, total_risk_score, risk_level
        FROM road_risk_analysis_result
        WHERE road_id = ?
        ORDER BY analysis_date ASC, id ASC
        LIMIT 12
        """,
        (road_id,),
    )
    return cause_rows, trend_rows
