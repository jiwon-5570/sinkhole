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

    pdf = canvas.Canvas(str(report_path), pagesize=A4)
    width, height = A4
    margin_x = 50
    top_margin = 56
    bottom_margin = 56
    y = height - top_margin

    pdf.setTitle(title)
    pdf.setAuthor("Jiwon Kang")
    pdf.setSubject("Sinkhole analysis report")

    def new_page() -> None:
        nonlocal y
        pdf.showPage()
        pdf.setFont(font_name, 10.5)
        y = height - top_margin

    def ensure_space(current_y: float, needed_height: float) -> float:
        nonlocal y
        if current_y - needed_height < bottom_margin:
            new_page()
            return y
        return current_y

    pdf.setFont(font_name, 16)
    pdf.drawString(margin_x, y, title)
    y -= 22

    pdf.setFont(font_name, 9)
    generated = generated_at_text or datetime.now().isoformat(timespec="seconds")
    pdf.drawString(margin_x, y, f"Generated: {generated}")
    y -= 28

    pdf.setFont(font_name, 10.5)
    for line in lines:
        wrapped = _wrap_text(str(line), 88)
        if not wrapped:
            wrapped = [""]
        for chunk in wrapped:
            y = ensure_space(y, 16)
            pdf.drawString(margin_x, y, chunk)
            y -= 16

    if chart_sections:
        y = ensure_space(y, 28)
        pdf.setFont(font_name, 12)
        pdf.drawString(margin_x, y, "Analysis Charts")
        y -= 20
        pdf.setFont(font_name, 10.5)

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
            else:
                # Unknown chart type: skip safely so PDF generation never fails.
                continue

    pdf.save()
    return report_path


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
        try:
            value = float(raw.get("value") or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if not label:
            continue
        items.append((label, max(0.0, value)))

    items = items[:10]
    chart_h = max(92.0, 24.0 + len(items) * 18.0)
    y = ensure_space(y, chart_h + 44)

    pdf.setFont(font_name, 11.5)
    pdf.drawString(margin_x, y, title)
    y -= 16
    pdf.setFont(font_name, 10.5)

    if not items:
        pdf.setFont(font_name, 9.5)
        pdf.drawString(margin_x, y, "No chart data")
        return y - 20

    plot_top = y
    plot_bottom = y - chart_h
    axis_x = margin_x + 145
    right_x = width - margin_x - 20
    bar_max_w = max(100.0, right_x - axis_x - 8)

    max_value = _safe_float(section.get("max_value"))
    if max_value <= 0:
        max_value = max(value for _, value in items)
    if max_value <= 0:
        max_value = 1.0

    pdf.setStrokeColorRGB(0.75, 0.75, 0.75)
    pdf.setLineWidth(1.0)
    pdf.line(axis_x, plot_bottom + 10, axis_x, plot_top - 6)
    pdf.line(axis_x, plot_bottom + 10, right_x, plot_bottom + 10)

    pdf.setFont(font_name, 8.5)
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

        pdf.setFillColorRGB(0.20, 0.45, 0.80)
        pdf.rect(axis_x, row_y - 7, bar_w, 10, stroke=0, fill=1)

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont(font_name, 9.0)
        pdf.drawRightString(axis_x - 6, row_y - 1, _trim_label(label, 18))
        pdf.drawString(axis_x + bar_w + 4, row_y - 1, f"{value:.1f}")

    y = plot_bottom - 10
    note = str(section.get("note") or "").strip()
    if note:
        wrapped = _wrap_text(note, 96)
        y = ensure_space(y, len(wrapped) * 12 + 8)
        pdf.setFont(font_name, 9)
        for line in wrapped:
            pdf.drawString(margin_x, y, line)
            y -= 12

    return y - 8


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
        try:
            value = float(raw.get("value") or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if not label:
            continue
        points.append((label, value))

    points = points[-24:]
    chart_h = 176.0
    y = ensure_space(y, chart_h + 44)

    pdf.setFont(font_name, 11.5)
    pdf.drawString(margin_x, y, title)
    y -= 16
    pdf.setFont(font_name, 10.5)

    if not points:
        pdf.setFont(font_name, 9.5)
        pdf.drawString(margin_x, y, "No chart data")
        return y - 20

    plot_top = y - 10
    plot_bottom = y - chart_h + 28
    left_x = margin_x + 40
    right_x = width - margin_x - 20

    values = [v for _, v in points]
    max_value = _safe_float(section.get("max_value"))
    min_value = _safe_float(section.get("min_value"))
    if max_value <= min_value:
        max_value = max(values)
    min_value = min(min_value, min(values), 0.0)
    if max_value <= min_value:
        max_value = min_value + 1.0

    pdf.setStrokeColorRGB(0.75, 0.75, 0.75)
    pdf.setLineWidth(1.0)
    pdf.line(left_x, plot_bottom, right_x, plot_bottom)
    pdf.line(left_x, plot_bottom, left_x, plot_top)

    pdf.setFont(font_name, 8.5)
    for tick in (min_value, (min_value + max_value) / 2.0, max_value):
        ty = plot_bottom + ((tick - min_value) / (max_value - min_value)) * (plot_top - plot_bottom)
        pdf.line(left_x - 2, ty, left_x + 2, ty)
        pdf.drawRightString(left_x - 6, ty - 3, f"{tick:.0f}")

    point_xy: list[tuple[float, float]] = []
    count = len(points)
    for idx, (_, value) in enumerate(points):
        if count == 1:
            x = (left_x + right_x) / 2.0
        else:
            x = left_x + (idx / (count - 1)) * (right_x - left_x)
        y_val = plot_bottom + ((value - min_value) / (max_value - min_value)) * (plot_top - plot_bottom)
        point_xy.append((x, y_val))

    pdf.setStrokeColorRGB(0.15, 0.58, 0.42)
    pdf.setLineWidth(1.6)
    for idx in range(len(point_xy) - 1):
        x1, y1 = point_xy[idx]
        x2, y2 = point_xy[idx + 1]
        pdf.line(x1, y1, x2, y2)

    pdf.setFillColorRGB(0.15, 0.58, 0.42)
    for idx, ((x, y_val), (label, value)) in enumerate(zip(point_xy, points)):
        pdf.circle(x, y_val, 2.4, stroke=0, fill=1)
        if len(points) <= 10 or idx in {0, len(points) // 2, len(points) - 1}:
            pdf.setFont(font_name, 8.5)
            pdf.setFillColorRGB(0, 0, 0)
            pdf.drawCentredString(x, y_val + 7, f"{value:.1f}")
            pdf.setFillColorRGB(0.15, 0.58, 0.42)

        if idx in {0, len(points) // 2, len(points) - 1}:
            pdf.setFont(font_name, 8.5)
            pdf.setFillColorRGB(0, 0, 0)
            pdf.drawCentredString(x, plot_bottom - 12, _short_date(label))
            pdf.setFillColorRGB(0.15, 0.58, 0.42)

    y = plot_bottom - 20
    note = str(section.get("note") or "").strip()
    if note:
        wrapped = _wrap_text(note, 96)
        y = ensure_space(y, len(wrapped) * 12 + 8)
        pdf.setFont(font_name, 9)
        pdf.setFillColorRGB(0, 0, 0)
        for line in wrapped:
            pdf.drawString(margin_x, y, line)
            y -= 12

    return y - 8


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
    if len(value) <= limit:
        return [value]
    chunks: list[str] = []
    current = value
    while len(current) > limit:
        split_at = current.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(current[:split_at].rstrip())
        current = current[split_at:].lstrip()
    if current:
        chunks.append(current)
    return chunks
