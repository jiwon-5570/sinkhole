from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any, Callable, Iterable

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


WINDOWS_FONT = Path("C:/Windows/Fonts/malgun.ttf")
FONT_NAME = "Helvetica"

NAVY = (0.05, 0.10, 0.18)
NAVY_2 = (0.08, 0.15, 0.26)
BLUE = (0.15, 0.42, 0.90)
BLUE_SOFT = (0.90, 0.95, 1.00)
TEXT = (0.11, 0.15, 0.22)
MUTED = (0.38, 0.45, 0.55)
BORDER = (0.78, 0.84, 0.92)
PAPER = (0.98, 0.99, 1.00)
WHITE = (1.0, 1.0, 1.0)
GREEN = (0.18, 0.63, 0.41)
GOLD = (0.93, 0.65, 0.13)
ORANGE = (0.90, 0.36, 0.16)
RED = (0.85, 0.18, 0.18)


def _ensure_font() -> str:
    global FONT_NAME
    if FONT_NAME != "Helvetica":
        return FONT_NAME
    if WINDOWS_FONT.exists():
        pdfmetrics.registerFont(TTFont("MalgunGothic", str(WINDOWS_FONT)))
        FONT_NAME = "MalgunGothic"
    return FONT_NAME


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return slug or "report"


def write_pdf(
    report_path: Path,
    title: str,
    lines: Iterable[str],
    chart_sections: list[dict[str, Any]] | None = None,
    generated_at_text: str | None = None,
) -> Path:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    font_name = _ensure_font()
    chart_sections = chart_sections or []
    raw_lines = [str(line) for line in lines]

    pdf = canvas.Canvas(str(report_path), pagesize=A4)
    width, height = A4
    margin_x = 46
    bottom_margin = 48
    page_no = 1
    generated = generated_at_text or datetime.now().isoformat(timespec="seconds")

    pdf.setTitle(title)
    pdf.setAuthor("Jiwon Kang")
    pdf.setSubject("Sinkhole analysis report")

    def draw_page_background() -> None:
        pdf.setFillColorRGB(*PAPER)
        pdf.rect(0, 0, width, height, stroke=0, fill=1)

    def draw_header() -> None:
        draw_page_background()
        pdf.setFillColorRGB(*NAVY)
        pdf.rect(0, height - 76, width, 76, stroke=0, fill=1)
        pdf.setFillColorRGB(*BLUE)
        pdf.rect(0, height - 76, width, 4, stroke=0, fill=1)
        pdf.setFont(font_name, 16)
        pdf.setFillColorRGB(*WHITE)
        pdf.drawString(margin_x, height - 34, title)
        pdf.setFont(font_name, 8.5)
        pdf.setFillColorRGB(0.78, 0.86, 0.98)
        pdf.drawString(margin_x, height - 53, "Public-data based sinkhole risk assessment")
        pdf.drawRightString(width - margin_x, height - 34, "SinkHole Risk Platform")
        pdf.drawRightString(width - margin_x, height - 53, f"Generated: {generated}")
        pdf.setFillColorRGB(*TEXT)

    def draw_footer() -> None:
        pdf.setStrokeColorRGB(*BORDER)
        pdf.setLineWidth(0.6)
        pdf.line(margin_x, 34, width - margin_x, 34)
        pdf.setFont(font_name, 8)
        pdf.setFillColorRGB(*MUTED)
        pdf.drawString(margin_x, 22, "This report is a risk-priority indicator, not a deterministic prediction.")
        pdf.drawRightString(width - margin_x, 22, f"Page {page_no}")
        pdf.setFillColorRGB(*TEXT)

    y = height - 106
    draw_header()

    def new_page() -> None:
        nonlocal y, page_no
        draw_footer()
        pdf.showPage()
        page_no += 1
        draw_header()
        y = height - 106

    def ensure_space(current_y: float, needed_height: float) -> float:
        nonlocal y
        if current_y - needed_height < bottom_margin:
            new_page()
            return y
        return current_y

    summary = _extract_summary(raw_lines)
    drivers = _extract_key_drivers(raw_lines)
    if summary:
        y = _draw_summary_panel(
            pdf=pdf,
            font_name=font_name,
            width=width,
            margin_x=margin_x,
            y=y,
            summary=summary,
            drivers=drivers,
            ensure_space=ensure_space,
        )

    for line in raw_lines:
        text = str(line).strip()
        if not text:
            y -= 6
            if y < bottom_margin:
                new_page()
            continue
        if _is_separator(text):
            y = ensure_space(y, 14)
            pdf.setStrokeColorRGB(*BORDER)
            pdf.line(margin_x, y, width - margin_x, y)
            y -= 14
            continue
        if _is_section_heading(text):
            y = _draw_section_heading(pdf, font_name, width, margin_x, y, text, ensure_space)
            continue
        if _is_subheading(text):
            y = _draw_subheading(pdf, font_name, margin_x, y, text, ensure_space)
            continue
        if text.startswith("- "):
            y = _draw_bullet(pdf, font_name, margin_x, y, text[2:], ensure_space)
            continue
        if re.match(r"^\d+\.\s+", text):
            y = _draw_numbered(pdf, font_name, margin_x, y, text, ensure_space)
            continue
        y = _draw_paragraph(pdf, font_name, margin_x, y, text, ensure_space)

    if chart_sections:
        y = _draw_section_heading(
            pdf,
            font_name,
            width,
            margin_x,
            y,
            "Analysis Charts",
            ensure_space,
        )
        for section in chart_sections:
            chart_kind = str(section.get("kind") or "").strip().lower()
            if chart_kind == "bar":
                y = _draw_bar_chart(
                    pdf=pdf,
                    font_name=font_name,
                    width=width,
                    margin_x=margin_x,
                    y=y,
                    section=section,
                    ensure_space=ensure_space,
                )
            elif chart_kind == "line":
                y = _draw_line_chart(
                    pdf=pdf,
                    font_name=font_name,
                    width=width,
                    margin_x=margin_x,
                    y=y,
                    section=section,
                    ensure_space=ensure_space,
                )

    draw_footer()
    pdf.save()
    return report_path


