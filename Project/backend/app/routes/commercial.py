from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from app.config.settings import settings
from app.models.schemas import CommercialAnalyzeRequest, CommercialReportRequest
from app.services.features import format_client_clock_label
from app.services.reasoning import build_reason_cards
from app.services.report_pdf import safe_slug, write_pdf
from app.services.commercial import build_commercial_analysis, build_commercial_report
from app.utils.response import fail, ok


router = APIRouter()


def _file_meta(path: Path) -> dict:
    stat = path.stat()
    return {
        "file_name": path.name,
        "url": f"/api/reports/files/{path.name}",
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _write_commercial_pdf(payload: dict, report_text: str, language: str = "ko") -> dict:
    location = payload.get("location") or {}
    analysis = payload.get("analysis") or {}
    breakdown = payload.get("breakdown") or {}
    weather = payload.get("weather") or {}
    local_time = analysis.get("client_local_time")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    location_name = str(location.get("location_name") or "live-location")
    file_name = safe_slug(f"live-{location_name}-{stamp}.pdf")
    file_path = settings.reports_dir / file_name
    is_en = (language or "ko").lower().startswith("en")

    if is_en:
        lines = [
            f"Location: {location_name}",
            f"Road Address: {location_name}",
            f"Analysis Time (Local): {local_time or '-'}",
            f"Final Risk Score: {float(analysis.get('total_risk_score') or 0.0):.1f} / 100",
            f"Risk Level: {analysis.get('risk_level') or '-'}",
            "",
            *str(report_text or "").splitlines(),
        ]
    else:
        lines = [
            f"대상 위치: {location_name}",
            f"도로명 주소: {location_name}",
            f"분석 시각(로컬): {local_time or '-'}",
            f"최종 위험도 점수: {float(analysis.get('total_risk_score') or 0.0):.1f} / 100",
            f"위험 등급: {analysis.get('risk_level') or '-'}",
            "",
            *str(report_text or "").splitlines(),
        ]

    chart_sections = [
        {
            "kind": "bar",
            "title": "Risk Factor Contribution" if is_en else "위험 요인 기여도",
            "max_value": 30,
            "items": [
                {"label": "Past" if is_en else "과거 이력", "value": float(breakdown.get("past_sinkhole") or 0.0)},
                {"label": "GPR", "value": float(breakdown.get("gpr") or 0.0)},
                {"label": "Facility", "value": float(breakdown.get("facility") or 0.0)},
                {"label": "Rainfall", "value": float(breakdown.get("rainfall") or 0.0)},
                {"label": "Groundwater", "value": float(breakdown.get("groundwater") or 0.0)},
                {"label": "Environment", "value": float(breakdown.get("environment") or 0.0)},
                {"label": "Construction", "value": float(breakdown.get("construction") or 0.0)},
            ],
        },
        {
            "kind": "line",
            "title": "7-day Rainfall Trend (mm)" if is_en else "최근 7일 강우 추이(mm)",
            "points": [
                {"label": f"D{idx + 1}", "value": float(value or 0.0)}
                for idx, value in enumerate(weather.get("rainfall_7d_daily") or [])
            ],
            "min_value": 0,
        },
    ]

    write_pdf(
        file_path,
        "Sinkhole Commercial Analysis Report",
        lines,
        chart_sections=chart_sections,
        generated_at_text=local_time,
    )
    return _file_meta(file_path)


@router.post("/api/commercial/analyze")
def commercial_analyze(req: CommercialAnalyzeRequest) -> dict:
    try:
        payload = build_commercial_analysis(req.location_name, req.latitude, req.longitude)
        payload["analysis"]["client_local_time"] = format_client_clock_label(
            client_local_datetime=req.client_local_datetime,
            client_timezone=req.client_timezone,
            client_utc_offset_minutes=req.client_utc_offset_minutes,
        )
        payload["reason_cards"] = build_reason_cards(
            payload["location"]["location_name"],
            payload["analysis"],
            payload["breakdown"],
            features=payload.get("features"),
            weather=payload.get("weather"),
        )
    except Exception as exc:
        return fail(str(exc), "COMMERCIAL_ANALYZE_FAILED")
    return ok(payload)


@router.post("/api/commercial/report")
def commercial_report(req: CommercialReportRequest) -> dict:
    try:
        payload = build_commercial_analysis(req.location_name, req.latitude, req.longitude)
        payload["analysis"]["client_local_time"] = format_client_clock_label(
            client_local_datetime=req.client_local_datetime,
            client_timezone=req.client_timezone,
            client_utc_offset_minutes=req.client_utc_offset_minutes,
        )
        payload["reason_cards"] = build_reason_cards(
            payload["location"]["location_name"],
            payload["analysis"],
            payload["breakdown"],
            features=payload.get("features"),
            weather=payload.get("weather"),
        )
        report = build_commercial_report(payload)
        pdf = _write_commercial_pdf(payload, report, language=req.language or "ko")
    except Exception as exc:
        return fail(str(exc), "COMMERCIAL_REPORT_FAILED")
    return ok({"report": report, "analysis": payload, "pdf": pdf})
