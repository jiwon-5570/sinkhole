from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
import sqlite3
from typing import Any

import requests

from app.config.settings import settings
from app.db.core import query_all, query_one


SOURCE_PREFIX = "seoul_open_data"


@dataclass(frozen=True)
class SeoulOpenDataSource:
    name: str
    label: str
    service: str
    normalizer: str


def _sources() -> list[SeoulOpenDataSource]:
    candidates = [
        SeoulOpenDataSource(
            "seoul_groundwater_observations",
            "Seoul groundwater observation network",
            settings.seoul_groundwater_observation_service,
            "groundwater",
        ),
        SeoulOpenDataSource(
            "seoul_rainfall",
            "Seoul rainfall gauges",
            settings.seoul_rainfall_service,
            "rainfall",
        ),
        SeoulOpenDataSource(
            "seoul_sewer_levels",
            "Seoul sewer pipe water levels",
            settings.seoul_sewer_level_service,
            "sewer_level",
        ),
        SeoulOpenDataSource(
            "seoul_road_excavation",
            "Seoul road excavation status",
            settings.seoul_road_excavation_service,
            "road_excavation",
        ),
    ]
    return [source for source in candidates if source.service]


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS seoul_groundwater_observations (
            id INTEGER PRIMARY KEY,
            region_id INTEGER,
            station_id TEXT,
            station_name TEXT,
            observed_at TEXT,
            groundwater_level REAL,
            water_temperature REAL,
            electrical_conductivity REAL,
            source_name TEXT,
            source_record_id TEXT,
            raw_json TEXT,
            FOREIGN KEY (region_id) REFERENCES regions(region_id),
            UNIQUE(source_name, source_record_id)
        );

        CREATE TABLE IF NOT EXISTS seoul_sewer_levels (
            id INTEGER PRIMARY KEY,
            region_id INTEGER,
            station_id TEXT,
            station_name TEXT,
            observed_at TEXT,
            sewer_level REAL,
            communication_status TEXT,
            source_name TEXT,
            source_record_id TEXT,
            raw_json TEXT,
            FOREIGN KEY (region_id) REFERENCES regions(region_id),
            UNIQUE(source_name, source_record_id)
        );
        """
    )
    groundwater_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(groundwater_data)")}
    if "station_id" not in groundwater_columns:
        conn.execute("ALTER TABLE groundwater_data ADD COLUMN station_id TEXT")
    if "station_name" not in groundwater_columns:
        conn.execute("ALTER TABLE groundwater_data ADD COLUMN station_name TEXT")


def _redact(value: Any) -> str:
    text = str(value)
    if settings.seoul_open_data_api_key:
        text = text.replace(settings.seoul_open_data_api_key, "[SEOUL_OPEN_DATA_API_KEY]")
    return text


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _norm(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).lower()


def _ci_get(item: dict[str, Any], aliases: tuple[str, ...], default: Any = None) -> Any:
    normalized = {_norm(key): key for key in item.keys()}
    for alias in aliases:
        key = normalized.get(_norm(alias))
        if key is not None:
            return item.get(key)
    for alias in aliases:
        alias_norm = _norm(alias)
        if len(alias_norm) < 2:
            continue
        for key_norm, original in normalized.items():
            if alias_norm in key_norm or key_norm in alias_norm:
                return item.get(original)
    return default


def _text(item: dict[str, Any], aliases: tuple[str, ...], default: str = "") -> str:
    value = _ci_get(item, aliases, default)
    if value is None:
        return default
    return str(value).strip()


def _float(item: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    value = _ci_get(item, aliases)
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _date_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now().date().isoformat()
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, fmt).isoformat(timespec="seconds")
        except ValueError:
            pass
    compact = re.sub(r"\D", "", text)
    if len(compact) >= 8:
        for fmt, size in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
            if len(compact) >= size:
                try:
                    return datetime.strptime(compact[:size], fmt).isoformat(timespec="seconds")
                except ValueError:
                    pass
    return text


def _record_date(observed_at: str) -> str:
    return observed_at.split("T", 1)[0].split(" ", 1)[0]


def _source_record_id(source: SeoulOpenDataSource, item: dict[str, Any], *parts: Any) -> str:
    clean = [str(part).strip() for part in parts if str(part or "").strip()]
    if clean:
        return ":".join(clean)
    return f"{source.name}:{abs(hash(_stable_json(item)))}"


def _load_regions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return query_all(
        conn,
        """
        SELECT region_id, region_name, sido, sigungu, latitude, longitude
        FROM regions
        ORDER BY region_id
        """,
    )


def _region_for_item(item: dict[str, Any], regions: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = _norm(" ".join(str(value or "") for value in item.values()))
    for region in regions:
        for key in ("sigungu", "region_name", "sido"):
            value = _norm(str(region.get(key) or ""))
            if value and value in text:
                return region
    return regions[0] if len(regions) == 1 else None


def _seoul_url(service: str, start: int, end: int) -> str:
    base = settings.seoul_open_data_base_url.rstrip("/")
    key = settings.seoul_open_data_api_key or ""
    return f"{base}/{key}/json/{service}/{start}/{end}/"


def _seoul_url_with_tail(service: str, start: int, end: int, tail: str) -> str:
    return f"{_seoul_url(service, start, end).rstrip('/')}/{tail.strip('/')}/"


def _extract_rows(payload: dict[str, Any], service: str) -> tuple[list[dict[str, Any]], int]:
    body = payload.get(service)
    if not isinstance(body, dict):
        for value in payload.values():
            if isinstance(value, dict) and "row" in value:
                body = value
                break
    if not isinstance(body, dict):
        error = payload.get("RESULT") if isinstance(payload.get("RESULT"), dict) else payload
        code = error.get("CODE") if isinstance(error, dict) else None
        message = error.get("MESSAGE") if isinstance(error, dict) else payload
        raise RuntimeError(f"Seoul Open Data response error {code or ''}: {message}")
    rows = body.get("row") or []
    if isinstance(rows, dict):
        rows = [rows]
    total_count = int(body.get("list_total_count") or len(rows))
    return [row for row in rows if isinstance(row, dict)], total_count


def _fetch_service_page(source: SeoulOpenDataSource, start: int, end: int, tail: str = "") -> tuple[list[dict[str, Any]], int]:
    url = _seoul_url_with_tail(source.service, start, end, tail) if tail else _seoul_url(source.service, start, end)
    response = requests.get(url, timeout=settings.public_data_timeout_seconds)
    response.raise_for_status()
    return _extract_rows(response.json(), source.service)


def _fetch_standard_items(source: SeoulOpenDataSource) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    rows_per_page = max(1, min(1000, int(settings.seoul_open_data_rows_per_page)))
    max_pages = max(1, int(settings.seoul_open_data_max_pages))
    for page in range(max_pages):
        start = page * rows_per_page + 1
        end = start + rows_per_page - 1
        rows, total_count = _fetch_service_page(source, start, end)
        items.extend(rows)
        if not rows or len(items) >= total_count or len(rows) < rows_per_page:
            break
    return items


def _fetch_sewer_level_items(source: SeoulOpenDataSource) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    end_hour = datetime.now()
    start_hour = end_hour - timedelta(hours=1)
    time_tail = f"{start_hour:%Y%m%d%H}/{end_hour:%Y%m%d%H}"
    rows_per_page = max(1, min(1000, int(settings.seoul_open_data_rows_per_page)))
    max_pages = max(1, int(settings.seoul_open_data_max_pages))
    for code in range(1, 26):
        code_text = f"{code:02d}"
        fetched_for_code = 0
        for page in range(max_pages):
            start = page * rows_per_page + 1
            end = start + rows_per_page - 1
            rows, total_count = _fetch_service_page(source, start, end, f"{code_text}/{time_tail}")
            items.extend(rows)
            fetched_for_code += len(rows)
            if not rows or fetched_for_code >= total_count or len(rows) < rows_per_page:
                break
    return items


def _fetch_items(source: SeoulOpenDataSource) -> list[dict[str, Any]]:
    if source.normalizer == "sewer_level":
        return _fetch_sewer_level_items(source)
    return _fetch_standard_items(source)


def _insert_groundwater(
    conn: sqlite3.Connection,
    source: SeoulOpenDataSource,
    item: dict[str, Any],
    regions: list[dict[str, Any]],
) -> bool:
    region = _region_for_item(item, regions)
    if not region:
        return False
    region_id = int(region["region_id"])
    station_id = _text(item, ("obsv_cd", "obsrvt_cd", "station_id", "관측소코드", "관측망번호", "코드"))
    station_name = _text(item, ("OBSVTR_NM", "obsv_nm", "obsrvt_nm", "station_name", "관측소명", "측정소명", "관측망명"))
    observed_at = _date_text(_ci_get(item, ("OBSRVN_YMD", "ymd", "msr_dt", "obsr_de", "observed_at", "관측일자", "측정일자", "일자")))
    level = _float(item, ("UDGD_WATL", "groundwater_level", "water_level", "gwl", "수위", "지하수위"))
    temperature = _float(item, ("WATT", "water_temperature", "temp", "수온"))
    conductivity = _float(item, ("ELCD", "electrical_conductivity", "ec", "전기전도도"))
    if level is None:
        return False
    record_id = _source_record_id(source, item, station_id or station_name, observed_at)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO seoul_groundwater_observations(
            region_id, station_id, station_name, observed_at, groundwater_level,
            water_temperature, electrical_conductivity, source_name, source_record_id, raw_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            station_id or None,
            station_name or None,
            observed_at,
            level,
            temperature,
            conductivity,
            source.name,
            record_id,
            _stable_json(item),
        ),
    )
    if not cur.rowcount:
        return False

    previous = query_one(
        conn,
        """
        SELECT groundwater_level
        FROM groundwater_data
        WHERE region_id = ?
          AND source_name = ?
          AND station_id = ?
        ORDER BY record_date DESC, id DESC
        LIMIT 1
        """,
        (region_id, source.name, station_id or station_name),
    )
    previous_level = previous.get("groundwater_level") if previous else None
    variation = abs(float(level) - float(previous_level)) if previous_level is not None else 0.0
    conn.execute(
        """
        INSERT INTO groundwater_data(
            region_id, record_date, groundwater_level, variation,
            source_name, source_record_id, station_id, station_name
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (region_id, _record_date(observed_at), level, variation, source.name, record_id, station_id, station_name),
    )
    return True


