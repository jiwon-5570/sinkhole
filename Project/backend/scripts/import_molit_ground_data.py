from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Allow `python scripts/import_molit_ground_data.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import settings
from app.db.core import connect
from app.db.migrate import apply_schema


BACKEND_DIR = Path(__file__).resolve().parents[1]
RAW_PUBLIC_DIR = BACKEND_DIR / "data" / "raw" / "public"
LAYERS_DIR = RAW_PUBLIC_DIR / "molit_ground_layers"
BOREHOLES_DIR = RAW_PUBLIC_DIR / "molit_boreholes"

SOURCE_LAYERS = "국토교통부_지반정보_지층정보"
SOURCE_BOREHOLES = "국토교통부_지반정보_시추공"

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


COMMON_ALIASES = {
    "borehole_code": (
        "시추공번호",
        "시추공명",
        "시추공코드",
        "공번",
        "boreholecode",
        "boreholeno",
        "boreholename",
        "bhno",
        "bhid",
        "boreno",
    ),
    "project_name": (
        "사업명",
        "공사명",
        "프로젝트명",
        "보고서명",
        "현장명",
        "projectname",
        "prjname",
        "sitename",
    ),
    "address": ("주소", "소재지", "현장주소", "지점주소", "address", "addr"),
    "latitude": ("위도", "lat", "latitude", "y좌표", "ycoord", "ycoordinate"),
    "longitude": ("경도", "lon", "lng", "longitude", "x좌표", "xcoord", "xcoordinate"),
}

LAYER_ALIASES = {
    **COMMON_ALIASES,
    "layer_sequence": ("지층순번", "층순번", "층번호", "순번", "layerseq", "layerno", "seq"),
    "top_depth_m": (
        "상부심도",
        "시작심도",
        "상단심도",
        "심도상부",
        "depthfrom",
        "fromdepth",
        "topdepth",
    ),
    "bottom_depth_m": (
        "하부심도",
        "종료심도",
        "하단심도",
        "심도하부",
        "depthto",
        "todepth",
        "bottomdepth",
    ),
    "thickness_m": ("두께", "층후", "층두께", "thickness", "layerthickness"),
    "layer_name": ("지층명", "지층명분류", "토질명", "토층명", "strataname", "layername", "soilname"),
    "layer_color": ("지층색상", "색상", "color", "colour", "layercolor"),
    "layer_description": ("지층정보", "지층설명", "설명", "특징", "비고", "description", "remark"),
    "soil_class": ("토질분류", "지층분류", "uscs", "soilclass", "soiltype"),
    "n_value": ("n치", "n값", "nvalue", "표준관입시험n값", "sptn"),
}

BOREHOLE_ALIASES = {
    **COMMON_ALIASES,
    "elevation_m": ("표고", "지반고", "해발고도", "elevation", "groundlevel"),
    "total_depth_m": ("굴진심도", "시추심도", "총심도", "depth", "totaldepth", "boredepth"),
    "groundwater_level_m": ("지하수위", "groundwaterlevel", "waterlevel"),
    "borehole_method": ("시추방법", "boringmethod", "boreholemethod"),
    "borehole_type": ("시추공종류", "시추공구분", "boreholetype", "boringtype"),
}


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s_()\[\]{}\-./:·]+", "", str(value).strip().lower())


def _source_file(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(BACKEND_DIR))
    except ValueError:
        return str(resolved)


def _detect_encoding(path: Path, preferred: str | None = None) -> str:
    if preferred:
        return preferred
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                handle.read(4096)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8-sig"


def _build_column_map(fieldnames: list[str], aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    normalized = {name: _normalize_header(name) for name in fieldnames}
    result: dict[str, str] = {}
    for target, names in aliases.items():
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


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _int_value(value: Any) -> int | None:
    number = _float_value(value)
    if number is None:
        return None
    return int(number)


def _coordinate_pair(latitude: Any, longitude: Any) -> tuple[float | None, float | None]:
    lat = _float_value(latitude)
    lon = _float_value(longitude)
    if lat is None or lon is None:
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon


def _value(row: dict[str, Any], column_map: dict[str, str], key: str) -> Any:
    column = column_map.get(key)
    return row.get(column) if column else None


def _csv_files(paths: list[str] | None, default_dir: Path) -> list[Path]:
    if paths:
        return [Path(path).expanduser().resolve() for path in paths]
    default_dir.mkdir(parents=True, exist_ok=True)
    return sorted(default_dir.glob("*.csv"))


def import_layers(
    conn: sqlite3.Connection,
    path: Path,
    *,
    encoding: str | None = None,
    keep_raw: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    actual_encoding = _detect_encoding(path, encoding)
    source_file = _source_file(path)
    with path.open("r", encoding=actual_encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        column_map = _build_column_map(fieldnames, LAYER_ALIASES)
        if dry_run:
            return {
                "file": source_file,
                "kind": "layers",
                "encoding": actual_encoding,
                "columns": fieldnames,
                "mapped_columns": column_map,
                "imported": 0,
            }

        conn.execute("DELETE FROM molit_ground_layers WHERE source_file = ?", (source_file,))
        batch: list[tuple[Any, ...]] = []
        imported = 0
        for row_number, row in enumerate(reader, start=2):
            if limit is not None and imported >= limit:
                break
            lat, lon = _coordinate_pair(_value(row, column_map, "latitude"), _value(row, column_map, "longitude"))
            payload = (
                _clean_text(_value(row, column_map, "borehole_code")),
                _clean_text(_value(row, column_map, "project_name")),
                _clean_text(_value(row, column_map, "address")),
                lat,
                lon,
                _int_value(_value(row, column_map, "layer_sequence")),
                _float_value(_value(row, column_map, "top_depth_m")),
                _float_value(_value(row, column_map, "bottom_depth_m")),
                _float_value(_value(row, column_map, "thickness_m")),
                _clean_text(_value(row, column_map, "layer_name")),
                _clean_text(_value(row, column_map, "layer_color")),
                _clean_text(_value(row, column_map, "layer_description")),
                _clean_text(_value(row, column_map, "soil_class")),
                _float_value(_value(row, column_map, "n_value")),
                SOURCE_LAYERS,
                source_file,
                row_number,
                json.dumps(row, ensure_ascii=False) if keep_raw else None,
            )
            batch.append(payload)
            imported += 1
            if len(batch) >= 5000:
                _insert_layers(conn, batch)
                batch.clear()
        if batch:
            _insert_layers(conn, batch)
    return {
        "file": source_file,
        "kind": "layers",
        "encoding": actual_encoding,
        "mapped_columns": column_map,
        "imported": imported,
    }


def _insert_layers(conn: sqlite3.Connection, batch: list[tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO molit_ground_layers(
            borehole_code, project_name, address, latitude, longitude,
            layer_sequence, top_depth_m, bottom_depth_m, thickness_m,
            layer_name, layer_color, layer_description, soil_class, n_value,
            source_name, source_file, source_row_number, raw_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )


def import_boreholes(
    conn: sqlite3.Connection,
    path: Path,
    *,
    encoding: str | None = None,
    keep_raw: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    actual_encoding = _detect_encoding(path, encoding)
    source_file = _source_file(path)
    with path.open("r", encoding=actual_encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        column_map = _build_column_map(fieldnames, BOREHOLE_ALIASES)
        if dry_run:
            return {
                "file": source_file,
                "kind": "boreholes",
                "encoding": actual_encoding,
                "columns": fieldnames,
                "mapped_columns": column_map,
                "imported": 0,
            }

        conn.execute("DELETE FROM molit_ground_boreholes WHERE source_file = ?", (source_file,))
        batch: list[tuple[Any, ...]] = []
        imported = 0
        for row_number, row in enumerate(reader, start=2):
            if limit is not None and imported >= limit:
                break
            lat, lon = _coordinate_pair(_value(row, column_map, "latitude"), _value(row, column_map, "longitude"))
            payload = (
                _clean_text(_value(row, column_map, "borehole_code")),
                _clean_text(_value(row, column_map, "project_name")),
                _clean_text(_value(row, column_map, "address")),
                lat,
                lon,
                None,
                None,
                "WGS84" if lat is not None and lon is not None else None,
                _float_value(_value(row, column_map, "elevation_m")),
                _float_value(_value(row, column_map, "total_depth_m")),
                _float_value(_value(row, column_map, "groundwater_level_m")),
                _clean_text(_value(row, column_map, "borehole_method")),
                _clean_text(_value(row, column_map, "borehole_type")),
                SOURCE_BOREHOLES,
                _clean_text(_value(row, column_map, "borehole_code")),
                source_file,
                row_number,
                json.dumps(row, ensure_ascii=False) if keep_raw else None,
            )
            batch.append(payload)
            imported += 1
            if len(batch) >= 5000:
                _insert_boreholes(conn, batch)
                batch.clear()
        if batch:
            _insert_boreholes(conn, batch)
    return {
        "file": source_file,
        "kind": "boreholes",
        "encoding": actual_encoding,
        "mapped_columns": column_map,
        "imported": imported,
    }


def _insert_boreholes(conn: sqlite3.Connection, batch: list[tuple[Any, ...]]) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO molit_ground_boreholes(
            borehole_code, project_name, address, latitude, longitude,
            raw_x, raw_y, coordinate_crs, elevation_m, total_depth_m,
            groundwater_level_m, borehole_method, borehole_type,
            source_name, source_record_id, source_file, source_row_number, raw_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )


def _count_rows(conn: sqlite3.Connection) -> dict[str, int]:
    layers = conn.execute("SELECT COUNT(*) FROM molit_ground_layers").fetchone()[0]
    boreholes = conn.execute("SELECT COUNT(*) FROM molit_ground_boreholes").fetchone()[0]
    layer_coords = conn.execute(
        """
        SELECT COUNT(*)
        FROM molit_ground_layers l
        LEFT JOIN molit_ground_boreholes b
          ON b.borehole_code IS NOT NULL
         AND l.borehole_code IS NOT NULL
         AND b.borehole_code = l.borehole_code
        WHERE COALESCE(l.latitude, b.latitude) IS NOT NULL
          AND COALESCE(l.longitude, b.longitude) IS NOT NULL
        """
    ).fetchone()[0]
    return {
        "ground_layers": int(layers),
        "ground_boreholes": int(boreholes),
        "ground_layers_with_coordinates": int(layer_coords),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import MOLIT ground borehole/layer CSV files.")
    parser.add_argument("--layers-file", action="append", help="Path to a ground layer CSV file.")
    parser.add_argument("--boreholes-file", action="append", help="Path to a borehole CSV file.")
    parser.add_argument("--encoding", help="CSV encoding. Auto-detected when omitted.")
    parser.add_argument("--keep-raw", action="store_true", help="Store each original CSV row as JSON. Increases DB size.")
    parser.add_argument("--dry-run", action="store_true", help="Only show detected columns; do not write DB rows.")
    parser.add_argument("--limit", type=int, help="Import only the first N rows per file. Useful for testing.")
    args = parser.parse_args()

    layer_files = _csv_files(args.layers_file, LAYERS_DIR)
    borehole_files = _csv_files(args.boreholes_file, BOREHOLES_DIR)

    if not layer_files and not borehole_files:
        print("No CSV files found.")
        print(f"Put layer CSV files here: {LAYERS_DIR}")
        print(f"Optional borehole CSV files here: {BOREHOLES_DIR}")
        return

    conn = connect(settings.db_path)
    try:
        apply_schema(conn, settings.schema_path)
        results: list[dict[str, Any]] = []
        for path in borehole_files:
            results.append(
                import_boreholes(
                    conn,
                    path,
                    encoding=args.encoding,
                    keep_raw=args.keep_raw,
                    limit=args.limit,
                    dry_run=args.dry_run,
                )
            )
        for path in layer_files:
            results.append(
                import_layers(
                    conn,
                    path,
                    encoding=args.encoding,
                    keep_raw=args.keep_raw,
                    limit=args.limit,
                    dry_run=args.dry_run,
                )
            )
        if not args.dry_run:
            conn.commit()
        for result in results:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.dry_run:
            print(json.dumps({"db_path": str(settings.db_path), "counts": _count_rows(conn)}, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
