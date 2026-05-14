from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
import hashlib
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import re
import sqlite3
from typing import Any

from app.config.settings import settings
from app.db.core import query_all
from app.services.addressing import region_road_address, road_road_address


SOURCE_NAME = "서울시_도로굴착공사정보_파일"
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xls"}
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
DATE_RE = re.compile(r"(20\d{2}|19\d{2})[.\-/년\s]*(\d{1,2})?[.\-/월\s]*(\d{1,2})?")

ALIASES = {
    "record_id": (
        "관리번호",
        "허가번호",
        "신고번호",
        "접수번호",
        "공사번호",
        "굴착허가번호",
        "id",
        "recordid",
    ),
    "address": (
        "주소",
        "도로명주소",
        "공사위치",
        "위치",
        "굴착위치",
        "점용위치",
        "작업위치",
        "소재지",
        "공사장주소",
        "현장주소",
        "도로명",
        "구간",
    ),
    "sigungu": ("시군구", "자치구", "구", "관할구", "행정구"),
    "dong": ("동", "행정동", "법정동"),
    "road_name": ("도로명", "노선명", "도로", "굴착도로명"),
    "construction_name": ("공사명", "사업명", "현장명", "공사제목", "공사내용"),
    "construction_type": ("공사종류", "공종", "굴착목적", "점용목적", "공사구분", "작업종류"),
    "start_date": ("시작일", "착공일", "공사시작일", "굴착시작일", "허가시작일", "공사기간시작", "startdate"),
    "end_date": ("종료일", "준공일", "완료일", "공사종료일", "굴착종료일", "허가종료일", "공사기간종료", "enddate"),
    "latitude": ("위도", "lat", "latitude", "y좌표", "ycoord"),
    "longitude": ("경도", "lon", "lng", "longitude", "x좌표", "xcoord"),
    "length_m": ("연장", "굴착연장", "길이", "공사연장", "length", "굴착길이"),
    "depth_m": ("깊이", "굴착깊이", "굴착심도", "depth"),
    "width_m": ("폭", "굴착폭", "width"),
    "area_m2": ("면적", "굴착면적", "점용면적", "area"),
}