def _insert_rainfall(
    conn: sqlite3.Connection,
    source: SeoulOpenDataSource,
    item: dict[str, Any],
    regions: list[dict[str, Any]],
) -> bool:
    region = _region_for_item(item, regions)
    if not region:
        return False
    region_id = int(region["region_id"])
    station_id = _text(item, ("RF_CD", "GU_CD", "raingauge_code", "gauge_code", "code", "강우량계코드", "구청코드"))
    station_name = _text(item, ("RF_NM", "GU_NM", "raingauge_name", "gauge_name", "station_name", "강우량계명", "측정계명"))
    observed_at = _date_text(_ci_get(item, ("DATA_CLCT_TM", "receive_time", "data_time", "msr_dt", "자료수집시각", "수집시각", "일자")))
    rainfall = _float(item, ("RN_10M", "rainfall10", "rainfall", "hour_rainfall", "시우량", "10분누적강우량", "강우량"))
    if rainfall is None:
        rainfall = _float(item, ("일일누계", "day_rainfall", "daily_rainfall"))
    if rainfall is None:
        return False
    record_id = _source_record_id(source, item, station_id or station_name, observed_at)
    existing = query_one(
        conn,
        """
        SELECT id
        FROM weather_data
        WHERE region_id = ? AND source_name = ? AND source_record_id = ?
        LIMIT 1
        """,
        (region_id, source.name, record_id),
    )
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO weather_data(
            region_id, record_date, rainfall, temperature, humidity,
            source_name, source_record_id, station_id, station_name
        )
        VALUES(?, ?, ?, NULL, NULL, ?, ?, ?, ?)
        """,
        (region_id, _record_date(observed_at), rainfall, source.name, record_id, station_id, station_name),
    )
    return True


def _insert_sewer_level(
    conn: sqlite3.Connection,
    source: SeoulOpenDataSource,
    item: dict[str, Any],
    regions: list[dict[str, Any]],
) -> bool:
    region = _region_for_item(item, regions)
    if not region:
        return False
    region_id = int(region["region_id"])
    station_id = _text(item, ("UNQ_NO", "SE_CD", "id", "mntr_id", "code", "고유번호", "구분코드"))
    station_name = _text(item, ("SE_NM", "name", "mntr_nm", "구분명", "수위계명"))
    observed_at = _date_text(_ci_get(item, ("MSRMT_YMD", "msr_dt", "measure_date", "측정일자", "수집시각")))
    level = _float(item, ("MSRMT_WATL", "level", "water_level", "측정수위", "수위"))
    status = _text(item, ("SGN_STTS", "status", "communication_status", "통신상태"))
    if level is None:
        return False
    record_id = _source_record_id(source, item, station_id or station_name, observed_at)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO seoul_sewer_levels(
            region_id, station_id, station_name, observed_at, sewer_level,
            communication_status, source_name, source_record_id, raw_json
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            station_id or None,
            station_name or None,
            observed_at,
            level,
            status or None,
            source.name,
            record_id,
            _stable_json(item),
        ),
    )
    if cur.rowcount:
        row = query_one(
            conn,
            """
            SELECT COALESCE(MAX(building_density), 0) AS bd,
                   COALESCE(MAX(road_density), 0) AS rd
            FROM environment_features
            WHERE region_id = ?
            """,
            (region_id,),
        ) or {"bd": 0, "rd": 0}
        drainage_penalty = min(1.0, max(0.0, float(level) / 5.0))
        conn.execute(
            """
            INSERT INTO environment_features(region_id, building_density, road_density, land_use_type)
            VALUES(?, ?, ?, ?)
            """,
            (region_id, float(row["bd"]), max(float(row["rd"]), drainage_penalty), "seoul_sewer_level"),
        )
        return True
    return False


def _insert_road_excavation(
    conn: sqlite3.Connection,
    source: SeoulOpenDataSource,
    item: dict[str, Any],
    regions: list[dict[str, Any]],
) -> bool:
    region = _region_for_item(item, regions)
    if not region:
        return False
    region_id = int(region["region_id"])
    start_raw = _ci_get(item, ("CNWPD_DT", "start_date", "st_dt", "착공일", "시작일", "공사시작일"))
    start_date = _record_date(_date_text(str(start_raw or "").split("~", 1)[0].strip()))
    construction_type = _text(item, ("CNW_NM", "construction_type", "work_type", "공사종류", "공사명", "공사내용"), "Seoul road excavation")
    length_m = _float(item, ("length", "굴착연장", "연장"))
    depth_m = _float(item, ("depth", "굴착깊이", "깊이"))
    scale_score = 6.0 + min(8.0, (length_m or 0.0) / 100.0) + min(6.0, (depth_m or 0.0) * 1.5)
    record_id = _source_record_id(
        source,
        item,
        _text(item, ("PRMISN_REQ_NO", "PRMISN_NO", "id", "허가번호", "관리번호", "공사번호")),
        start_date,
        construction_type,
    )
    existing = query_one(
        conn,
        """
        SELECT id
        FROM construction_events
        WHERE region_id = ? AND source_name = ? AND source_record_id = ?
        LIMIT 1
        """,
        (region_id, source.name, record_id),
    )
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO construction_events(
            region_id, construction_type, start_date, scale_score,
            source_name, source_record_id, address, latitude, longitude
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, NULL, NULL)
        """,
        (
            region_id,
            construction_type[:200],
            start_date,
            min(20.0, scale_score),
            source.name,
            record_id,
            _text(item, ("PSTN_INFO", "ATDRC_ID", "ADSTRD_CD", "address", "공사위치", "도로명주소", "위치"))[:300],
        ),
    )
    return True


