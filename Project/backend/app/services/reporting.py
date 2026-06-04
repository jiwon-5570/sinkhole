from __future__ import annotations

from datetime import datetime
import sqlite3
from typing import Any

import requests

from app.config.settings import settings
from app.db.core import query_one
from app.services.addressing import region_road_address
from app.services.risk_scoring import FACTOR_MAX_SCORES


REPORT_TEMPLATE_VERSION = "operational-risk-report-v3-20260519"

FACTOR_LABELS_KO = {
    "past_sinkhole": "과거 지반침하 사고",
    "gpr": "GPR/탐사 이상 신호",
    "facility": "시설물 및 노후도",
    "rainfall": "강우 영향",
    "groundwater": "지하수 변동",
    "environment": "환경/지층 요인",
    "construction": "굴착/공사 영향",
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

FEATURE_UNITS = {
    "past_sinkhole_count": "건",
    "gpr_detected_count": "건 상당",
    "facility_aging_score": "원자료 점",
    "rainfall_score": "점",
    "groundwater_score": "점",
    "environment_score": "점",
    "construction_score": "원자료 점",
}

STATUS_LABELS = {
    "confirmed": "직접 원자료 반영",
    "estimated": "대체 지표 기반 추정",
    "missing": "직접 원자료 부족",
}

DATA_SOURCES = {
    "past_sinkhole": "국토교통부/국토안전관리원 지반침하 이력 데이터",
    "gpr": "GPR 탐사 데이터, 국토교통부 물리탐사/지반정보 보조 데이터",
    "facility": "국토안전관리원 시설물 안전관리/점검/사고 데이터, 노후 시설물 데이터",
    "rainfall": "기상청 ASOS 및 서울 열린데이터광장 강우 데이터",
    "groundwater": "서울 열린데이터광장 지하수 관측망, 국토교통부 시추공 지하수위 데이터",
    "environment": "환경 밀집도, 도로 밀도, 국토교통부 지층/시추공 보조 데이터",
    "construction": "서울 도로굴착 공사 파일/API 데이터, 지하안전/굴착 관련 공공데이터",
}

ACTION_GUIDE = {
    "past_sinkhole": (
        "과거 사고 주소 주변의 포장 처짐, 균열, 보수부, 하수관 접합부를 우선 현장 확인하고 "
        "반복 사고 구간은 CCTV 관로 조사와 GPR 재탐사를 묶어 시행합니다."
    ),
    "gpr": (
        "탐사 이상 신호가 있는 경우 공동 위치와 규모를 재확인하고, 공동 의심 구간은 굴착 전 "
        "교통 통제와 보수 계획을 먼저 수립합니다."
    ),
    "facility": (
        "노후 관로, 맨홀, 지하시설물의 누수와 접합부 이탈 가능성을 점검하고, 고위험 시설은 "
        "보수/교체 우선순위를 별도 관리합니다."
    ),
    "rainfall": (
        "집중호우 전후로 포장 침하, 배수 불량, 토사 유출 흔적을 순찰하고 강우 종료 후 "
        "24~72시간 동안 위험 구간을 재점검합니다."
    ),
    "groundwater": (
        "지하수위 급변 구간은 관측정 수위 변화를 추적하고, 굴착·양수·누수 가능성과 함께 "
        "검토합니다."
    ),
    "environment": (
        "건물/도로 밀집도가 높거나 취약 지층 가능성이 있는 구간은 점검 간격을 줄이고, "
        "지층 데이터가 부족하면 추가 시추 또는 지반조사를 검토합니다."
    ),
    "construction": (
        "굴착 공사 인접 구간은 흙막이, 되메우기, 배수, 진동 관리 상태를 확인하고 공사 일정과 "
        "모니터링 계획을 연동합니다."
    ),
}


def cached_report(conn: sqlite3.Connection, region_id: int, analysis_date: str) -> str | None:
    row = query_one(
        conn,
        "SELECT report_text FROM ai_report WHERE region_id = ? AND analysis_date = ?",
        (region_id, analysis_date),
    )
    if not row:
        return None
    text = str(row["report_text"] or "")
    if REPORT_TEMPLATE_VERSION not in text:
        return None
    return text


def store_report(conn: sqlite3.Connection, region_id: int, analysis_date: str, text: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO ai_report(region_id, analysis_date, report_text, created_at)
        VALUES(?, ?, ?, ?)
        """,
        (region_id, analysis_date, text, datetime.utcnow().isoformat(timespec="seconds") + "Z"),
    )


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value: Any, digits: int = 1) -> str:
    number = _num(value)
    if abs(number - round(number)) < 0.0001:
        return str(int(round(number)))
    return f"{number:.{digits}f}"


def _as_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        return {key: value[key] for key in value.keys()}
    except AttributeError:
        return dict(value)


def _top_factors(breakdown: dict[str, Any], limit: int = 4) -> list[tuple[str, float]]:
    ranked = sorted(
        ((key, _num(value)) for key, value in breakdown.items() if key in FACTOR_LABELS_KO),
        key=lambda item: item[1],
        reverse=True,
    )
    return [(key, value) for key, value in ranked if value > 0][:limit]


def _status_label(status: str | None) -> str:
    return STATUS_LABELS.get(str(status or "").strip(), str(status or "확인 필요"))


def _trend_summary(trend_data: list[dict] | None, current_score: float) -> str:
    rows = [dict(row) for row in (trend_data or []) if row]
    if len(rows) < 2:
        return "동일 지역의 과거 분석 이력이 부족하여 추세 판단은 현재 점수 중심으로 제한합니다."
    first = _num(rows[0].get("total_risk_score"))
    last = _num(rows[-1].get("total_risk_score"), current_score)
    delta = last - first
    direction = "상승" if delta > 0.5 else "하락" if delta < -0.5 else "유지"
    return (
        f"{rows[0].get('analysis_date')} 대비 {rows[-1].get('analysis_date')} 점수 변화는 "
        f"{delta:+.1f}점으로, 최근 추세는 '{direction}'으로 판단됩니다."
    )


def _cause_summary(history_cause: list[dict] | None) -> str:
    rows = [dict(row) for row in (history_cause or []) if row]
    if not rows:
        return "원인 유형별 과거 사고 분포를 계산할 수 있는 이력 데이터가 없습니다."
    parts = []
    for row in rows[:5]:
        label = str(row.get("cause_type") or "미상").strip() or "미상"
        parts.append(f"{label} {int(_num(row.get('count')))}건")
    return ", ".join(parts)


def _feature_line(features: dict[str, Any], factor_key: str) -> str:
    feature_key = FACTOR_FEATURE_KEYS[factor_key]
    value = _fmt(features.get(feature_key))
    unit = FEATURE_UNITS.get(feature_key, "")
    return f"{value}{unit}"


def _factor_line(
    factor_key: str,
    contribution: float,
    features: dict[str, Any],
    evidence_context: dict[str, Any],
) -> str:
    label = FACTOR_LABELS_KO[factor_key]
    max_score = FACTOR_MAX_SCORES[factor_key]
    evidence = evidence_context.get(factor_key) or {}
    status = _status_label(evidence.get("status"))
    feature_text = _feature_line(features, factor_key)
    return f"- {label}: {contribution:.1f}/{max_score:.0f}점, 원자료 지표 {feature_text}, 근거 상태: {status}"


def _data_status_summary(evidence_context: dict[str, Any]) -> str:
    if not evidence_context:
        return "요인별 세부 근거 컨텍스트가 없어 데이터 신뢰도는 점수 산정용 feature 기준으로만 판단했습니다."
    counts = {"confirmed": 0, "estimated": 0, "missing": 0}
    for item in evidence_context.values():
        status = str((item or {}).get("status") or "missing")
        counts[status if status in counts else "missing"] += 1
    return (
        f"직접 원자료 반영 {counts['confirmed']}개, 대체 지표 기반 추정 {counts['estimated']}개, "
        f"직접 원자료 부족 {counts['missing']}개 요인으로 구성됩니다."
    )


def _risk_decision_text(level: str, score: float) -> str:
    if score >= 80:
        return "즉시 현장 확인과 관계기관 공유가 필요한 최우선 관리 대상입니다."
    if score >= 60:
        return "단기 점검 대상으로 지정하고, 강우·공사 일정과 연동한 집중 모니터링이 필요합니다."
    if score >= 30:
        return "상시 관리 대상입니다. 상위 기여 요인의 원자료가 증가하면 우선순위를 올려야 합니다."
    return "현재 점수만으로는 긴급 위험 신호가 낮지만, 데이터 공백과 신규 공사/강우 이벤트는 계속 확인해야 합니다."


def _evidence_block(
    factor_key: str,
    contribution: float,
    evidence_context: dict[str, Any],
) -> list[str]:
    label = FACTOR_LABELS_KO[factor_key]
    evidence = evidence_context.get(factor_key) or {}
    lines = [
        f"[{label}]",
        f"- 점수 기여: {contribution:.1f}/{FACTOR_MAX_SCORES[factor_key]:.0f}점",
        f"- 근거 상태: {_status_label(evidence.get('status'))}",
        f"- 산정 방식: {evidence.get('formula') or '현재 위험도 산정 엔진의 가중치 규칙을 적용했습니다.'}",
        f"- 실제 근거: {evidence.get('summary') or '세부 원자료가 현재 리포트 컨텍스트에 없습니다.'}",
        f"- 관리 방향: {ACTION_GUIDE[factor_key]}",
        f"- 주의 사항: {evidence.get('limitation') or '세부 원자료가 없는 항목은 확정 원인으로 표현하지 않습니다.'}",
    ]
    if str(evidence.get("status") or "") == "estimated":
        lines.append("- 추정 표시: 이 항목은 직접 관측값이 아니라 대체 공공데이터를 활용한 추정 지표입니다.")
    return lines


def build_professional_report(
    *,
    region: dict,
    analysis: dict,
    breakdown: dict,
    features: dict[str, Any] | None = None,
    evidence_context: dict[str, Any] | None = None,
    trend_data: list[dict] | None = None,
    history_cause: list[dict] | None = None,
    analysis_local_time: str | None = None,
) -> str:
    region = _as_dict(region)
    analysis = _as_dict(analysis)
    features = _as_dict(features)
    evidence_context = evidence_context or {}

    score = _num(analysis.get("total_risk_score"))
    level = str(analysis.get("risk_level") or "")
    top_factors = _top_factors(breakdown, limit=4)

    lines: list[str] = [
        "[보고서 형식] 운영형 상세 분석 리포트",
        "",
        "1. 분석 개요",
        f"- 대상 지역: {region.get('region_name') or '-'}",
        f"- 도로명 주소/대표 주소: {region_road_address(region)}",
        f"- 행정구역: {region.get('sido') or '-'} {region.get('sigungu') or '-'}",
        f"- 분석일: {analysis.get('analysis_date') or '-'}",
        f"- 생성 시각: {analysis_local_time or '-'}",
        "- 분석 성격: 이 결과는 싱크홀 발생 확률을 단정하는 예측값이 아니라, 공공데이터와 파일 데이터를 종합해 사전 점검 우선순위를 정하기 위한 위험도 상대지표입니다.",
        "",
        "2. 종합 판단",
        f"- 종합 위험도: {score:.1f}/100점",
        f"- 위험 등급: {level or '-'}",
        f"- 운영 판단: {_risk_decision_text(level, score)}",
        f"- 최근 추세: {_trend_summary(trend_data, score)}",
        f"- 과거 사고 원인 분포: {_cause_summary(history_cause)}",
        "",
        "3. 점수 산정 결과",
    ]

    for factor_key, contribution in sorted(
        ((key, _num(value)) for key, value in breakdown.items() if key in FACTOR_LABELS_KO),
        key=lambda item: item[1],
        reverse=True,
    ):
        lines.append(_factor_line(factor_key, contribution, features, evidence_context))

    lines.extend(
        [
            "",
            "4. 핵심 위험 요인 상세 근거",
        ]
    )
    if top_factors:
        for factor_key, contribution in top_factors:
            lines.extend(_evidence_block(factor_key, contribution, evidence_context))
            lines.append("")
    else:
        lines.append("- 현재 0점을 초과하는 주요 기여 요인이 없어 세부 근거는 데이터 수집 상태 중심으로 확인해야 합니다.")
        lines.append("")

    lines.extend(
        [
            "5. 권고 조치",
            "- 우선 점검: 점수 기여도가 높은 상위 요인부터 현장 점검 대상을 배정합니다.",
            "- 현장 확인: 지도 위치 주변의 포장 침하, 균열, 맨홀 단차, 배수 불량, 공사 복구부를 확인합니다.",
            "- 정밀 조사: 과거 사고·GPR·시설물 노후도 중 2개 이상이 동시에 높은 구간은 GPR 재탐사와 관로 CCTV 조사를 우선 검토합니다.",
            "- 모니터링: 집중호우, 지하수위 급변, 도로굴착 공사 기간에는 동일 위치를 모니터링 지점으로 등록해 재평가합니다.",
            "- 점수 저감: 원인이 확인된 노후 관로 보수, 누수 차단, 되메우기 품질 확인, 배수 개선, 공사장 계측 관리를 완료한 뒤 데이터를 갱신해 재산정합니다.",
            "",
            "6. 데이터 신뢰도 및 한계",
            f"- 데이터 상태 요약: {_data_status_summary(evidence_context)}",
            "- 직접 원자료가 없는 항목은 확정 원인으로 쓰지 않고, 대체 지표 또는 추정 지표로 구분해야 합니다.",
            "- 점수는 행정 의사결정을 위한 우선순위 지표이며, 실제 지반침하 발생 여부는 현장 조사와 계측으로 확정해야 합니다.",
            "- 주소 매칭, 관측소 매핑, 공사 위치 좌표가 부정확하면 특정 지역 점수가 과대 또는 과소 산정될 수 있습니다.",
            "",
            "7. 점검 체크리스트",
            "- 과거 사고 주소 반경 내 반복 침하 흔적 확인",
            "- 하수관/상수관/맨홀 접합부 누수 및 공동 가능성 확인",
            "- 최근 굴착 공사 구간의 복구 상태와 배수 상태 확인",
            "- 강우 후 24~72시간 내 포장 침하와 배수 불량 재점검",
            "- 지하수 관측값 또는 시추공 자료가 부족한 경우 추가 관측 지점 확보",
            "",
            "8. 사용 데이터 출처",
        ]
    )
    for factor_key, label in FACTOR_LABELS_KO.items():
        lines.append(f"- {label}: {DATA_SOURCES[factor_key]}")

    lines.extend(
        [
            "",
            f"[보고서 버전] {REPORT_TEMPLATE_VERSION}",
        ]
    )
    return "\n".join(lines)


def _gemini_prompt(
    region: dict,
    analysis: dict,
    breakdown: dict,
    features: dict[str, Any],
    evidence_context: dict[str, Any] | None = None,
    trend_data: list[dict] | None = None,
    history_cause: list[dict] | None = None,
    analysis_local_time: str | None = None,
    language: str = "한국어",
) -> str:
    base_report = build_professional_report(
        region=region,
        analysis=analysis,
        breakdown=breakdown,
        features=features,
        evidence_context=evidence_context,
        trend_data=trend_data,
        history_cause=history_cause,
        analysis_local_time=analysis_local_time,
    )
    return f"""
당신은 지반침하 위험도 평가 보고서를 작성하는 재난안전 분석 보조 엔진이다.
아래 원본 보고서에 포함된 사실만 사용해 {language}로 운영 보고서 문체를 다듬어라.
새로운 시설명, 사고 원인, 주소, 수치, 출처를 만들면 안 된다.
직접 원자료가 없거나 대체 지표인 항목은 반드시 '추정' 또는 '자료 부족'이라고 표시한다.
분량은 원본보다 짧게 줄이지 말고, 8개 섹션 구조를 유지한다.

[원본 보고서]
{base_report}
""".strip()


def generate_report_with_gemini(
    region: dict,
    analysis: dict,
    breakdown: dict,
    features: dict[str, Any],
    evidence_context: dict[str, Any] | None = None,
    trend_data: list[dict] | None = None,
    history_cause: list[dict] | None = None,
    analysis_local_time: str | None = None,
    language: str = "한국어",
) -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    prompt = _gemini_prompt(
        region,
        analysis,
        breakdown,
        features,
        evidence_context=evidence_context,
        trend_data=trend_data,
        history_cause=history_cause,
        analysis_local_time=analysis_local_time,
        language=language,
    )
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    response = requests.post(
        endpoint,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.15,
                "topP": 0.85,
                "maxOutputTokens": 2200,
            },
        },
        timeout=settings.gemini_timeout_seconds,
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
    if REPORT_TEMPLATE_VERSION not in text:
        text = text.rstrip() + f"\n\n[보고서 버전] {REPORT_TEMPLATE_VERSION}"
    return text


def template_report(
    region: dict,
    analysis: dict,
    breakdown: dict,
    features: dict[str, Any] | None = None,
    evidence_context: dict[str, Any] | None = None,
    trend_data: list[dict] | None = None,
    history_cause: list[dict] | None = None,
    analysis_local_time: str | None = None,
    language: str = "ko",
) -> str:
    return build_professional_report(
        region=region,
        analysis=analysis,
        breakdown=breakdown,
        features=features,
        evidence_context=evidence_context,
        trend_data=trend_data,
        history_cause=history_cause,
        analysis_local_time=analysis_local_time,
    )