def construction_import_dir() -> Path:
    return Path(settings.local_construction_file_dir)


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS local_file_import_state (
            source_file TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            file_mtime REAL NOT NULL,
            file_size INTEGER NOT NULL,
            imported_at TEXT NOT NULL,
            imported_rows INTEGER NOT NULL DEFAULT 0,
            skipped_rows INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            message TEXT
        )
        """
    )


def _normalize_header(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "").strip().lower())


def _normalize_text(value: str | None) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "").strip()).lower()


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text


def _float_value(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    match = NUMBER_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _date_value(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    values = _date_values(value)
    return values[0] if values else None


def _date_values(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []

    values: list[str] = []
    for year, month, day in re.findall(r"(20\d{2}|19\d{2})\D{0,3}(\d{1,2})\D{0,3}(\d{1,2})", text):
        try:
            values.append(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            continue
    if values:
        return values

    compact = re.sub(r"\D", "", text)
    if len(compact) >= 8:
        try:
            values.append(datetime.strptime(compact[:8], "%Y%m%d").date().isoformat())
        except ValueError:
            pass
    if len(compact) >= 16:
        try:
            values.append(datetime.strptime(compact[8:16], "%Y%m%d").date().isoformat())
        except ValueError:
            pass
    if values:
        return values

    match = DATE_RE.search(text)
    if not match:
        return []
    year = int(match.group(1))
    month = int(match.group(2) or 1)
    day = int(match.group(3) or 1)
    try:
        return [date(year, month, day).isoformat()]
    except ValueError:
        return []


def _date_range_values(row: dict[str, Any], column_map: dict[str, str]) -> tuple[str | None, str | None]:
    start_column = column_map.get("start_date")
    end_column = column_map.get("end_date")
    if start_column and end_column and start_column == end_column:
        values = _date_values(row.get(start_column))
        if not values:
            return None, None
        return values[0], values[-1] if len(values) > 1 else None
    return _date_value(_value(row, column_map, "start_date")), _date_value(_value(row, column_map, "end_date"))


def _build_column_map(fieldnames: list[str]) -> dict[str, str]:
    normalized = {name: _normalize_header(name) for name in fieldnames}
    result: dict[str, str] = {}
    for target, names in ALIASES.items():
        alias_values = {_normalize_header(name) for name in names}
        for original, key in normalized.items():
            if key in alias_values:
                result[target] = original
                break
        if target in result:
            continue
        for original, key in normalized.items():
            if any(alias and alias in key for alias in alias_values if len(alias) >= 3):
                result[target] = original
                break
    return result


def _value(row: dict[str, Any], column_map: dict[str, str], key: str) -> Any:
    column = column_map.get(key)
    return row.get(column) if column else None


def _detect_encoding(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                handle.read(4096)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8-sig"


def _read_csv_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    encoding = _detect_encoding(path)
    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        fieldnames = list(reader.fieldnames or [])
        return [dict(row) for row in reader], fieldnames


def _read_excel_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("엑셀 파일을 읽으려면 pandas/openpyxl 설치가 필요합니다.") from exc

    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    rows: list[dict[str, Any]] = []
    fieldnames: list[str] = []
    for sheet_name, frame in sheets.items():
        frame = frame.where(frame.notna(), None)
        if not fieldnames:
            fieldnames = [str(column) for column in frame.columns]
        for row in frame.to_dict(orient="records"):
            row["__sheet_name"] = sheet_name
            rows.append(row)
    return rows, fieldnames


def _read_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return _read_excel_rows(path)
    return _read_csv_rows(path)


def _source_key(path: Path) -> str:
    base = construction_import_dir().resolve()
    try:
        return str(path.resolve().relative_to(base)).replace("\\", "/")
    except ValueError:
        return path.name


def _record_id(source_key: str, row_number: int, row: dict[str, Any], column_map: dict[str, str]) -> str:
    raw = _clean_text(_value(row, column_map, "record_id"))
    if raw:
        return f"{source_key}#{raw}"
    material = json.dumps(row, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(material.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{source_key}#row-{row_number}-{digest}"


def _coordinate_pair(row: dict[str, Any], column_map: dict[str, str]) -> tuple[float | None, float | None]:
    lat = _float_value(_value(row, column_map, "latitude"))
    lon = _float_value(_value(row, column_map, "longitude"))
    if lat is None or lon is None:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def _duration_days(start_date: str | None, end_date: str | None) -> int:
    if not start_date or not end_date:
        return 0
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return 0
    return max(0, (end - start).days + 1)


def _is_recent_or_active(start_date: str | None, end_date: str | None) -> bool:
    if not start_date and not end_date:
        return False
    lookback = timedelta(days=settings.public_data_construction_lookback_days)
    cutoff = date.today() - lookback
    for value in (end_date, start_date):
        if not value:
            continue
        try:
            if date.fromisoformat(value) >= cutoff:
                return True
        except ValueError:
            continue
    return False


def _address_text(row: dict[str, Any], column_map: dict[str, str]) -> str:
    parts = [
        _clean_text(_value(row, column_map, "address")),
        _clean_text(_value(row, column_map, "sigungu")),
        _clean_text(_value(row, column_map, "dong")),
        _clean_text(_value(row, column_map, "road_name")),
    ]
    return " ".join(part for part in parts if part)


def _construction_type(row: dict[str, Any], column_map: dict[str, str]) -> str:
    parts = [
        _clean_text(_value(row, column_map, "construction_type")),
        _clean_text(_value(row, column_map, "construction_name")),
    ]
    return " / ".join(part for part in parts if part) or "도로굴착 공사"


def _scale_score(row: dict[str, Any], column_map: dict[str, str], start_date: str | None, end_date: str | None) -> float:
    text = " ".join(str(value or "") for value in row.values())
    length_m = _float_value(_value(row, column_map, "length_m")) or 0.0
    depth_m = _float_value(_value(row, column_map, "depth_m")) or 0.0
    width_m = _float_value(_value(row, column_map, "width_m")) or 0.0
    area_m2 = _float_value(_value(row, column_map, "area_m2")) or 0.0
    duration = _duration_days(start_date, end_date)

    score = 6.0
    if any(keyword in text for keyword in ("굴착", "터파기", "지하", "상수", "하수", "관로", "전력", "통신")):
        score += 2.0
    if any(keyword in text for keyword in ("대형", "심도", "차도", "도로점용")):
        score += 2.0
    if any(keyword in text for keyword in ("소규모", "복구", "포장")):
        score -= 1.0

    score += min(5.0, length_m / 80.0)
    score += min(5.0, depth_m * 1.2)
    score += min(3.0, width_m * 0.5)
    score += min(4.0, area_m2 / 200.0)
    score += min(3.0, duration / 60.0)
    return round(max(3.0, min(20.0, score)), 2)


def _load_regions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = query_all(
        conn,
        """
        SELECT region_id, region_name, latitude, longitude, sido, sigungu
        FROM regions
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """,
    )
    for row in rows:
        row["road_address"] = region_road_address(row)
        row["_norm_candidates"] = [
            _normalize_text(row.get("road_address")),
            _normalize_text(str(row.get("road_address") or "").replace(" 인근", "")),
            _normalize_text(row.get("region_name")),
            _normalize_text(row.get("sigungu")),
        ]
    return rows


def _load_roads(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = query_all(
        conn,
        """
        SELECT road_id, region_id, road_name, center_lat, center_lon
        FROM road_segments
        WHERE center_lat IS NOT NULL AND center_lon IS NOT NULL
        """,
    )
    for row in rows:
        row["road_address"] = road_road_address(row)
        row["_norm_candidates"] = [
            _normalize_text(row.get("road_address")),
            _normalize_text(row.get("road_name")),
        ]
    return rows


def _address_match_score(query: str, candidates: list[str]) -> int:
    query_norm = _normalize_text(query)
    if not query_norm:
        return 0
    score = 0
    for candidate in candidates:
        if not candidate:
            continue
        if query_norm == candidate:
            score = max(score, 1000)
        elif query_norm in candidate or candidate in query_norm:
            score = max(score, 500 + min(len(query_norm), len(candidate)))
        else:
            score += sum(30 for token in re.split(r"\s+", query) if _normalize_text(token) in candidate)
    return score


def _match_region(
    regions: list[dict[str, Any]],
    *,
    address: str,
    latitude: float | None,
    longitude: float | None,
) -> dict[str, Any] | None:
    if latitude is not None and longitude is not None:
        nearest = min(
            regions,
            key=lambda row: _haversine_m(latitude, longitude, float(row["latitude"]), float(row["longitude"])),
            default=None,
        )
        if nearest:
            distance = _haversine_m(latitude, longitude, float(nearest["latitude"]), float(nearest["longitude"]))
            if distance <= max(settings.public_data_match_radius_m, 8000.0):
                return nearest

    scored = [
        (_address_match_score(address, row["_norm_candidates"]), row)
        for row in regions
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 30:
        return scored[0][1]
    return None


def _match_road(
    roads: list[dict[str, Any]],
    *,
    region_id: int | None,
    address: str,
    latitude: float | None,
    longitude: float | None,
) -> dict[str, Any] | None:
    candidates = [row for row in roads if region_id is None or int(row.get("region_id") or 0) == region_id]
    if not candidates:
        return None
    if latitude is not None and longitude is not None:
        nearest = min(
            candidates,
            key=lambda row: _haversine_m(latitude, longitude, float(row["center_lat"]), float(row["center_lon"])),
            default=None,
        )
        if nearest:
            distance = _haversine_m(latitude, longitude, float(nearest["center_lat"]), float(nearest["center_lon"]))
            if distance <= max(settings.public_data_match_radius_m, 3000.0):
                return nearest
    scored = [(_address_match_score(address, row["_norm_candidates"]), row) for row in candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] >= 30:
        return scored[0][1]
    return None


def _file_records_changed(conn: sqlite3.Connection, path: Path, source_key: str) -> bool:
    stat = path.stat()
    row = conn.execute(
        """
        SELECT file_mtime, file_size, status
        FROM local_file_import_state
        WHERE source_file = ? AND source_name = ?
        """,
        (source_key, SOURCE_NAME),
    ).fetchone()
    return not row or float(row["file_mtime"]) != float(stat.st_mtime) or int(row["file_size"]) != int(stat.st_size)


def _delete_file_rows(conn: sqlite3.Connection, source_key: str) -> None:
    pattern = f"{source_key}#%"
    conn.execute(
        "DELETE FROM construction_events WHERE source_name = ? AND source_record_id LIKE ?",
        (SOURCE_NAME, pattern),
    )
    conn.execute(
        "DELETE FROM road_construction_events WHERE construction_type LIKE ?",
        (f"[{SOURCE_NAME}:{source_key}]%",),
    )


def _insert_row(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    column_map: dict[str, str],
    source_key: str,
    row_number: int,
    regions: list[dict[str, Any]],
    roads: list[dict[str, Any]],
) -> bool:
    start_date, end_date = _date_range_values(row, column_map)
    if not _is_recent_or_active(start_date, end_date):
        return False

    latitude, longitude = _coordinate_pair(row, column_map)
    address = _address_text(row, column_map)
    matched_region = _match_region(regions, address=address, latitude=latitude, longitude=longitude)
    if not matched_region:
        return False

    region_id = int(matched_region["region_id"])
    construction_type = _construction_type(row, column_map)
    scale_score = _scale_score(row, column_map, start_date, end_date)
    source_record_id = _record_id(source_key, row_number, row, column_map)
    conn.execute(
        """
        INSERT INTO construction_events(
            region_id, construction_type, start_date, scale_score,
            source_name, source_record_id, address, latitude, longitude
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            construction_type[:200],
            start_date,
            scale_score,
            SOURCE_NAME,
            source_record_id,
            address[:300] if address else region_road_address(matched_region),
            latitude,
            longitude,
        ),
    )

    matched_road = _match_road(roads, region_id=region_id, address=address, latitude=latitude, longitude=longitude)
    if matched_road:
        conn.execute(
            """
            INSERT INTO road_construction_events(
                road_id, construction_type, start_date, end_date, scale_score, impact_score
            )
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                int(matched_road["road_id"]),
                f"[{SOURCE_NAME}:{source_key}] {construction_type}"[:200],
                start_date,
                end_date,
                scale_score,
                scale_score,
            ),
        )

    return True


def _source_files() -> list[Path]:
    root = construction_import_dir()
    root.mkdir(parents=True, exist_ok=True)
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and not path.name.startswith("~$")
    )


def import_local_construction_files(conn: sqlite3.Connection, *, force: bool = False) -> dict[str, Any]:
    _ensure_tables(conn)
    files = _source_files()
    regions = _load_regions(conn)
    roads = _load_roads(conn)
    changed = False
    results: list[dict[str, Any]] = []

    existing = {
        row["source_file"]
        for row in query_all(
            conn,
            "SELECT source_file FROM local_file_import_state WHERE source_name = ?",
            (SOURCE_NAME,),
        )
    }
    current = {_source_key(path) for path in files}
    for deleted in sorted(existing - current):
        _delete_file_rows(conn, deleted)
        conn.execute("DELETE FROM local_file_import_state WHERE source_file = ? AND source_name = ?", (deleted, SOURCE_NAME))
        changed = True
        results.append({"file": deleted, "status": "deleted", "imported_rows": 0, "skipped_rows": 0})

    for path in files:
        source_key = _source_key(path)
        stat = path.stat()
        if not force and not _file_records_changed(conn, path, source_key):
            results.append({"file": source_key, "status": "unchanged", "imported_rows": 0, "skipped_rows": 0})
            continue

        _delete_file_rows(conn, source_key)
        imported = 0
        skipped = 0
        status = "imported"
        message = None
        try:
            rows, fieldnames = _read_rows(path)
            column_map = _build_column_map(fieldnames)
            for row_number, row in enumerate(rows, start=2):
                if _insert_row(conn, row, column_map, source_key, row_number, regions, roads):
                    imported += 1
                else:
                    skipped += 1
        except Exception as exc:
            status = "error"
            message = str(exc)
            skipped += 1

        conn.execute(
            """
            INSERT OR REPLACE INTO local_file_import_state(
                source_file, source_name, file_mtime, file_size, imported_at,
                imported_rows, skipped_rows, status, message
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_key,
                SOURCE_NAME,
                float(stat.st_mtime),
                int(stat.st_size),
                datetime.now().isoformat(timespec="seconds"),
                imported,
                skipped,
                status,
                message,
            ),
        )
        changed = True
        results.append({
            "file": source_key,
            "status": status,
            "imported_rows": imported,
            "skipped_rows": skipped,
            "message": message,
        })

    if changed:
        conn.execute("DELETE FROM feature_dataset")
        conn.execute("DELETE FROM road_feature_dataset")

    return {
        "enabled": bool(settings.local_construction_file_import_enabled),
        "directory": str(construction_import_dir()),
        "changed": changed,
        "files": results,
    }


def local_construction_import_status(conn: sqlite3.Connection) -> dict[str, Any]:
    _ensure_tables(conn)
    rows = query_all(
        conn,
        """
        SELECT source_file, imported_at, imported_rows, skipped_rows, status, message
        FROM local_file_import_state
        WHERE source_name = ?
        ORDER BY source_file
        """,
        (SOURCE_NAME,),
    )
    count = conn.execute(
        "SELECT COUNT(*) FROM construction_events WHERE source_name = ?",
        (SOURCE_NAME,),
    ).fetchone()[0]
    return {
        "enabled": bool(settings.local_construction_file_import_enabled),
        "directory": str(construction_import_dir()),
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "imported_construction_events": int(count),
        "files": rows,
    }