def _extract_summary(lines: list[str]) -> dict[str, str]:
    summary: dict[str, str] = {}
    key_map = {
        "대상 지역": "target",
        "Region": "target",
        "도로명 주소/대표 주소": "address",
        "분석 일자": "date",
        "분석일": "date",
        "Analysis Date": "date",
        "분석 시각(로컬)": "time",
        "Analysis Time (Local)": "time",
        "최종 위험도 점수": "score",
        "종합 위험도": "score",
        "Final Risk Score": "score",
        "위험 등급": "level",
        "Risk Level": "level",
        "운영 판단": "decision",
    }
    for raw in lines:
        text = str(raw).strip().lstrip("- ").strip()
        if ":" not in text:
            continue
        left, right = text.split(":", 1)
        left = left.strip()
        right = right.strip()
        if not right:
            continue
        for key, dest in key_map.items():
            if left == key and dest not in summary:
                if dest == "target" and left == "Region" and "Region ID" in text:
                    continue
                summary[dest] = right
    return summary


def _extract_key_drivers(lines: list[str]) -> list[tuple[str, float]]:
    drivers: list[tuple[str, float]] = []
    capture = False
    for raw in lines:
        text = str(raw).strip()
        if text in {"[주요 위험 기여 요인]", "[Key Drivers]"}:
            capture = True
            continue
        if capture and not text:
            break
        if capture and text.startswith("[") and text.endswith("]"):
            break
        if capture and text.startswith("- "):
            body = text[2:]
            if ":" in body:
                label, value = body.split(":", 1)
                drivers.append((label.strip(), _safe_float(value.strip().split()[0])))
    return drivers[:5]


