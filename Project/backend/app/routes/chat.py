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
    101: "경상남도 진주시 진주대로 501",
    102: "경상남도 진주시 진주역로 130",
    103: "경상남도 진주시 충의로 19",
    104: "경상남도 진주시 남강로1번길 146",
    105: "경상남도 사천시 사천읍 사천대로 1971",
}

REGION_ADDRESS_ALIASES = {
    101: "경상국립대학교 가좌캠퍼스",
    102: "진주역",
    103: "진주혁신도시 한국토지주택공사 본사",
    104: "진양호전망대",
    105: "사천공항",
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


def _summary(conn: sqlite3.Connection, analysis_date: str | None) -> dict[str, Any]:
    if not analysis_date:
        return {
            "region_count": 0,
            "high_risk_count": 0,
            "very_high_risk_count": 0,
            "average_risk_score": 0,
            "monitoring_point_count": 0,
            "recent_detection_count": 0,
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
    recent_detection = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM sinkhole_history
        WHERE occurrence_date IS NOT NULL
          AND date(occurrence_date) >= date('now', '-1 day')
        """,
    )
    summary["monitoring_point_count"] = 0
    summary["recent_detection_count"] = int((recent_detection or {}).get("count") or 0)
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
    return [_with_address(row) for row in query_all(conn, "SELECT region_id, region_name FROM regions ORDER BY region_id")]


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
        f"현재 프로그램에 등록된 진주지역 중심 분석 대상 기준으로 가장 싱크홀 발생 위험도가 높은 곳은 "
        f"도로명 주소 기준 {_address_label(top)}입니다. 최신 분석일 {analysis_date or top.get('analysis_date') or '-'} 기준 "
        f"위험도는 {_fmt(top['total_risk_score'])}/100점, 등급은 {top['risk_level']}, 우선순위는 {top['priority_rank']}위입니다. "
        f"주요 근거는 {reason}입니다. 진주지역 중심으로 현재 시스템 DB에 들어온 분석 대상 기준의 판단입니다."
    )


def _reason_answer(target: dict[str, Any] | None, payload: dict[str, Any] | None) -> str:
    if not target or not payload:
        return "설명할 대상 지역을 찾지 못했습니다. 예를 들어 '가좌캠퍼스 위험 이유 알려줘'처럼 지역명을 함께 물어보면 더 정확히 답할 수 있습니다."
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
    return (
        f"{_address_label(target)}의 위험 점수를 낮추려면 먼저 상위 기여 요인을 줄여야 합니다. "
        f"현재 점수는 {_fmt(analysis.get('total_risk_score'))}점이고 주요 기여 요인은 {_factor_text(factors)}입니다. "
        f"{_action_text(factors)} "
        "조치 이후에는 같은 기준으로 재분석해서 총점이 60점 아래로 내려가는지 확인하는 것이 운영 목표입니다."
    )


def _monitoring_answer(summary: dict[str, Any]) -> str:
    monitoring_count = int(summary.get("monitoring_point_count") or 0)
    return (
        f"현재 실제 센서 원본 기준으로 집계된 모니터링 지점은 {monitoring_count}개입니다. "
        "아직 센서 또는 현장 탐지 이벤트 원본 데이터가 연동되지 않았으므로 임의 모니터링 수치를 만들지 않습니다. "
        "운영 단계에서는 장비 ID, 수집 시각, 위치가 확인된 이벤트만 모니터링 지점과 최근 탐지 건수에 반영해야 합니다."
    )


def _fallback_answer(summary: dict[str, Any], top_rows: list[dict[str, Any]], analysis_date: str | None) -> str:
    leader = top_rows[0] if top_rows else None
    if leader:
        return (
            f"현재 데이터 기준으로는 도로명 주소 기준 {_address_label(leader)}이 {_fmt(leader['total_risk_score'])}점으로 가장 우선 관리 대상입니다. "
            f"최신 분석일은 {analysis_date or '-'}이고, 진주지역 평균 위험도는 {_fmt(summary['average_risk_score'])}점입니다. "
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
) -> str:
    lower = message.lower()
    if _contains(lower, ("목적", "뭐하는", "무슨 프로그램", "사용 목적", "시스템 설명")):
        return _purpose_answer(summary, top_rows, analysis_date)
    elif _contains(lower, ("전체", "현황", "요약", "상황", "현재 상태")) and not _contains(lower, ("이유", "왜")):
        return _overview_answer(summary, top_rows, analysis_date)
    elif _contains(lower, ("어디", "가장", "최고", "높은 곳", "위험지역", "위험 지역")) and not _contains(lower, ("이유", "왜", "원인", "근거")):
        return _top_region_answer(top_rows, analysis_date, payload)
    elif _contains(lower, ("이유", "왜", "원인", "근거", "판단")):
        return _reason_answer(target, payload)
    elif _contains(lower, ("관리", "대응", "낮추", "줄이", "조치", "개선", "점수")):
        return _management_answer(target, payload)
    elif _contains(lower, ("모니터링", "센서", "탐지")):
        return _monitoring_answer(summary)
    return _fallback_answer(summary, top_rows, analysis_date)


def _requires_verified_local_answer(message: str) -> bool:
    lower = message.lower()
    return _contains(
        lower,
        (
            "모니터링",
            "센서",
            "탐지",
            "최근 건수",
            "데이터 출처",
            "공공데이터",
            "원본 데이터",
            "정규데이터",
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
) -> dict[str, Any]:
    analysis = payload.get("analysis") if payload else None
    features = payload.get("features") if payload else None
    breakdown = payload.get("breakdown") if payload else None
    reason_cards = payload.get("reason_cards") if payload else []
    return {
        "program_scope": "현재 시스템 DB에 등록된 진주지역 중심 분석 대상 기준입니다. 대한민국 전체 결과로 표현하면 안 됩니다.",
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
- 위치를 말할 때는 내부 키 이름을 말하지 말고, 지역명/시설명 대신 도로명 주소 문자열만 사용하세요.
- 사용자가 대한민국 전체를 물어도 "현재 시스템에 등록된 진주지역 중심 분석 대상 기준"이라고 분명히 말하세요.
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
    local_answer = _local_chat_answer(message, summary, top_rows, analysis_date, target, payload)

    engine = "local_fallback"
    fallback_reason = None
    if _requires_verified_local_answer(message):
        answer = local_answer
        engine = "local_verified"
    else:
        try:
            context = _chat_context(summary, top_rows, analysis_date, target, payload, local_answer)
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
            },
            "quick_questions": [
                "현재 가장 위험한 지역이 어디야?",
                "그 지역이 위험한 이유가 뭐야?",
                "위험 점수를 낮추려면 무엇을 해야 해?",
                "전체 현황을 요약해줘.",
            ],
        }
    )