def _normalize_items(
    conn: sqlite3.Connection,
    source: SeoulOpenDataSource,
    items: list[dict[str, Any]],
    regions: list[dict[str, Any]],
) -> int:
    count = 0
    for item in items:
        if source.normalizer == "groundwater":
            changed = _insert_groundwater(conn, source, item, regions)
        elif source.normalizer == "rainfall":
            changed = _insert_rainfall(conn, source, item, regions)
        elif source.normalizer == "sewer_level":
            changed = _insert_sewer_level(conn, source, item, regions)
        elif source.normalizer == "road_excavation":
            changed = _insert_road_excavation(conn, source, item, regions)
        else:
            changed = False
        if changed:
            count += 1
    return count


def collect_seoul_open_data_once(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    if not settings.seoul_open_data_enabled:
        return {"enabled": False, "key_loaded": bool(settings.seoul_open_data_api_key), "sources": []}
    if not settings.seoul_open_data_api_key:
        return {
            "enabled": True,
            "key_loaded": False,
            "error": "SEOUL_OPEN_DATA_API_KEY is not set",
            "sources": [],
        }

    owns_conn = conn is None
    if conn is None:
        from app.config.settings import settings as app_settings
        from app.db.core import connect

        conn = connect(app_settings.db_path)

    try:
        _ensure_tables(conn)
        regions = _load_regions(conn)
        results: list[dict[str, Any]] = []
        for source in _sources():
            try:
                items = _fetch_items(source)
                normalized_count = _normalize_items(conn, source, items, regions)
                results.append(
                    {
                        "source": source.name,
                        "label": source.label,
                        "service": source.service,
                        "success": True,
                        "fetched_count": len(items),
                        "normalized_count": normalized_count,
                    }
                )
                conn.commit()
            except Exception as exc:
                results.append(
                    {
                        "source": source.name,
                        "label": source.label,
                        "service": source.service,
                        "success": False,
                        "fetched_count": 0,
                        "normalized_count": 0,
                        "error": _redact(exc),
                    }
                )
        return {
            "enabled": True,
            "key_loaded": True,
            "base_url": settings.seoul_open_data_base_url,
            "sources": results,
        }
    finally:
        if owns_conn and conn is not None:
            conn.close()