def _draw_summary_panel(
    pdf: canvas.Canvas,
    font_name: str,
    width: float,
    margin_x: float,
    y: float,
    summary: dict[str, str],
    drivers: list[tuple[str, float]],
    ensure_space: Callable[[float, float], float],
) -> float:
    panel_w = width - margin_x * 2
    target = summary.get("target") or "-"
    address = summary.get("address") or ""
    score = summary.get("score") or "-"
    level = summary.get("level") or "-"
    date = summary.get("date") or "-"
    decision = summary.get("decision") or ""
    target_text = target if not address else f"{target} / {address}"
    target_chunks = _wrap_text(target_text, 76)[:3]
    decision_chunks = _wrap_text(f"Decision: {decision}", 76)[:2] if decision else []
    driver_rows = drivers[:3]

    card_h = 48
    info_h = 16 + (len(target_chunks) + len(decision_chunks)) * 14
    driver_h = 0 if not driver_rows else 24 + len(driver_rows) * 15
    panel_h = 40 + 18 + card_h + 18 + info_h + (14 + driver_h if driver_rows else 0) + 20
    y = ensure_space(y, panel_h + 18)
    panel_y = y - panel_h

    pdf.setFillColorRGB(*WHITE)
    pdf.setStrokeColorRGB(*BORDER)
    pdf.roundRect(margin_x, panel_y, panel_w, panel_h, 9, stroke=1, fill=1)
    pdf.setFillColorRGB(*BLUE_SOFT)
    pdf.roundRect(margin_x + 10, y - 40, panel_w - 20, 30, 7, stroke=0, fill=1)
    pdf.setFont(font_name, 12)
    pdf.setFillColorRGB(*NAVY)
    pdf.drawString(margin_x + 22, y - 29, "Executive Summary")

    score_num = _first_number(score)
    risk_rgb = _risk_color(score_num)

    top_y = y - 58
    card_gap = 10
    card_w = (panel_w - 44 - card_gap * 2) / 3
    card_x = margin_x + 22
    _draw_card(pdf, font_name, card_x, top_y - card_h, card_w, card_h, "Risk Score", score, risk_rgb)
    _draw_card(pdf, font_name, card_x + card_w + card_gap, top_y - card_h, card_w, card_h, "Risk Level", level, BLUE)
    _draw_card(pdf, font_name, card_x + (card_w + card_gap) * 2, top_y - card_h, card_w, card_h, "Analysis Date", date, NAVY_2)

    cursor = top_y - card_h - 18
    pdf.setFont(font_name, 9.5)
    pdf.setFillColorRGB(*MUTED)
    pdf.drawString(margin_x + 22, cursor, "Target")
    pdf.setFont(font_name, 10.5)
    pdf.setFillColorRGB(*TEXT)
    for chunk in target_chunks:
        cursor -= 14
        pdf.drawString(margin_x + 22, cursor, chunk)
    for chunk in decision_chunks:
        cursor -= 14
        pdf.drawString(margin_x + 22, cursor, chunk)

    if driver_rows:
        cursor -= 20
        driver_x = margin_x + 22
        pdf.setFont(font_name, 9.5)
        pdf.setFillColorRGB(*MUTED)
        pdf.drawString(driver_x, cursor, "Top Risk Drivers")
        cursor -= 17
        max_value = max((value for _, value in driver_rows), default=1.0) or 1.0
        bar_x = driver_x + 122
        bar_w = panel_w - 170
        for label, value in driver_rows:
            row_y = cursor
            pdf.setFont(font_name, 8.5)
            pdf.setFillColorRGB(*TEXT)
            pdf.drawString(driver_x, row_y, _trim_label(label, 18))
            pdf.setFillColorRGB(0.88, 0.92, 0.97)
            pdf.roundRect(bar_x, row_y - 1, bar_w, 7, 3, stroke=0, fill=1)
            pdf.setFillColorRGB(*_risk_color(value / max_value * 100.0))
            pdf.roundRect(bar_x, row_y - 1, max(2.0, bar_w * value / max_value), 7, 3, stroke=0, fill=1)
            pdf.setFillColorRGB(*TEXT)
            pdf.drawRightString(bar_x + bar_w + 28, row_y - 1, f"{value:.1f}")
            cursor -= 15

    return panel_y - 18


