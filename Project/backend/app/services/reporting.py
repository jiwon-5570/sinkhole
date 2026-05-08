from __future__ import annotations

from datetime import datetime
import sqlite3
from typing import Any

import requests

from app.config.settings import settings
from app.db.core import query_one
from app.services.addressing import region_road_address


def cached_report(conn: sqlite3.Connection, region_id: int, analysis_date: str) -> str | None:
    row = query_one(
        conn,
        "SELECT report_text FROM ai_report WHERE region_id = ? AND analysis_date = ?",
        (region_id, analysis_date),
    )
    return row["report_text"] if row else None


def store_report(conn: sqlite3.Connection, region_id: int, analysis_date: str, text: str) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO ai_report(region_id, analysis_date, report_text, created_at)
        VALUES(?, ?, ?, ?)
        """,
        (region_id, analysis_date, text, datetime.utcnow().isoformat(timespec="seconds") + "Z"),
    )


def _gemini_prompt(region: dict, analysis: dict, breakdown: dict, features: dict[str, Any], language: str = "한국어") -> str:
    return f"""
당신은 지반침하 위험 분석 보고서를 작성하는 보조 엔진이다.
출력은 {language}로 작성하고, 과장 없이 데이터 근거 중심으로 설명한다.

[지역 정보]
- 지역명: {region.get("region_name")}
- 도로명 주소: {region_road_address(region)}
- 시도: {region.get("sido")}
- 시군구: {region.get("sigungu")}

[분석 결과]
- 분석일: {analysis.get("analysis_date")}
- 위험 점수: {analysis.get("total_risk_score")}
- 위험 등급: {analysis.get("risk_level")}

[규칙 기반 기여도]
- 과거 사고 이력: {breakdown.get("past_sinkhole")}
- GPR/탐사: {breakdown.get("gpr")}
- 시설물 노후도: {breakdown.get("facility")}
- 강우 영향: {breakdown.get("rainfall")}
- 지하수 변동: {breakdown.get("groundwater")}
- 환경: {breakdown.get("environment")}
- 공사(보조): {breakdown.get("construction")}

[주요 feature]
{features}

다음 형식으로 6~10문장 정도의 간결한 보고서를 작성하라.
1. 현재 위험 수준 요약
2. 위험도에 영향을 준 주요 요인 2~4개
3. 단기 점검 또는 모니터링 권고
4. 불확실성 또는 추가 확인 필요 사항
""".strip()


def generate_report_with_gemini(region: dict, analysis: dict, breakdown: dict, features: dict[str, Any], language: str = "한국어") -> str:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    prompt = _gemini_prompt(region, analysis, breakdown, features, language=language)
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    response = requests.post(
        endpoint,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "topP": 0.9,
                "maxOutputTokens": 600,
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
    return text


def template_report(region: dict, analysis: dict, breakdown: dict) -> str:
    lines: list[str] = []
    lines.append(f"[\uc9c0\uc5ed] {region.get('region_name')} (region_id={region.get('region_id')})")
    lines.append(f"[\ubd84\uc11d\uc77c] {analysis.get('analysis_date')}")
    lines.append(f"[\uc885\ud569 \uc704\ud5d8\ub3c4] {analysis.get('total_risk_score')} / 100 ({analysis.get('risk_level')})")
    lines.append("")
    lines.append("[\uc8fc\uc694 \uae30\uc5ec \uc694\uc778(\uaddc\uce59 \uae30\ubc18)]")

    items = [
        ("\uacfc\uac70 \uc0ac\uace0 \uc774\ub825", breakdown.get("past_sinkhole")),
        ("GPR/\ud0d0\uc0ac", breakdown.get("gpr")),
        ("\uc2dc\uc124\ubb3c \ub178\ud6c4\ub3c4", breakdown.get("facility")),
        ("\uac15\uc6b0 \uc601\ud5a5", breakdown.get("rainfall")),
        ("\uc9c0\ud558\uc218 \ubcc0\ub3d9", breakdown.get("groundwater")),
        ("\ud658\uacbd(\ubc00\uc9d1\ub3c4/\ub3c4\ub85c)", breakdown.get("environment")),
        ("\uacf5\uc0ac(\ubcf4\uc870)", breakdown.get("construction")),
    ]
    for name, val in items:
        if val is None:
            continue
        lines.append(f"- {name}: {float(val):.1f}\uc810")

    lines.append("")
    lines.append("[\uad8c\uace0]")
    if analysis.get("risk_level") in {"\ub192\uc74c", "\ub9e4\uc6b0 \ub192\uc74c"}:
        lines.append("- \uc6b0\uc120 \uc810\uac80 \ub300\uc0c1\uc73c\ub85c \ub4f1\ub85d\ud558\uace0, GPR/\ud604\uc7a5 \uc810\uac80 \uc77c\uc815\uc744 \uac80\ud1a0\ud558\uc2ed\uc2dc\uc624.")
    else:
        lines.append("- \ucd94\uc138 \ubaa8\ub2c8\ud130\ub9c1\uc744 \uc720\uc9c0\ud558\uace0, \uac15\uc6b0/\uc9c0\ud558\uc218 \ubcc0\ub3d9\uc774 \ud070 \uc2dc\uae30\uc5d0 \uc7ac\ud3c9\uac00\ud558\uc2ed\uc2dc\uc624.")
    return "\n".join(lines)
