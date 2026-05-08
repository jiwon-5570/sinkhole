from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config.settings import settings
from app.db.core import query_all, query_one
from app.main_deps import get_db
from app.models.schemas import GenerateReportRequest, ReportFilesRequest
from app.services.features import (
    format_client_clock_label,
    load_or_build_feature_row,
    resolve_analysis_date,
    today_str,
)
from app.services.report_pdf import safe_slug, write_pdf
from app.services.reporting import cached_report, generate_report_with_gemini, store_report, template_report
from app.services.risk_scoring import risk_level, score_rule_based
from app.utils.response import fail, ok


router = APIRouter()


FACTOR_LABELS_KO = {
    "past_sinkhole": "과거 침하 이력",
    "gpr": "GPR/공동탐지",
    "facility": "노후 시설물",
    "rainfall": "강우량",
    "groundwater": "지하수 변동",
    "environment": "환경 요인",
    "construction": "공사 영향",
}

FACTOR_LABELS_EN = {
    "past_sinkhole": "Past Sinkhole",
    "gpr": "GPR / Cavity",
    "facility": "Facility Aging",
    "rainfall": "Rainfall",
    "groundwater": "Groundwater",
    "environment": "Environment",
    "construction": "Construction",
}


def _file_meta(path: Path) -> dict:
    stat = path.stat()
    return {
        "file_name": path.name,
        "url": f"/api/reports/files/{path.name}",
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _score_breakdown_dict(breakdown: object) -> dict[str, float]:
    return {
        "past_sinkhole": float(getattr(breakdown, "past_sinkhole", 0.0)),
        "gpr": float(getattr(breakdown, "gpr", 0.0)),
        "facility": float(getattr(breakdown, "facility", 0.0)),
        "rainfall": float(getattr(breakdown, "rainfall", 0.0)),
        "groundwater": float(getattr(breakdown, "groundwater", 0.0)),
        "environment": float(getattr(breakdown, "environment", 0.0)),
        "construction": float(getattr(breakdown, "construction", 0.0)),
    }


def _risk_level_for_output(level: str, is_en: bool) -> str:
    if not is_en:
        return level
    mapping = {
        "낮음": "Low",
        "보통": "Moderate",
        "높음": "High",
        "매우 높음": "Very High",
    }
    return mapping.get(level, level)


def _build_report_context(conn: sqlite3.Connection, region_id: int, analysis_date: str) -> tuple[dict, dict, dict, list[dict], list[dict]]:
    features = load_or_build_feature_row(conn, region_id, analysis_date)
    score, breakdown = score_rule_based(features)
    breakdown_data = _score_breakdown_dict(breakdown)

    analysis_row = query_one(
        conn,
        """
        SELECT total_risk_score, risk_level
        FROM risk_analysis_result
        WHERE region_id = ? AND analysis_date = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (region_id, analysis_date),
    )
    total_score = float(analysis_row.get("total_risk_score") or score) if analysis_row else float(score)
    level = str(analysis_row["risk_level"]) if analysis_row and analysis_row.get("risk_level") else risk_level(total_score)
    analysis = {
        "region_id": region_id,
        "analysis_date": analysis_date,
        "total_risk_score": round(total_score, 1),
        "risk_level": level,
    }

    trend_data = query_all(
        conn,
        """
        SELECT analysis_date, total_risk_score, risk_level
        FROM risk_analysis_result
        WHERE region_id = ?
        ORDER BY analysis_date ASC, id ASC
        LIMIT 90
        """,
        (region_id,),
    )
    if not trend_data:
        trend_data = [
            {
                "analysis_date": analysis_date,
                "total_risk_score": analysis["total_risk_score"],
                "risk_level": analysis["risk_level"],
            }
        ]

    history_cause = query_all(
        conn,
        """
        SELECT COALESCE(cause_type, 'Unknown') AS cause_type, COUNT(*) AS count
        FROM sinkhole_history
        WHERE region_id = ?
        GROUP BY COALESCE(cause_type, 'Unknown')
        ORDER BY count DESC, cause_type ASC
        LIMIT 7
        """,
        (region_id,),
    )

    return features, analysis, breakdown_data, trend_data, history_cause


def _top_factors(breakdown_data: dict[str, float]) -> list[tuple[str, float]]:
    sorted_items = sorted(breakdown_data.items(), key=lambda item: item[1], reverse=True)
    return [(name, round(value, 1)) for name, value in sorted_items if value > 0][:3]


def _build_chart_sections(
    breakdown_data: dict[str, float],
    trend_data: list[dict],
    history_cause: list[dict],
    is_en: bool,
) -> list[dict]:
    factor_labels = FACTOR_LABELS_EN if is_en else FACTOR_LABELS_KO
    factor_items = [
        {"label": factor_labels[key], "value": round(value, 1)}
        for key, value in breakdown_data.items()
    ]

    trend_points = [
        {"label": str(row.get("analysis_date", "")), "value": float(row.get("total_risk_score") or 0.0)}
        for row in trend_data
    ]

    cause_items: list[dict] = []
    for row in history_cause:
        raw_cause = str(row.get("cause_type") or "").strip()
        if raw_cause == "Unknown" and not is_en:
            raw_cause = "미상"
        if not raw_cause:
            raw_cause = "Unknown" if is_en else "미상"
        cause_items.append({"label": raw_cause, "value": float(row.get("count") or 0)})

    return [
        {
            "kind": "bar",
            "title": "Risk Factor Contribution" if is_en else "위험 요인 기여도",
            "items": factor_items,
            "max_value": 30,
            "note": (
                "Each value is a weighted contribution to total risk score."
                if is_en
                else "각 값은 최종 위험도 점수에 반영되는 가중 기여 점수입니다."
            ),
        },
        {
            "kind": "line",
            "title": "Risk Score Trend" if is_en else "위험도 점수 추이",
            "points": trend_points,
            "min_value": 0,
            "max_value": 100,
            "note": (
                "Trend from historical analyses for this region."
                if is_en
                else "해당 지역의 누적 분석 결과 기준 위험도 추이입니다."
            ),
        },
        {
            "kind": "bar",
            "title": "Past Sinkhole Cause Distribution" if is_en else "과거 침하 원인 분포",
            "items": cause_items,
            "note": (
                "Frequency by cause type in historical sinkhole records."
                if is_en
                else "과거 지반침하 이력에서 원인 유형별 발생 건수입니다."
            ),
        },
    ]


def _write_pdf(
    region: dict,
    analysis_date: str,
    report_text: str,
    analysis: dict,
    breakdown_data: dict[str, float],
    trend_data: list[dict],
    history_cause: list[dict],
    analysis_local_time: str | None = None,
    history: list[dict] | None = None,
    language: str = "ko",
) -> dict:
    time_part = datetime.now().strftime("%H%M%S-%f")
    file_name = safe_slug(f"region-{region['region_id']}-{analysis_date}-{time_part}.pdf")
    file_path = settings.reports_dir / file_name

    is_en = (language or "ko").lower().startswith("en")
    factor_labels = FACTOR_LABELS_EN if is_en else FACTOR_LABELS_KO
    top_factors = _top_factors(breakdown_data)
    risk_level_text = _risk_level_for_output(str(analysis.get("risk_level") or ""), is_en)

    if is_en:
        lines = [
            f"Region: {region['region_name']}",
            f"Region ID: {region['region_id']}",
            f"Analysis Date: {analysis_date}",
            f"Analysis Time (Local): {analysis_local_time or '-'}",
            f"Final Risk Score: {float(analysis.get('total_risk_score') or 0.0):.1f} / 100",
            f"Risk Level: {risk_level_text}",
            "",
            "[Key Drivers]",
            *(f"- {factor_labels[name]}: {value:.1f}" for name, value in top_factors),
            "",
            *report_text.splitlines(),
        ]
    else:
        lines = [
            f"대상 지역: {region['region_name']}",
            f"지역 ID: {region['region_id']}",
            f"분석 일자: {analysis_date}",
            f"분석 시각(로컬): {analysis_local_time or '-'}",
            f"최종 위험도 점수: {float(analysis.get('total_risk_score') or 0.0):.1f} / 100",
            f"위험 등급: {risk_level_text}",
            "",
            "[주요 위험 기여 요인]",
            *(f"- {factor_labels[name]}: {value:.1f}" for name, value in top_factors),
            "",
            *report_text.splitlines(),
        ]

    if history:
        lines.extend([
            "",
            "-" * 40,
            "[Detailed Past Sinkhole History]" if is_en else "[과거 침하 이력 상세 / Detailed Past Sinkhole History]",
            "",
        ])
        for idx, row in enumerate(history, 1):
            date_str = row.get("occurrence_date", "Unknown")
            cause = row.get("cause_type", "Unknown")
            scale = row.get("damage_scale", 0.0)
            if is_en:
                lines.append(f"{idx}. Date: {date_str} | Cause: {cause} | Damage Scale: {scale:.1f}")
            else:
                lines.append(f"{idx}. 일자: {date_str} | 원인: {cause} | 피해규모(점수): {scale:.1f}")

    if is_en:
        lines.extend([
            "",
            "-" * 40,
            "[Analysis Metrics Guide]",
            "",
            "1. Past Sinkhole",
            "   - Scores the frequency and scale of past sinkholes.",
            "2. Ground Penetrating Radar (GPR)",
            "   - Underground safety index based on GPR data.",
            "3. Facility",
            "   - Reflects the deterioration of underground facilities like pipes.",
            "4. Rainfall",
            "   - Recent precipitation amount, a major cause of ground weakening.",
            "5. Groundwater",
            "   - Indicates sudden fluctuations in groundwater level.",
            "",
            "※ These metrics are aggregated to calculate a Final Risk Score (0~100) and classified into grades (Safe, Warning, Danger).",
            "",
            "-" * 40,
            "[Data Sources]",
            " - KALIS: Sinkhole, GPR, Facility data",
            " - KMA: Weather data (Rainfall)",
            " - Open Data Portal: Groundwater variation",
        ])
    else:
        lines.extend([
            "",
            "-" * 40,
            "[분석 지표 설명 / Analysis Metrics Guide]",
            "",
            "1. 과거 침하 이력 (Past Sinkhole)",
            "   - 지역 내 과거 싱크홀 발생 빈도 및 규모를 점수화합니다.",
            "2. 지표투과레이더 (GPR)",
            "   - 지하 공동(빈 공간) 탐사 결과를 바탕으로 한 지하 안전성 지표입니다.",
            "3. 노후 시설물 (Facility)",
            "   - 주변 상하수도관 등 지하 매설물의 노후화 정도를 반영합니다.",
            "4. 강우량 (Rainfall)",
            "   - 최근 내린 비의 양으로, 지반 약화의 주요 원인입니다.",
            "5. 지하수 (Groundwater)",
            "   - 지하수위의 급격한 변동성을 나타내며 싱크홀 발생과 밀접한 관련이 있습니다.",
            "",
            "※ 위 지표들을 종합하여 최종 위험도 점수(0~100)를 산출하고 등급(안전, 주의, 위험)을 분류합니다.",
            "",
            "-" * 40,
            "[데이터 출처 / Data Sources]",
            " - 국토안전관리원: 지반침하 안전점검, GPR 공동탐지, 시설물 안전관리",
            " - 기상청: 강우량 등 기상 데이터",
            " - 공공데이터포털: 지하수 등 변동 데이터",
        ])

    chart_sections = _build_chart_sections(
        breakdown_data=breakdown_data,
        trend_data=trend_data,
        history_cause=history_cause,
        is_en=is_en,
    )

    write_pdf(
        file_path,
        "Sinkhole Analysis Report",
        lines,
        chart_sections=chart_sections,
        generated_at_text=analysis_local_time,
    )
    return _file_meta(file_path)


@router.post("/api/generate-report")
def generate_report(req: GenerateReportRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    analysis_date = resolve_analysis_date(req.analysis_date, req.client_local_datetime)
    analysis_local_time = format_client_clock_label(
        client_local_datetime=req.client_local_datetime,
        client_timezone=req.client_timezone,
        client_utc_offset_minutes=req.client_utc_offset_minutes,
    )
    region = query_one(conn, "SELECT * FROM regions WHERE region_id = ?", (req.region_id,))
    if not region:
        return fail("Region not found.", "NOT_FOUND")

    history_data = query_all(
        conn,
        "SELECT occurrence_date, cause_type, damage_scale FROM sinkhole_history WHERE region_id = ? ORDER BY occurrence_date DESC",
        (req.region_id,)
    )
    features, analysis, breakdown_data, trend_data, history_cause = _build_report_context(conn, req.region_id, analysis_date)
    cached = cached_report(conn, req.region_id, analysis_date)

    if cached:
        pdf = _write_pdf(
            region=region,
            analysis_date=analysis_date,
            report_text=cached,
            analysis=analysis,
            breakdown_data=breakdown_data,
            trend_data=trend_data,
            history_cause=history_cause,
            analysis_local_time=analysis_local_time,
            history=history_data,
            language=req.language or "ko",
        )
        return ok(
            {
                "region_id": req.region_id,
                "analysis_date": analysis_date,
                "analysis_local_time": analysis_local_time,
                "report": cached,
                "cached": True,
                "source": "cached",
                "pdf": pdf,
            }
        )

    try:
        text = generate_report_with_gemini(region=region, analysis=analysis, breakdown=breakdown_data, features=features)
        source = "gemini"
    except Exception:
        text = template_report(region=region, analysis=analysis, breakdown=breakdown_data)
        source = "template"

    store_report(conn, req.region_id, analysis_date, text)
    pdf = _write_pdf(
        region=region,
        analysis_date=analysis_date,
        report_text=text,
        analysis=analysis,
        breakdown_data=breakdown_data,
        trend_data=trend_data,
        history_cause=history_cause,
        analysis_local_time=analysis_local_time,
        history=history_data,
        language=req.language or "ko",
    )
    return ok(
        {
            "region_id": req.region_id,
            "analysis_date": analysis_date,
            "analysis_local_time": analysis_local_time,
            "report": text,
            "cached": False,
            "source": source,
            "pdf": pdf,
        }
    )


@router.get("/api/report/{region_id}")
def get_report(region_id: int, analysis_date: str | None = None, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    target_date = analysis_date or today_str()
    cached = cached_report(conn, region_id, target_date)
    if not cached:
        return fail("Report not found. Generate it first.", "NOT_FOUND")
    return ok({"region_id": region_id, "analysis_date": target_date, "report": cached})


@router.get("/api/reports")
def list_reports() -> dict:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(settings.reports_dir.glob("*.pdf"), key=lambda path: path.stat().st_mtime, reverse=True)
    return ok([_file_meta(path) for path in files])


@router.get("/api/reports/files/{file_name}")
def get_report_file(file_name: str) -> FileResponse:
    safe_name = Path(file_name).name
    file_path = settings.reports_dir / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, media_type="application/pdf", filename=safe_name)


@router.post("/api/reports/delete")
def delete_reports(req: ReportFilesRequest) -> dict:
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    deleted: list[str] = []
    missing: list[str] = []
    failed: list[str] = []

    for name in req.file_names:
        safe_name = Path(name).name
        if not safe_name.lower().endswith(".pdf"):
            failed.append(safe_name)
            continue
        file_path = settings.reports_dir / safe_name
        if not file_path.exists():
            missing.append(safe_name)
            continue
        try:
            file_path.unlink()
            deleted.append(safe_name)
        except Exception:
            failed.append(safe_name)

    return ok(
        {
            "deleted": deleted,
            "missing": missing,
            "failed": failed,
        }
    )