def _draw_card(
    pdf: canvas.Canvas,
    font_name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    label: str,
    value: str,
    accent_rgb: tuple[float, float, float],
) -> None:
    pdf.setFillColorRGB(0.97, 0.99, 1.00)
    pdf.setStrokeColorRGB(*BORDER)
    pdf.roundRect(x, y, w, h, 7, stroke=1, fill=1)
    pdf.setFillColorRGB(*accent_rgb)
    pdf.roundRect(x, y, 5, h, 3, stroke=0, fill=1)
    pdf.setFont(font_name, 8.5)
    pdf.setFillColorRGB(*MUTED)
    pdf.drawString(x + 13, y + h - 16, label)
    pdf.setFont(font_name, 14)
    pdf.setFillColorRGB(*TEXT)
    pdf.drawString(x + 13, y + 13, _trim_label(str(value), 18))


def _is_separator(text: str) -> bool:
    return bool(text) and set(text) <= {"-"} and len(text) >= 8


def _is_section_heading(text: str) -> bool:
    if text.startswith("[") and text.endswith("]"):
        return True
    if re.match(r"^\d+\.\s+", text) and ":" not in text[:24] and len(text) <= 70:
        return True
    return False


def _is_subheading(text: str) -> bool:
    return text.endswith(":") and len(text) <= 36


def _draw_section_heading(
    pdf: canvas.Canvas,
    font_name: str,
    width: float,
    margin_x: float,
    y: float,
    text: str,
    ensure_space: Callable[[float, float], float],
) -> float:
    chunks = _wrap_text(text.strip("[]"), 72)
    height = 22 + (len(chunks) - 1) * 12
    y = ensure_space(y, height + 12)
    box_y = y - height
    pdf.setFillColorRGB(*NAVY_2)
    pdf.roundRect(margin_x, box_y, width - margin_x * 2, height, 7, stroke=0, fill=1)
    pdf.setFillColorRGB(*BLUE)
    pdf.roundRect(margin_x, box_y, 5, height, 3, stroke=0, fill=1)
    pdf.setFont(font_name, 11.2)
    pdf.setFillColorRGB(*WHITE)
    cursor = y - 15
    for chunk in chunks:
        pdf.drawString(margin_x + 15, cursor, chunk)
        cursor -= 12
    pdf.setFillColorRGB(*TEXT)
    return box_y - 12


def _draw_subheading(
    pdf: canvas.Canvas,
    font_name: str,
    margin_x: float,
    y: float,
    text: str,
    ensure_space: Callable[[float, float], float],
) -> float:
    y = ensure_space(y, 20)
    pdf.setFont(font_name, 10.8)
    pdf.setFillColorRGB(*NAVY)
    pdf.drawString(margin_x + 2, y - 12, text)
    pdf.setFillColorRGB(*TEXT)
    return y - 22


def _draw_bullet(
    pdf: canvas.Canvas,
    font_name: str,
    margin_x: float,
    y: float,
    text: str,
    ensure_space: Callable[[float, float], float],
) -> float:
    font_size = 9.3
    text_x = margin_x + 18
    max_width = A4[0] - margin_x - text_x - 8
    chunks = _wrap_text_to_width(text, font_name, font_size, max_width)
    needed = max(16, len(chunks) * 13 + 3)
    y = ensure_space(y, needed)
    cursor = y - 11
    pdf.setFillColorRGB(*BLUE)
    pdf.circle(margin_x + 7, cursor + 3, 2.1, stroke=0, fill=1)
    pdf.setFont(font_name, font_size)
    pdf.setFillColorRGB(*TEXT)
    for idx, chunk in enumerate(chunks):
        pdf.drawString(text_x, cursor - idx * 13, chunk)
    return y - needed


def _draw_numbered(
    pdf: canvas.Canvas,
    font_name: str,
    margin_x: float,
    y: float,
    text: str,
    ensure_space: Callable[[float, float], float],
) -> float:
    font_size = 9.3
    first_x = margin_x
    indent_x = margin_x + 18
    max_width = A4[0] - margin_x - first_x - 8
    chunks = _wrap_text_to_width(text, font_name, font_size, max_width)
    needed = max(16, len(chunks) * 13 + 3)
    y = ensure_space(y, needed)
    cursor = y - 11
    pdf.setFont(font_name, font_size)
    pdf.setFillColorRGB(*TEXT)
    for idx, chunk in enumerate(chunks):
        pdf.drawString(first_x if idx == 0 else indent_x, cursor - idx * 13, chunk)
    return y - needed


def _draw_paragraph(
    pdf: canvas.Canvas,
    font_name: str,
    margin_x: float,
    y: float,
    text: str,
    ensure_space: Callable[[float, float], float],
) -> float:
    font_size = 9.4
    text_x = margin_x + 2
    max_width = A4[0] - margin_x - text_x - 8
    chunks = _wrap_text_to_width(text, font_name, font_size, max_width)
    needed = max(16, len(chunks) * 13 + 4)
    y = ensure_space(y, needed)
    pdf.setFont(font_name, font_size)
    pdf.setFillColorRGB(*TEXT)
    cursor = y - 11
    for idx, chunk in enumerate(chunks):
        pdf.drawString(text_x, cursor - idx * 13, chunk)
    return y - needed


def _draw_bar_chart(
    pdf: canvas.Canvas,
    font_name: str,
    width: float,
    margin_x: float,
    y: float,
    section: dict[str, Any],
    ensure_space: Callable[[float, float], float],
) -> float:
    title = str(section.get("title") or "Bar Chart")
    raw_items = section.get("items") or []
    items: list[tuple[str, float]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or raw.get("name") or "")
        value = _safe_float(raw.get("value"))
        if label:
            items.append((label, max(0.0, value)))

    items = items[:10]
    chart_h = max(92.0, 24.0 + len(items) * 18.0)
    y = ensure_space(y, chart_h + 62)
    card_y = y - chart_h - 44
    card_h = chart_h + 38
    pdf.setFillColorRGB(*WHITE)
    pdf.setStrokeColorRGB(*BORDER)
    pdf.roundRect(margin_x, card_y, width - margin_x * 2, card_h, 8, stroke=1, fill=1)

    pdf.setFont(font_name, 11.5)
    pdf.setFillColorRGB(*NAVY)
    pdf.drawString(margin_x + 16, y - 17, title)
    y -= 28

    if not items:
        pdf.setFont(font_name, 9.5)
        pdf.setFillColorRGB(*MUTED)
        pdf.drawString(margin_x + 16, y, "No chart data")
        return card_y - 16

    plot_top = y
    plot_bottom = y - chart_h
    axis_x = margin_x + 160
    right_x = width - margin_x - 28
    bar_max_w = max(100.0, right_x - axis_x - 8)

    max_value = _safe_float(section.get("max_value"))
    if max_value <= 0:
        max_value = max(value for _, value in items)
    if max_value <= 0:
        max_value = 1.0

    pdf.setStrokeColorRGB(0.82, 0.86, 0.92)
    pdf.setLineWidth(0.8)
    pdf.line(axis_x, plot_bottom + 10, axis_x, plot_top - 6)
    pdf.line(axis_x, plot_bottom + 10, right_x, plot_bottom + 10)

    pdf.setFont(font_name, 8.0)
    pdf.setFillColorRGB(*MUTED)
    for tick in (0.0, max_value / 2.0, max_value):
        tx = axis_x + (bar_max_w * (tick / max_value))
        pdf.line(tx, plot_bottom + 8, tx, plot_bottom + 12)
        pdf.drawCentredString(tx, plot_bottom - 2, f"{tick:.0f}")

    start_y = plot_top - 18
    for idx, (label, value) in enumerate(items):
        row_y = start_y - (idx * 18.0)
        if row_y < plot_bottom + 14:
            break
        bar_w = bar_max_w * (value / max_value)
        pdf.setFillColorRGB(0.88, 0.92, 0.97)
        pdf.roundRect(axis_x, row_y - 7, bar_max_w, 10, 4, stroke=0, fill=1)
        pdf.setFillColorRGB(*_risk_color(value / max_value * 100.0))
        pdf.roundRect(axis_x, row_y - 7, max(2.0, bar_w), 10, 4, stroke=0, fill=1)
        pdf.setFillColorRGB(*TEXT)
        pdf.setFont(font_name, 9.0)
        pdf.drawRightString(axis_x - 8, row_y - 1, _trim_label(label, 20))
        pdf.drawString(axis_x + bar_w + 4, row_y - 1, f"{value:.1f}")

    y = plot_bottom - 12
    note = str(section.get("note") or "").strip()
    if note:
        pdf.setFont(font_name, 8.7)
        pdf.setFillColorRGB(*MUTED)
        for line in _wrap_text(note, 96)[:3]:
            pdf.drawString(margin_x + 16, y, line)
            y -= 11

    return card_y - 16


def _draw_line_chart(
    pdf: canvas.Canvas,
    font_name: str,
    width: float,
    margin_x: float,
    y: float,
    section: dict[str, Any],
    ensure_space: Callable[[float, float], float],
) -> float:
    title = str(section.get("title") or "Line Chart")
    raw_points = section.get("points") or []
    points: list[tuple[str, float]] = []
    for raw in raw_points:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or raw.get("name") or "")
        value = _safe_float(raw.get("value"))
        if label:
            points.append((label, value))

    points = points[-24:]
    chart_h = 176.0
    y = ensure_space(y, chart_h + 64)
    card_y = y - chart_h - 46
    card_h = chart_h + 40
    pdf.setFillColorRGB(*WHITE)
    pdf.setStrokeColorRGB(*BORDER)
    pdf.roundRect(margin_x, card_y, width - margin_x * 2, card_h, 8, stroke=1, fill=1)

    pdf.setFont(font_name, 11.5)
    pdf.setFillColorRGB(*NAVY)
    pdf.drawString(margin_x + 16, y - 17, title)
    y -= 30

    if not points:
        pdf.setFont(font_name, 9.5)
        pdf.setFillColorRGB(*MUTED)
        pdf.drawString(margin_x + 16, y, "No chart data")
        return card_y - 16

    plot_top = y - 10
    plot_bottom = y - chart_h + 28
    left_x = margin_x + 58
    right_x = width - margin_x - 30

    values = [v for _, v in points]
    max_value = _safe_float(section.get("max_value"))
    min_value = _safe_float(section.get("min_value"))
    if max_value <= min_value:
        max_value = max(values)
    min_value = min(min_value, min(values), 0.0)
    if max_value <= min_value:
        max_value = min_value + 1.0

    pdf.setStrokeColorRGB(0.82, 0.86, 0.92)
    pdf.setLineWidth(0.8)
    pdf.line(left_x, plot_bottom, right_x, plot_bottom)
    pdf.line(left_x, plot_bottom, left_x, plot_top)

    pdf.setFont(font_name, 8.2)
    pdf.setFillColorRGB(*MUTED)
    for tick in (min_value, (min_value + max_value) / 2.0, max_value):
        ty = plot_bottom + ((tick - min_value) / (max_value - min_value)) * (plot_top - plot_bottom)
        pdf.line(left_x - 2, ty, left_x + 2, ty)
        pdf.drawRightString(left_x - 6, ty - 3, f"{tick:.0f}")

    point_xy: list[tuple[float, float]] = []
    count = len(points)
    for idx, (_, value) in enumerate(points):
        x = (left_x + right_x) / 2.0 if count == 1 else left_x + (idx / (count - 1)) * (right_x - left_x)
        y_val = plot_bottom + ((value - min_value) / (max_value - min_value)) * (plot_top - plot_bottom)
        point_xy.append((x, y_val))

    pdf.setStrokeColorRGB(*BLUE)
    pdf.setLineWidth(1.7)
    for idx in range(len(point_xy) - 1):
        x1, y1 = point_xy[idx]
        x2, y2 = point_xy[idx + 1]
        pdf.line(x1, y1, x2, y2)

    pdf.setFillColorRGB(*BLUE)
    for idx, ((x, y_val), (label, value)) in enumerate(zip(point_xy, points)):
        pdf.circle(x, y_val, 2.5, stroke=0, fill=1)
        if len(points) <= 10 or idx in {0, len(points) // 2, len(points) - 1}:
            pdf.setFont(font_name, 8.3)
            pdf.setFillColorRGB(*TEXT)
            pdf.drawCentredString(x, y_val + 7, f"{value:.1f}")
            pdf.setFillColorRGB(*BLUE)
        if idx in {0, len(points) // 2, len(points) - 1}:
            pdf.setFont(font_name, 8.3)
            pdf.setFillColorRGB(*TEXT)
            pdf.drawCentredString(x, plot_bottom - 12, _short_date(label))
            pdf.setFillColorRGB(*BLUE)

    y = plot_bottom - 24
    note = str(section.get("note") or "").strip()
    if note:
        pdf.setFont(font_name, 8.7)
        pdf.setFillColorRGB(*MUTED)
        for line in _wrap_text(note, 96)[:3]:
            pdf.drawString(margin_x + 16, y, line)
            y -= 11

    return card_y - 16


def _safe_float(value: Any) -> float:
    try:
        if isinstance(value, str):
            match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
            if match:
                return float(match.group(0))
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _first_number(value: str) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(match.group(0)) if match else 0.0


def _risk_color(score_0_100: float) -> tuple[float, float, float]:
    if score_0_100 < 30:
        return GREEN
    if score_0_100 < 60:
        return GOLD
    if score_0_100 < 80:
        return ORANGE
    return RED


def _trim_label(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "."


def _short_date(value: str) -> str:
    text = value.strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[5:10]
    return _trim_label(text, 10)


def _wrap_text(value: str, limit: int) -> list[str]:
    text = str(value)
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = text
    while len(current) > limit:
        split_at = current.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(current[:split_at].rstrip())
        current = current[split_at:].lstrip()
    if current:
        chunks.append(current)
    return chunks


def _wrap_text_to_width(value: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    text = _insert_break_points(str(value).strip())
    if not text:
        return [""]
    words = text.split()
    if not words:
        return [text]

    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if pdfmetrics.stringWidth(word, font_name, font_size) <= max_width:
            current = word
        else:
            broken = _break_long_token(word, font_name, font_size, max_width)
            chunks.extend(broken[:-1])
            current = broken[-1] if broken else ""
    if current:
        chunks.append(current)
    return chunks or [text]


def _insert_break_points(value: str) -> str:
    text = value
    for mark in (";", "/", "|", ","):
        text = text.replace(mark, f"{mark} ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _break_long_token(token: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    pieces: list[str] = []
    current = ""
    for char in token:
        candidate = current + char
        if current and pdfmetrics.stringWidth(candidate, font_name, font_size) > max_width:
            pieces.append(current)
            current = char
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces or [token]
