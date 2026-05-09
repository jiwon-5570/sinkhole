from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import logging
import math
import re
import sqlite3
import threading
from typing import Any
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import requests

from app.config.settings import settings
from app.db.core import connect, query_all, query_one
from app.services.features import today_str


LOGGER = logging.getLogger(__name__)
SOURCE_BUNDLE = "approved_public_data_bundle"
_RUN_LOCK = threading.Lock()
_WORKING_API_VARIANTS: dict[str, tuple[str, str]] = {}
_COORD_TRANSFORMERS: dict[str, Any] = {}


@dataclass(frozen=True)
class PublicDataSource:
    name: str
    label: str
    url: str
    scope: str
    normalizer: str
    address_param: str | None = None
    max_rows_per_page: int = 100


APPROVED_SOURCES = (
    PublicDataSource(
        name="kalis_public_facility_safety",
        label="KALIS public facility safety management",
        url=settings.kalis_public_facility_safety_url,
        scope="region",
        normalizer="facility",
        address_param="facilAddr",
        max_rows_per_page=20,
    ),
    PublicDataSource(
        name="kalis_public_facility_diagnosis",
        label="KALIS public facility inspection diagnosis",
        url=settings.kalis_public_facility_diagnosis_url,
        scope="region",
        normalizer="facility",
        address_param="facilAddr",
        max_rows_per_page=100,
    ),
    PublicDataSource(
        name="molit_underground_safety",
        label="MOLIT underground safety information",
        url=settings.underground_safety_info_url,
        scope="global",
        normalizer="underground",
        max_rows_per_page=100,
    ),
    PublicDataSource(
        name="ground_subsidence_accident",
        label="MOLIT ground subsidence accident history",
        url=settings.ground_subsidence_accident_url,
        scope="global",
        normalizer="accident",
        max_rows_per_page=1000,
    ),
    PublicDataSource(
        name="kma_asos_hourly_rainfall",
        label="KMA ASOS hourly weather",
        url=settings.kma_asos_hourly_url,
        scope="global",
        normalizer="weather",
        max_rows_per_page=999,
    ),
    PublicDataSource(
        name="building_permit_construction",
        label="MOLIT building permit construction",
        url=settings.building_permit_url,
        scope="region",
        normalizer="construction_permit",
        max_rows_per_page=100,
    ),
    *(
        (
            PublicDataSource(
                name="molit_ground_boreholes",
                label="MOLIT ground information boreholes",
                url=settings.molit_borehole_api_url,
                scope="global",
                normalizer="borehole",
                max_rows_per_page=1000,
            ),
        )
        if settings.molit_borehole_api_enabled
        else ()
    ),
)

_STATE: dict[str, Any] = {
    "enabled": settings.public_data_auto_collect,
    "running": False,
    "key_loaded": bool(settings.public_data_api_key),
    "last_started_at": None,
    "last_finished_at": None,
    "last_success": None,
    "last_error": None,
    "last_fetched_count": 0,
    "last_saved_count": 0,
    "last_normalized_count": 0,
    "sources": [],
}

_SINKHOLE_TERMS = (
    "\uc9c0\ubc18\uce68\ud558",
    "\uc2f1\ud06c\ud640",
    "\ub3d9\uacf5",
    "\uacf5\ub3d9",
    "\ud568\ubab0",
    "\uce68\ud558",
)
_FACILITY_RISK_TERMS = (
    "\uade0\uc5f4",
    "\ub204\uc218",
    "\ud30c\uc190",
    "\ubd80\uc2dd",
    "\ubcf4\uc218",
    "\ubcf4\uac15",
    "\uc704\ud5d8",
    "\ubbf8\ud761",
    "\uacb0\ud568",
)

_BUILDING_PERMIT_TARGETS: dict[int, tuple[str, str]] = {
    101: ("48170", "13100"),  # Jinju-si Gajwa-dong
    102: ("48170", "13100"),  # Jinju Station area
    103: ("48170", "13700"),  # Jinju Innovation City, Chungmugong-dong
    104: ("48170", "12900"),  # Jinyangho entrance, Panmun-dong
    105: ("48240", "25000"),  # Sacheon Airport area, Sacheon-eup
}

_REGION_DONG_HINTS: dict[int, tuple[str, ...]] = {
    101: ("가좌동",),
    102: ("가좌동", "호탄동"),
    103: ("충무공동",),
    104: ("판문동", "평거동"),
    105: ("사천읍",),
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _state_copy() -> dict[str, Any]:
    data = dict(_STATE)
    data.update(
        {
            "interval_seconds": settings.public_data_interval_seconds,
            "rows_per_page": settings.public_data_rows_per_page,
            "max_pages": settings.public_data_max_pages,
            "source_names": [source.name for source in APPROVED_SOURCES],
            "source_urls": {source.name: source.url for source in APPROVED_SOURCES},
        }
    )
    return data


def _api_key_for_request(api_key: str) -> str:
    return unquote(api_key.strip())


def _redact_message(value: Any) -> str:
    text = str(value)
    api_key = settings.public_data_api_key
    if api_key:
        for secret in {api_key, _api_key_for_request(api_key)}:
            if secret:
                text = text.replace(secret, "[PUBLIC_DATA_API_KEY]")
    text = re.sub(r"([?&]ServiceKey=)[^&\s)]+", r"\1[REDACTED]", text)
    text = re.sub(r"([?&]serviceKey=)[^&\s)]+", r"\1[REDACTED]", text)
    return text


def _is_network_wide_error(message: str) -> bool:
    markers = (
        "Failed to establish a new connection",
        "NameResolutionError",
        "WinError 10013",
        "Connection refused",
    )
    return any(marker in message for marker in markers)


def get_public_data_status() -> dict[str, Any]:
    return _state_copy()


def _ensure_collector_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS raw_source_records (
            id INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_url TEXT,
            source_record_id TEXT,
            fetched_at TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            normalized INTEGER DEFAULT 0,
            error_message TEXT,
            UNIQUE(source_name, payload_hash)
        );

        CREATE TABLE IF NOT EXISTS public_data_collection_runs (
            id INTEGER PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            success INTEGER DEFAULT 0,
            source_name TEXT,
            fetched_count INTEGER DEFAULT 0,
            saved_count INTEGER DEFAULT 0,
            normalized_count INTEGER DEFAULT 0,
            error_message TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_raw_source_records_source
            ON raw_source_records(source_name, fetched_at);
        CREATE INDEX IF NOT EXISTS idx_public_data_collection_runs_started
            ON public_data_collection_runs(started_at);
        """
    )
    _ensure_normalized_table_columns(conn)


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _ensure_normalized_table_columns(conn: sqlite3.Connection) -> None:
    common_columns = {
        "source_name": "TEXT",
        "source_record_id": "TEXT",
        "address": "TEXT",
        "latitude": "REAL",
        "longitude": "REAL",
    }
    for table_name in ("facility_inspection", "facility_status", "underground_safety"):
        for column_name, column_type in common_columns.items():
            _ensure_column(conn, table_name, column_name, column_type)

    _ensure_column(conn, "facility_inspection", "facility_name", "TEXT")
    _ensure_column(conn, "facility_status", "facility_name", "TEXT")
    _ensure_column(conn, "underground_safety", "project_name", "TEXT")
    _ensure_column(conn, "underground_safety", "max_dig_depth", "REAL")
    _ensure_column(conn, "underground_safety", "risk_score", "REAL")

    for table_name in ("sinkhole_history", "construction_events", "groundwater_data"):
        _ensure_column(conn, table_name, "source_name", "TEXT")
        _ensure_column(conn, table_name, "source_record_id", "TEXT")
    for table_name in ("sinkhole_history", "construction_events"):
        _ensure_column(conn, table_name, "address", "TEXT")
        _ensure_column(conn, table_name, "latitude", "REAL")
        _ensure_column(conn, table_name, "longitude", "REAL")
    _ensure_column(conn, "weather_data", "source_name", "TEXT")
    _ensure_column(conn, "weather_data", "source_record_id", "TEXT")
    _ensure_column(conn, "weather_data", "station_id", "TEXT")
    _ensure_column(conn, "weather_data", "station_name", "TEXT")
    for column_name, column_type in {
        "raw_x": "REAL",
        "raw_y": "REAL",
        "coordinate_crs": "TEXT",
        "groundwater_level_m": "REAL",
        "borehole_method": "TEXT",
        "borehole_type": "TEXT",
        "source_record_id": "TEXT",
    }.items():
        _ensure_column(conn, "molit_ground_boreholes", column_name, column_type)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_element_to_value(element: ET.Element) -> Any:
    children = list(element)
    if not children:
        return (element.text or "").strip()

    grouped: dict[str, Any] = {}
    for child in children:
        key = _strip_namespace(child.tag)
        value = _xml_element_to_value(child)
        if key in grouped:
            if not isinstance(grouped[key], list):
                grouped[key] = [grouped[key]]
            grouped[key].append(value)
        else:
            grouped[key] = value
    return grouped


def _parse_response_payload(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except ValueError:
        pass

    text = response.text.strip()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        preview = text.replace("\n", " ")[:180]
        raise RuntimeError(f"public data API returned non-JSON/XML response: {preview}") from exc
    return {_strip_namespace(root.tag): _xml_element_to_value(root)}


def _ci_get(data: Any, key: str, default: Any = None) -> Any:
    if not isinstance(data, dict):
        return default
    key_lower = key.lower()
    for item_key, value in data.items():
        if str(item_key).lower() == key_lower:
            return value
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = _ci_get(payload, "data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    response = _ci_get(payload, "response", payload)
    body = _ci_get(response, "body", response)
    items = _ci_get(body, "items")
    if items is None:
        items = _ci_get(body, "Items")
    if isinstance(items, dict):
        items = _ci_get(items, "item", items)
    if items is None:
        items = _ci_get(body, "item")
    return [item for item in _as_list(items) if isinstance(item, dict)]


def _response_total_count(payload: dict[str, Any]) -> int:
    try:
        value = _ci_get(payload, "totalCount")
        if value is not None:
            return int(value or 0)
    except (TypeError, ValueError):
        pass

    response = _ci_get(payload, "response", payload)
    body = _ci_get(response, "body", response)
    try:
        return int(_ci_get(body, "totalCount", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _raise_on_api_error(payload: dict[str, Any], source: PublicDataSource) -> None:
    response = _ci_get(payload, "response", payload)
    header = _ci_get(response, "header", {})
    result_code = str(_ci_get(header, "resultCode", "") or "").strip()
    result_msg = str(_ci_get(header, "resultMsg", "") or "").strip()
    if result_code and result_code not in {"00", "0", "03", "3"}:
        message = result_msg or "public data API error"
        raise RuntimeError(f"{source.name} returned {result_code}: {message}")


def _candidate_urls(url: str) -> list[str]:
    urls = [url]
    if url.startswith("http://"):
        urls.append("https://" + url[len("http://") :])
    elif url.startswith("https://"):
        urls.append("http://" + url[len("https://") :])
    return list(dict.fromkeys(urls))


def _date_range_params() -> dict[str, str]:
    end = datetime.now()
    start = end - timedelta(days=365)
    return {
        "sysRegDateFrom": start.strftime("%Y%m%d"),
        "sysRegDateTo": end.strftime("%Y%m%d"),
    }


def _csv_values(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _source_rows(source: PublicDataSource) -> int:
    if source.name == "molit_ground_boreholes":
        return min(max(1, int(settings.molit_borehole_rows_per_page)), source.max_rows_per_page)
    if source.name == "ground_subsidence_accident":
        return source.max_rows_per_page
    if source.name == "kma_asos_hourly_rainfall":
        return source.max_rows_per_page
    return min(max(1, int(settings.public_data_rows_per_page)), source.max_rows_per_page)


def _lookback_date_params(days: int, from_key: str, to_key: str, end_offset_days: int = 0) -> dict[str, str]:
    end = datetime.now() - timedelta(days=max(0, end_offset_days))
    start = end - timedelta(days=max(1, int(days)))
    return {
        from_key: start.strftime("%Y%m%d"),
        to_key: end.strftime("%Y%m%d"),
    }


def _weather_params(source: PublicDataSource, page_no: int) -> dict[str, Any]:
    params = {
        "numOfRows": _source_rows(source),
        "pageNo": page_no,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "HR",
        "startHh": "00",
        "endHh": "23",
        "stnIds": settings.kma_asos_station_ids,
    }
    params.update(
        _lookback_date_params(
            settings.public_data_weather_lookback_days,
            "startDt",
            "endDt",
            end_offset_days=1,
        )
    )
    return params


def _source_params(source: PublicDataSource, page_no: int, region: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = _source_rows(source)
    if source.name == "kma_asos_hourly_rainfall":
        return _weather_params(source, page_no)
    if source.name == "molit_ground_boreholes":
        return {
            "page": page_no,
            "perPage": _source_rows(source),
            "returnType": "JSON",
        }

    params: dict[str, Any] = {
        "numOfRows": rows,
        "pageNo": page_no,
        "type": "json",
    }
    if source.name == "building_permit_construction":
        params.pop("type", None)
        params["_type"] = "json"
        if region:
            params["sigunguCd"] = region.get("sigungu_cd")
            params["bjdongCd"] = region.get("bjdong_cd")
        return params
    if source.name == "ground_subsidence_accident":
        params.update(
            _lookback_date_params(
                settings.public_data_accident_lookback_days,
                "sagoDateFrom",
                "sagoDateTo",
            )
        )
        return params
    if source.scope == "global":
        params.update(_date_range_params())
    if source.address_param and region:
        query = str(region.get("sigungu") or region.get("region_name") or "").strip()
        if query:
            params[source.address_param] = query
    return params


def _source_max_pages(source: PublicDataSource) -> int:
    if source.name == "molit_ground_boreholes":
        return max(1, int(settings.molit_borehole_max_pages))
    return max(1, int(settings.public_data_max_pages))


def _fetch_page(
    source: PublicDataSource,
    api_key: str,
    page_no: int,
    region: dict[str, Any] | None = None,
) -> dict[str, Any]:
    variants: list[tuple[str, str]] = []
    if source.name in _WORKING_API_VARIANTS:
        variants.append(_WORKING_API_VARIANTS[source.name])
    for url in _candidate_urls(source.url):
        key_names = ("serviceKey", "ServiceKey") if source.name == "molit_ground_boreholes" else ("ServiceKey", "serviceKey")
        for key_name in key_names:
            variant = (url, key_name)
            if variant not in variants:
                variants.append(variant)

    last_error: Exception | None = None
    for url, key_name in variants:
        params = _source_params(source, page_no, region)
        params[key_name] = _api_key_for_request(api_key)
        try:
            response = requests.get(url, params=params, timeout=settings.public_data_timeout_seconds)
            response.raise_for_status()
            payload = _parse_response_payload(response)
            _raise_on_api_error(payload, source)
            _WORKING_API_VARIANTS[source.name] = (url, key_name)
            return payload
        except Exception as exc:
            last_error = exc

    raise RuntimeError(_redact_message(last_error or f"{source.name} request failed"))


def _fetch_source_items(
    source: PublicDataSource,
    api_key: str,
    region: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    max_pages = _source_max_pages(source)
    rows_per_page = _source_rows(source)
    for page_no in range(1, max_pages + 1):
        payload = _fetch_page(source, api_key, page_no, region)
        page_items = _extract_items(payload)
        items.extend(page_items)
        total_count = _response_total_count(payload)
        if not page_items or len(items) >= total_count or len(page_items) < rows_per_page:
            break
    return items


def _source_operation_url(source: PublicDataSource, operation_name: str) -> str:
    base = source.url.rsplit("/", 1)[0]
    return f"{base}/{operation_name}"


def _fetch_operation_items(
    source: PublicDataSource,
    api_key: str,
    operation_name: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    variants: list[tuple[str, str]] = []
    for url in _candidate_urls(_source_operation_url(source, operation_name)):
        for key_name in ("ServiceKey", "serviceKey"):
            variants.append((url, key_name))

    last_error: Exception | None = None
    for url, key_name in variants:
        request_params = dict(params)
        request_params[key_name] = _api_key_for_request(api_key)
        try:
            response = requests.get(url, params=request_params, timeout=settings.public_data_timeout_seconds)
            response.raise_for_status()
            payload = _parse_response_payload(response)
            _raise_on_api_error(payload, source)
            return _extract_items(payload)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(_redact_message(last_error or f"{source.name} detail request failed"))


def _region_sigungus(regions: list[dict[str, Any]]) -> set[str]:
    return {str(region.get("sigungu") or "").strip() for region in regions if region.get("sigungu")}


def _postprocess_source_items(
    source: PublicDataSource,
    api_key: str,
    items: list[dict[str, Any]],
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if source.name != "ground_subsidence_accident":
        return items

    target_sigungus = _region_sigungus(regions)
    enriched: list[dict[str, Any]] = []
    for item in items:
        sigungu = _first_text(item, ("sigungu", "siGunGu"), "")
        if sigungu and sigungu not in target_sigungus:
            continue
        sago_no = _first_text(item, ("sagoNo", "sogoNo"), "")
        if not sago_no:
            continue
        try:
            detail_items = _fetch_operation_items(
                source,
                api_key,
                "getSubsidenceInfo01",
                {
                    "sagoNo": sago_no,
                    "numOfRows": 1,
                    "pageNo": 1,
                    "type": "json",
                },
            )
        except Exception as exc:
            LOGGER.warning("failed to fetch subsidence accident detail %s: %s", sago_no, _redact_message(exc))
            detail_items = []
        enriched.append({**item, **(detail_items[0] if detail_items else {})})
    return enriched


def _item_text(item: dict[str, Any]) -> str:
    return " ".join(str(value) for value in item.values() if value is not None)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _first_text(item: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = _ci_get(item, key)
        if value not in (None, ""):
            return str(value).strip()
    return default


def _item_record_id(item: dict[str, Any]) -> str | None:
    parts = [
        _first_text(item, ("no", "No", "시추공코드"), ""),
        _first_text(item, ("facilNo", "arNo", "evalNo", "accdntNo", "sagoNo", "sogoNo", "mgmPmsrgstPk"), ""),
        _first_text(item, ("chckDignSeq", "facilNm", "evalNm", "accdntNm", "accdntYmd", "tm", "archPmsDay"), ""),
    ]
    value = ":".join(part for part in parts if part)
    return value or None


def _item_address(item: dict[str, Any]) -> str:
    return _first_text(item, ("facilAddr", "addr", "address", "roadAddr", "jibunAddr", "platPlc"), "")


def _item_name(item: dict[str, Any]) -> str:
    return _first_text(item, ("facilNm", "evalNm", "projectNm", "bizNm", "accdntNm", "bldNm", "stnNm"), "")


def _item_lat_lon(item: dict[str, Any]) -> tuple[float, float] | None:
    x = _optional_float(_first_text(item, ("gisX", "lon", "lng", "longitude", "x", "sagoLon"), ""))
    y = _optional_float(_first_text(item, ("gisY", "lat", "latitude", "y", "sagoLat"), ""))
    if x is None or y is None:
        return None
    if abs(x) < 0.000001 and abs(y) < 0.000001:
        return None

    if -90.0 <= y <= 90.0 and -180.0 <= x <= 180.0:
        return y, x
    if -90.0 <= x <= 90.0 and -180.0 <= y <= 180.0:
        return x, y
    return None


def _korea_wgs84(lat: float, lon: float) -> bool:
    return 32.0 <= lat <= 39.8 and 124.0 <= lon <= 132.5


def _projected_xy_to_wgs84(raw_x: float | None, raw_y: float | None) -> tuple[float | None, float | None, str | None]:
    if raw_x is None or raw_y is None:
        return None, None, None

    if _korea_wgs84(raw_y, raw_x):
        return raw_y, raw_x, "EPSG:4326"
    if _korea_wgs84(raw_x, raw_y):
        return raw_x, raw_y, "EPSG:4326"

    try:
        from pyproj import Transformer
    except ImportError:
        return None, None, settings.molit_borehole_coord_crs

    candidates = [
        settings.molit_borehole_coord_crs,
        "EPSG:5181",
        "EPSG:5186",
        "EPSG:5187",
        "EPSG:5185",
        "EPSG:5179",
    ]
    for crs in dict.fromkeys(candidate for candidate in candidates if candidate):
        try:
            transformer = _COORD_TRANSFORMERS.get(crs)
            if transformer is None:
                transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
                _COORD_TRANSFORMERS[crs] = transformer

            lon, lat = transformer.transform(raw_x, raw_y)
            if _korea_wgs84(float(lat), float(lon)):
                return float(lat), float(lon), crs

            lon, lat = transformer.transform(raw_y, raw_x)
            if _korea_wgs84(float(lat), float(lon)):
                return float(lat), float(lon), f"{crs}:swapped"
        except Exception:
            continue
    return None, None, settings.molit_borehole_coord_crs


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _query_targets(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[tuple[str, str], dict[str, Any]] = {}
    for region in regions:
        key = (str(region.get("sido") or ""), str(region.get("sigungu") or ""))
        if key not in targets:
            targets[key] = {
                "sido": region.get("sido"),
                "sigungu": region.get("sigungu"),
                "region_name": region.get("sigungu") or region.get("region_name"),
            }
    return list(targets.values())


def _building_permit_target(region: dict[str, Any]) -> dict[str, Any] | None:
    region_id = int(region["region_id"])
    codes = _BUILDING_PERMIT_TARGETS.get(region_id)
    if not codes:
        return None
    sigungu_cd, bjdong_cd = codes
    return {
        "region_id": region_id,
        "sido": region.get("sido"),
        "sigungu": region.get("sigungu"),
        "region_name": region.get("region_name"),
        "sigungu_cd": sigungu_cd,
        "bjdong_cd": bjdong_cd,
    }


def _source_targets(source: PublicDataSource, regions: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    if source.name == "building_permit_construction":
        return [target for region in regions if (target := _building_permit_target(region))]
    if source.scope == "region":
        return _query_targets(regions)
    return [None]


def _item_context(item: dict[str, Any]) -> dict[str, Any]:
    context = item.get("_collector_context")
    return context if isinstance(context, dict) else {}


def _resolve_item_region(item: dict[str, Any], regions: list[dict[str, Any]]) -> dict[str, Any] | None:
    coords = _item_lat_lon(item)
    if not coords:
        return None

    lat, lon = coords
    address = _item_address(item)
    if address:
        candidates = [region for region in regions if region.get("sigungu") and str(region["sigungu"]) in address]
    else:
        candidates = list(regions)
    if not candidates:
        candidates = list(regions)

    nearest = min(
        candidates,
        key=lambda region: _distance_m(lat, lon, float(region["latitude"]), float(region["longitude"])),
    )
    distance = _distance_m(lat, lon, float(nearest["latitude"]), float(nearest["longitude"]))
    if distance <= float(settings.public_data_match_radius_m):
        return nearest
    return None


def _resolve_region_by_dong_hint(item: dict[str, Any], regions: list[dict[str, Any]]) -> dict[str, Any] | None:
    sigungu = _first_text(item, ("sigungu", "siGunGu"), "")
    text = " ".join(
        part
        for part in (
            _first_text(item, ("dong",), ""),
            _item_address(item),
            _item_text(item),
        )
        if part
    )
    for region in regions:
        if sigungu and str(region.get("sigungu") or "") != sigungu:
            continue
        hints = _REGION_DONG_HINTS.get(int(region["region_id"]), ())
        if any(hint and hint in text for hint in hints):
            return region
    return None


def _parse_public_date(value: Any) -> str:
    text = str(value or "").strip().replace(".", "-").replace("/", "-")
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) == 6:
        return f"{digits[:4]}-{digits[4:6]}-01"
    if len(digits) == 4:
        return f"{digits}-01-01"
    if len(text) >= 10:
        return text[:10]
    return today_str()


def _facility_date(item: dict[str, Any]) -> str:
    return _parse_public_date(
        _first_text(
            item,
            (
                "chckDignYmd",
                "lastChckDignYmd",
                "astChckDignYmd",
                "nextPcchkArrvlYmd",
                "cplYmd",
            ),
            "",
        )
    )


def _construction_age(item: dict[str, Any]) -> int:
    cpl_ymd = _first_text(item, ("cplYmd",), "")
    digits = "".join(ch for ch in cpl_ymd if ch.isdigit())
    if len(digits) < 4:
        return 0
    year = _safe_int(digits[:4])
    if year <= 0:
        return 0
    return max(0, datetime.now().year - year)


def _grade_risk_score(grade: str) -> float:
    text = grade.upper()
    if "E" in text or "\ubd88\ub7c9" in grade:
        return 95.0
    if "D" in text or "\uc704\ud5d8" in grade or "\ubbf8\ud761" in grade:
        return 82.0
    if "C" in text or "\ubcf4\ud1b5" in grade:
        return 60.0
    if "B" in text or "\uc591\ud638" in grade:
        return 35.0
    if "A" in text or "\uc6b0\uc218" in grade:
        return 18.0
    return 35.0


def _facility_risk_score(item: dict[str, Any]) -> float:
    grade = _first_text(item, ("sfGrade", "safetyGrade", "grade"), "")
    score = _grade_risk_score(grade)
    age = _construction_age(item)
    if age >= 50:
        score += 20.0
    elif age >= 30:
        score += 12.0
    elif age >= 20:
        score += 6.0
    if _contains_any(_item_text(item), _FACILITY_RISK_TERMS + _SINKHOLE_TERMS):
        score += 12.0
    return round(max(0.0, min(score, 100.0)), 1)


def _diagnosis_result(score: float) -> str:
    if score >= 75:
        return "danger"
    if score >= 55:
        return "attention"
    return "safe"


def _damage_scale(item: dict[str, Any]) -> float:
    score = _facility_risk_score(item)
    return round(max(1.0, min(score / 10.0, 10.0)), 2)


def _accident_damage_scale(item: dict[str, Any]) -> float:
    deaths = _safe_int(_ci_get(item, "deathCnt"), 0)
    wounds = _safe_int(_ci_get(item, "woundCnt"), 0)
    property_damage = _safe_float(_ci_get(item, "prptyDamageAmt"), 0.0)
    scale = 1.0 + deaths * 3.0 + wounds * 0.6 + min(property_damage / 1000.0, 4.0)
    width = _safe_float(_ci_get(item, "sinkWidth"), 0.0)
    extend = _safe_float(_ci_get(item, "sinkExtend"), 0.0)
    depth = _safe_float(_ci_get(item, "sinkDepth"), 0.0)
    if width or extend or depth:
        scale += min((max(width, 1.0) * max(extend, 1.0) * max(depth, 0.5)) / 20.0, 6.0)
    return round(max(1.0, min(scale, 10.0)), 2)


def _save_raw_records(
    conn: sqlite3.Connection,
    source: PublicDataSource,
    items: list[dict[str, Any]],
    fetched_at: str,
    context: dict[str, Any] | None = None,
) -> list[tuple[dict[str, Any], str]]:
    saved: list[tuple[dict[str, Any], str]] = []
    for item in items:
        payload = {"context": context or {}, "item": item}
        digest = _payload_hash(payload)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO raw_source_records(
                source_name, source_url, source_record_id, fetched_at, payload_hash, payload_json, normalized
            )
            VALUES(?, ?, ?, ?, ?, ?, 0)
            """,
            (
                source.name,
                source.url,
                _item_record_id(item),
                fetched_at,
                digest,
                _stable_json(payload),
            ),
        )
        if cur.rowcount:
            item_with_context = dict(item)
            item_with_context["_collector_context"] = context or {}
            saved.append((item_with_context, digest))
    return saved


def _insert_facility_inspection(conn: sqlite3.Connection, region_id: int, item: dict[str, Any], source_name: str) -> bool:
    score = _facility_risk_score(item)
    inspection_date = _facility_date(item)
    facility_type = _first_text(item, ("facilGbn", "facilKind", "facilNm"), "public facility")
    facility_name = _item_name(item)
    address = _item_address(item)
    coords = _item_lat_lon(item)
    latitude = coords[0] if coords else None
    longitude = coords[1] if coords else None
    source_record_id = _item_record_id(item)
    diagnosis = _diagnosis_result(score)
    existing = None
    if source_record_id:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM facility_inspection
            WHERE region_id = ?
              AND source_name = ?
              AND source_record_id = ?
            LIMIT 1
            """,
            (region_id, source_name, source_record_id),
        )
    if not existing:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM facility_inspection
            WHERE region_id = ?
              AND inspection_date = ?
              AND facility_type = ?
              AND facility_name = ?
              AND diagnosis_result = ?
              AND ABS(COALESCE(risk_score, 0) - ?) < 0.001
            LIMIT 1
            """,
            (region_id, inspection_date, facility_type, facility_name, diagnosis, score),
        )
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO facility_inspection(
            region_id, inspection_date, facility_type, diagnosis_result, risk_score,
            source_name, source_record_id, facility_name, address, latitude, longitude
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            inspection_date,
            facility_type,
            diagnosis,
            score,
            source_name,
            source_record_id,
            facility_name,
            address,
            latitude,
            longitude,
        ),
    )
    return True


def _insert_facility_status(conn: sqlite3.Connection, region_id: int, item: dict[str, Any], source_name: str) -> bool:
    facility_type = _first_text(item, ("facilGbn", "facilKind", "facilNm"), "public facility")
    facility_name = _item_name(item)
    address = _item_address(item)
    coords = _item_lat_lon(item)
    latitude = coords[0] if coords else None
    longitude = coords[1] if coords else None
    source_record_id = _item_record_id(item)
    age = _construction_age(item)
    inspection_date = _facility_date(item)
    inspection_rate = 100.0 if inspection_date else 0.0
    aging_count = 1 if age >= 30 else 0
    existing = None
    if source_record_id:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM facility_status
            WHERE region_id = ?
              AND source_name = ?
              AND source_record_id = ?
            LIMIT 1
            """,
            (region_id, source_name, source_record_id),
        )
    if not existing:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM facility_status
            WHERE region_id = ?
              AND facility_type = ?
              AND facility_name = ?
              AND total_count = 1
              AND aging_count = ?
              AND ABS(COALESCE(inspection_rate, 0) - ?) < 0.001
            LIMIT 1
            """,
            (region_id, facility_type, facility_name, aging_count, inspection_rate),
        )
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO facility_status(
            region_id, facility_type, total_count, aging_count, inspection_rate,
            source_name, source_record_id, facility_name, address, latitude, longitude
        )
        VALUES(?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            facility_type,
            aging_count,
            inspection_rate,
            source_name,
            source_record_id,
            facility_name,
            address,
            latitude,
            longitude,
        ),
    )
    return True


def _insert_sinkhole_history(conn: sqlite3.Connection, region_id: int, item: dict[str, Any], source_name: str) -> bool:
    text = _item_text(item)
    if source_name != "ground_subsidence_accident" and not _contains_any(text, _SINKHOLE_TERMS):
        return False
    occurrence_date = _parse_public_date(
        _first_text(item, ("sagoDate", "accdntYmd", "occrrncDe", "chckDignYmd", "sysRegDate"), "")
    )
    cause_type = _first_text(
        item,
        (
            "sagoReason",
            "grdKind",
            "accdntCauseDetail",
            "accdntContent",
            "mainChckDignContent",
            "evalNm",
            "facilNm",
            "accdntNm",
        ),
        "public data sinkhole signal",
    )[:240]
    damage_scale = _accident_damage_scale(item)
    source_record_id = _item_record_id(item)
    address = _item_address(item)
    coords = _item_lat_lon(item)
    latitude = coords[0] if coords else None
    longitude = coords[1] if coords else None
    existing = None
    if source_record_id:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM sinkhole_history
            WHERE region_id = ?
              AND source_name = ?
              AND source_record_id = ?
            LIMIT 1
            """,
            (region_id, source_name, source_record_id),
        )
    if not existing:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM sinkhole_history
            WHERE region_id = ?
              AND occurrence_date = ?
              AND cause_type = ?
              AND ABS(COALESCE(damage_scale, 0) - ?) < 0.001
            LIMIT 1
            """,
            (region_id, occurrence_date, cause_type, damage_scale),
        )
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO sinkhole_history(
            region_id, occurrence_date, cause_type, damage_scale,
            source_name, source_record_id, address, latitude, longitude
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            occurrence_date,
            cause_type,
            damage_scale,
            source_name,
            source_record_id,
            address,
            latitude,
            longitude,
        ),
    )
    return True


def _underground_risk_score(item: dict[str, Any]) -> float:
    depth = _safe_float(_ci_get(item, "maxDigDepth"), 0.0)
    score = min(70.0, depth * 2.0)
    text = _item_text(item)
    if _contains_any(text, _SINKHOLE_TERMS):
        score += 20.0
    if "진행" in text:
        score += 10.0
    return round(max(0.0, min(score, 100.0)), 1)


def _insert_underground_safety(conn: sqlite3.Connection, region_id: int, item: dict[str, Any], source_name: str) -> bool:
    safety_level = _first_text(item, ("proStage", "safetyLevel"), "registered")
    inspection_date = _parse_public_date(_first_text(item, ("sysRegDate", "regDate"), ""))
    risk_factors = _first_text(item, ("evalNm", "bizNm", "projectNm"), _item_text(item)[:240])[:500]
    project_name = _item_name(item)
    address = _item_address(item)
    coords = _item_lat_lon(item)
    latitude = coords[0] if coords else None
    longitude = coords[1] if coords else None
    source_record_id = _item_record_id(item)
    max_dig_depth = _safe_float(_ci_get(item, "maxDigDepth"), 0.0)
    risk_score = _underground_risk_score(item)
    existing = None
    if source_record_id:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM underground_safety
            WHERE region_id = ?
              AND source_name = ?
              AND source_record_id = ?
            LIMIT 1
            """,
            (region_id, source_name, source_record_id),
        )
    if not existing:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM underground_safety
            WHERE region_id = ?
              AND safety_level = ?
              AND inspection_date = ?
              AND project_name = ?
              AND ABS(COALESCE(max_dig_depth, 0) - ?) < 0.001
            LIMIT 1
            """,
            (region_id, safety_level, inspection_date, project_name, max_dig_depth),
        )
    if existing:
        return False
    conn.execute(
        """
        INSERT INTO underground_safety(
            region_id, safety_level, inspection_date, risk_factors,
            source_name, source_record_id, project_name, address, latitude, longitude, max_dig_depth, risk_score
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            region_id,
            safety_level,
            inspection_date,
            risk_factors,
            source_name,
            source_record_id,
            project_name,
            address,
            latitude,
            longitude,
            max_dig_depth,
            risk_score,
        ),
    )
    return True


def _insert_construction_from_underground(
    conn: sqlite3.Connection,
    region_id: int,
    item: dict[str, Any],
    source_name: str,
) -> bool:
    depth = _safe_float(_ci_get(item, "maxDigDepth"), 0.0)
    if depth <= 0:
        return False
    text = _item_text(item)
    if "진행" not in text and "공사" not in text and "승인" not in text:
        return False
    start_date = _parse_public_date(_first_text(item, ("sysRegDate", "regDate"), ""))
    construction_type = _item_name(item) or "underground safety evaluation"
    scale_score = min(20.0, max(1.0, depth))
    source_record_id = _item_record_id(item)
    address = _item_address(item)
    coords = _item_lat_lon(item)
    latitude = coords[0] if coords else None
    longitude = coords[1] if coords else None
    existing = None
    if source_record_id:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM construction_events
            WHERE region_id = ?
              AND source_name = ?
              AND source_record_id = ?
            LIMIT 1
            """,
            (region_id, source_name, source_record_id),
        )
    if existing:
        return False
    existing = query_one(
        conn,
        """
        SELECT id
        FROM construction_events
        WHERE region_id = ?
          AND construction_type = ?
          AND start_date = ?
          AND ABS(COALESCE(scale_score, 0) - ?) < 0.001
        LIMIT 1
        """,
        (region_id, construction_type, start_date, scale_score),
    )
    if existing:
        return False
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
            source_name,
            source_record_id,
            address,
            latitude,
            longitude,
        ),
    )
    return True


def _date_is_recent(date_value: str, lookback_days: int) -> bool:
    try:
        parsed = datetime.fromisoformat(date_value)
    except ValueError:
        return False
    return parsed >= datetime.now() - timedelta(days=max(1, int(lookback_days)))


def _insert_construction_from_permit(conn: sqlite3.Connection, item: dict[str, Any], source_name: str) -> bool:
    context = _item_context(item)
    region_id = _safe_int(context.get("region_id"), 0)
    if region_id <= 0:
        return False

    start_date = _parse_public_date(
        _first_text(item, ("realStcnsDay", "stcnsSchedDay", "archPmsDay", "crtnDay", "useAprDay"), "")
    )
    if not _date_is_recent(start_date, settings.public_data_construction_lookback_days):
        return False

    arch_type = _first_text(item, ("archGbCdNm",), "건축 인허가")
    purpose = _first_text(item, ("mainPurpsCdNm",), "")
    building_name = _item_name(item)
    construction_type = " ".join(part for part in (arch_type, purpose, building_name) if part).strip()
    area = max(_safe_float(_ci_get(item, "totArea"), 0.0), _safe_float(_ci_get(item, "archArea"), 0.0))
    building_count = _safe_float(_ci_get(item, "mainBldCnt"), 0.0) + _safe_float(_ci_get(item, "atchBldDongCnt"), 0.0)
    scale_score = min(20.0, max(1.0, math.sqrt(max(area, 1.0)) / 12.0 + building_count))
    if "신축" in arch_type:
        scale_score = min(20.0, scale_score + 2.0)

    source_record_id = _item_record_id(item)
    address = _item_address(item)
    existing = None
    if source_record_id:
        existing = query_one(
            conn,
            """
            SELECT id
            FROM construction_events
            WHERE region_id = ?
              AND source_name = ?
              AND source_record_id = ?
            LIMIT 1
            """,
            (region_id, source_name, source_record_id),
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
            construction_type[:200] or "building permit construction",
            start_date,
            round(scale_score, 2),
            source_name,
            source_record_id,
            address,
        ),
    )
    return True


def _insert_weather_data(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    regions: list[dict[str, Any]],
    source_name: str,
) -> bool:
    timestamp = _first_text(item, ("tm",), "")
    if not timestamp:
        return False
    record_date = _parse_public_date(timestamp)
    station_id = _first_text(item, ("stnId",), settings.kma_asos_station_ids)
    station_name = _first_text(item, ("stnNm",), "")
    rainfall = _safe_float(_ci_get(item, "rn"), 0.0)
    temperature = _optional_float(_ci_get(item, "ta"))
    humidity = _optional_float(_ci_get(item, "hm"))
    source_record_id = f"{station_id}:{timestamp}"
    target_sigungus = set(_csv_values(settings.kma_asos_target_sigungus))
    targets = [
        region
        for region in regions
        if not target_sigungus or str(region.get("sigungu") or "").strip() in target_sigungus
    ]

    changed = False
    for region in targets:
        region_id = int(region["region_id"])
        existing = query_one(
            conn,
            """
            SELECT id
            FROM weather_data
            WHERE region_id = ?
              AND source_name = ?
              AND source_record_id = ?
            LIMIT 1
            """,
            (region_id, source_name, source_record_id),
        )
        if existing:
            continue
        conn.execute(
            """
            INSERT INTO weather_data(
                region_id, record_date, rainfall, temperature, humidity,
                source_name, source_record_id, station_id, station_name
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                region_id,
                record_date,
                rainfall,
                temperature,
                humidity,
                source_name,
                source_record_id,
                station_id,
                station_name,
            ),
        )
        changed = True
    return changed


def _stable_source_row_number(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


def _insert_molit_borehole(conn: sqlite3.Connection, item: dict[str, Any], source_name: str) -> bool:
    borehole_code = _first_text(item, ("시추공코드", "borehole_code", "boreholeCode", "boreholeNo"), "")
    raw_x = _optional_float(_first_text(item, ("X좌표", "x", "coordX", "gisX"), ""))
    raw_y = _optional_float(_first_text(item, ("Y좌표", "y", "coordY", "gisY"), ""))
    latitude, longitude, coordinate_crs = _projected_xy_to_wgs84(raw_x, raw_y)
    elevation_m = _optional_float(_first_text(item, ("고도", "elevation", "elevation_m"), ""))
    total_depth_m = _optional_float(_first_text(item, ("시추심도", "total_depth_m", "boreDepth", "depth"), ""))
    groundwater_level_m = _optional_float(_first_text(item, ("지하수위", "groundwater_level_m", "waterLevel"), ""))
    borehole_method = _first_text(item, ("시추방법", "borehole_method", "boringMethod"), "")
    borehole_type = _first_text(item, ("시추공종류", "borehole_type", "boringType"), "")
    source_record_id = borehole_code or _item_record_id(item) or _payload_hash(item)
    source_file = source_name
    source_row_number = _stable_source_row_number(source_record_id)

    existing = query_one(
        conn,
        """
        SELECT id
        FROM molit_ground_boreholes
        WHERE source_name = ? AND source_record_id = ?
        LIMIT 1
        """,
        (source_name, source_record_id),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO molit_ground_boreholes(
            id, borehole_code, project_name, address, latitude, longitude,
            raw_x, raw_y, coordinate_crs, elevation_m, total_depth_m,
            groundwater_level_m, borehole_method, borehole_type,
            source_name, source_record_id, source_file, source_row_number, raw_json
        )
        VALUES(?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            existing["id"] if existing else None,
            borehole_code or None,
            latitude,
            longitude,
            raw_x,
            raw_y,
            coordinate_crs,
            elevation_m,
            total_depth_m,
            groundwater_level_m,
            borehole_method or None,
            borehole_type or None,
            source_name,
            source_record_id,
            source_file,
            source_row_number,
            _stable_json(item),
        ),
    )
    return not bool(existing)


def _match_region(item: dict[str, Any], regions: list[dict[str, Any]]) -> dict[str, Any] | None:
    text = _item_text(item)
    for region in regions:
        for key in ("sigungu", "region_name", "sido"):
            value = str(region.get(key) or "").strip()
            if value and value in text:
                return region
    return None


def _normalize_one_item(
    conn: sqlite3.Connection,
    source: PublicDataSource,
    item: dict[str, Any],
    regions: list[dict[str, Any]],
) -> bool:
    if source.normalizer == "weather":
        return _insert_weather_data(conn, item, regions, source.name)
    if source.normalizer == "construction_permit":
        return _insert_construction_from_permit(conn, item, source.name)
    if source.normalizer == "borehole":
        return _insert_molit_borehole(conn, item, source.name)

    target_region = _resolve_item_region(item, regions)
    if not target_region and source.normalizer == "accident":
        target_region = _resolve_region_by_dong_hint(item, regions)
    if not target_region:
        return False

    region_id = int(target_region["region_id"])
    changed = False
    if source.normalizer == "facility":
        changed = _insert_facility_inspection(conn, region_id, item, source.name) or changed
        changed = _insert_facility_status(conn, region_id, item, source.name) or changed
    elif source.normalizer == "accident":
        changed = _insert_sinkhole_history(conn, region_id, item, source.name) or changed
    elif source.normalizer == "underground":
        changed = _insert_underground_safety(conn, region_id, item, source.name) or changed
        changed = _insert_construction_from_underground(conn, region_id, item, source.name) or changed
    return changed


def _normalize_items(
    conn: sqlite3.Connection,
    source: PublicDataSource,
    saved_items: list[tuple[dict[str, Any], str]],
    regions: list[dict[str, Any]],
    region: dict[str, Any] | None = None,
) -> int:
    normalized_count = 0
    for item, digest in saved_items:
        try:
            changed = _normalize_one_item(conn, source, item, regions)
            conn.execute(
                """
                UPDATE raw_source_records
                SET normalized = 1, error_message = NULL
                WHERE source_name = ? AND payload_hash = ?
                """,
                (source.name, digest),
            )
            if changed:
                normalized_count += 1
        except Exception as exc:
            message = _redact_message(exc)[:500]
            conn.execute(
                """
                UPDATE raw_source_records
                SET error_message = ?
                WHERE source_name = ? AND payload_hash = ?
                """,
                (message, source.name, digest),
            )
            LOGGER.exception("failed to normalize public data item: %s", message)
    return normalized_count


def _clear_rebuilt_public_tables(conn: sqlite3.Connection) -> None:
    # These tables are derived from raw public-data records by this collector.
    # Rebuild them each run so changed location-matching rules do not leave stale rows.
    conn.execute("DELETE FROM facility_inspection")
    conn.execute("DELETE FROM facility_status")
    conn.execute("DELETE FROM underground_safety")
    conn.execute("DELETE FROM sinkhole_history WHERE source_name IS NOT NULL")
    conn.execute("DELETE FROM weather_data WHERE source_name IS NOT NULL")
    conn.execute("DELETE FROM construction_events WHERE source_name IS NOT NULL")
    conn.execute("DELETE FROM molit_ground_boreholes WHERE source_name = 'molit_ground_boreholes'")


def _renormalize_raw_records(conn: sqlite3.Connection, regions: list[dict[str, Any]]) -> int:
    sources = {source.name: source for source in APPROVED_SOURCES}
    rows = query_all(
        conn,
        """
        SELECT source_name, payload_hash, payload_json
        FROM raw_source_records
        ORDER BY id
        """,
    )
    normalized_count = 0
    for row in rows:
        source = sources.get(str(row["source_name"]))
        if not source:
            continue
        try:
            payload = json.loads(str(row["payload_json"]))
            item = payload.get("item") if isinstance(payload, dict) else None
            if not isinstance(item, dict):
                continue
            item = dict(item)
            context = payload.get("context") if isinstance(payload, dict) else {}
            item["_collector_context"] = context if isinstance(context, dict) else {}
            changed = _normalize_one_item(conn, source, item, regions)
            conn.execute(
                """
                UPDATE raw_source_records
                SET normalized = 1, error_message = NULL
                WHERE source_name = ? AND payload_hash = ?
                """,
                (source.name, row["payload_hash"]),
            )
            if changed:
                normalized_count += 1
        except Exception as exc:
            conn.execute(
                """
                UPDATE raw_source_records
                SET error_message = ?
                WHERE source_name = ? AND payload_hash = ?
                """,
                (_redact_message(exc)[:500], row["source_name"], row["payload_hash"]),
            )
    return normalized_count


def _rebuild_today_analysis(conn: sqlite3.Connection) -> None:
    from app.routes.analysis import analyze_region, analyze_road

    analysis_date = today_str()
    conn.execute("DELETE FROM feature_dataset WHERE analysis_date = ?", (analysis_date,))
    conn.execute("DELETE FROM road_feature_dataset WHERE analysis_date = ?", (analysis_date,))

    regions = query_all(conn, "SELECT region_id FROM regions ORDER BY region_id")
    for region in regions:
        analyze_region(conn, int(region["region_id"]), analysis_date)

    roads = query_all(conn, "SELECT road_id FROM road_segments ORDER BY road_id")
    for road in roads:
        analyze_road(conn, int(road["road_id"]), analysis_date)


def _fresh_source_skip_reason(conn: sqlite3.Connection, source: PublicDataSource) -> str | None:
    if source.name != "molit_ground_boreholes":
        return None
    row = query_one(
        conn,
        """
        SELECT MAX(fetched_at) AS fetched_at
        FROM raw_source_records
        WHERE source_name = ?
        """,
        (source.name,),
    )
    count = conn.execute("SELECT COUNT(*) FROM molit_ground_boreholes").fetchone()[0]
    fetched_at = row.get("fetched_at") if row else None
    if int(count or 0) < int(settings.molit_borehole_min_cached_rows):
        return None
    if not fetched_at:
        return None
    try:
        latest = datetime.fromisoformat(str(fetched_at))
    except ValueError:
        return None
    refresh_after = latest + timedelta(days=max(1, int(settings.molit_borehole_refresh_days)))
    if datetime.now() < refresh_after:
        return f"cached_until {refresh_after.isoformat(timespec='seconds')}"
    return None


def _collect_source(
    conn: sqlite3.Connection,
    source: PublicDataSource,
    api_key: str,
    regions: list[dict[str, Any]],
    started_at: str,
) -> dict[str, Any]:
    fetched_count = 0
    saved_count = 0
    normalized_count = 0
    errors: list[str] = []

    skip_reason = _fresh_source_skip_reason(conn, source)
    if skip_reason:
        return {
            "source": source.name,
            "label": source.label,
            "success": True,
            "fetched_count": 0,
            "saved_count": 0,
            "normalized_count": 0,
            "skipped": skip_reason,
            "errors": [],
        }

    targets = _source_targets(source, regions)
    for region in targets:
        try:
            items = _fetch_source_items(source, api_key, region)
            items = _postprocess_source_items(source, api_key, items, regions)
            fetched_count += len(items)
            context = (
                {
                    key: value
                    for key, value in {
                        "region_id": region.get("region_id"),
                        "sido": region.get("sido"),
                        "sigungu": region.get("sigungu"),
                        "sigungu_cd": region.get("sigungu_cd"),
                        "bjdong_cd": region.get("bjdong_cd"),
                    }.items()
                    if value not in (None, "")
                }
                if region
                else {"scope": "global"}
            )
            saved_items = _save_raw_records(conn, source, items, started_at, context)
            saved_count += len(saved_items)
            normalized_count += _normalize_items(conn, source, saved_items, regions, region)
            conn.commit()
        except Exception as exc:
            label = region.get("sigungu") or region.get("region_name") if region else "global"
            message = _redact_message(exc)
            errors.append(f"{label}: {message}")
            LOGGER.warning("public data source %s failed for %s: %s", source.name, label, message)
            if _is_network_wide_error(message) or "403 Client Error: Forbidden" in message:
                break

    return {
        "source": source.name,
        "label": source.label,
        "success": not errors,
        "fetched_count": fetched_count,
        "saved_count": saved_count,
        "normalized_count": normalized_count,
        "errors": errors,
    }


def collect_public_data_once() -> dict[str, Any]:
    if not _RUN_LOCK.acquire(blocking=False):
        return {**_state_copy(), "skipped": "already_running"}

    started_at = _now()
    _STATE.update(
        {
            "running": True,
            "key_loaded": bool(settings.public_data_api_key),
            "last_started_at": started_at,
            "last_error": None,
        }
    )

    conn: sqlite3.Connection | None = None
    run_id: int | None = None
    source_results: list[dict[str, Any]] = []

    try:
        conn = connect(settings.db_path)
        _ensure_collector_tables(conn)

        run_id = conn.execute(
            """
            INSERT INTO public_data_collection_runs(started_at, source_name)
            VALUES(?, ?)
            """,
            (started_at, SOURCE_BUNDLE),
        ).lastrowid
        conn.commit()

        if not settings.public_data_api_key:
            raise RuntimeError("PUBLIC_DATA_API_KEY is not set")

        regions = query_all(
            conn,
            """
            SELECT region_id, region_name, latitude, longitude, sido, sigungu
            FROM regions
            ORDER BY region_id
            """,
        )

        for source in APPROVED_SOURCES:
            result = _collect_source(conn, source, settings.public_data_api_key, regions, started_at)
            source_results.append(result)
            if any(_is_network_wide_error(error) for error in result["errors"]):
                break

        fetched_count = sum(int(result["fetched_count"]) for result in source_results)
        saved_count = sum(int(result["saved_count"]) for result in source_results)
        _clear_rebuilt_public_tables(conn)
        normalized_count = _renormalize_raw_records(conn, regions)
        errors = [
            f"{result['source']}: {'; '.join(result['errors'])}"
            for result in source_results
            if result["errors"]
        ]

        _rebuild_today_analysis(conn)
        finished_at = _now()
        success = 1 if (not errors or fetched_count > 0 or normalized_count > 0) else 0
        error_message = "; ".join(errors)[:1000] if errors else None
        conn.execute(
            """
            UPDATE public_data_collection_runs
            SET finished_at = ?,
                success = ?,
                fetched_count = ?,
                saved_count = ?,
                normalized_count = ?,
                error_message = ?
            WHERE id = ?
            """,
            (
                finished_at,
                success,
                fetched_count,
                saved_count,
                normalized_count,
                error_message,
                run_id,
            ),
        )
        conn.commit()

        _STATE.update(
            {
                "running": False,
                "last_finished_at": finished_at,
                "last_success": bool(success),
                "last_error": error_message,
                "last_fetched_count": fetched_count,
                "last_saved_count": saved_count,
                "last_normalized_count": normalized_count,
                "sources": source_results,
            }
        )
        return _state_copy()
    except Exception as exc:
        finished_at = _now()
        message = _redact_message(exc)
        fetched_count = sum(int(result.get("fetched_count", 0)) for result in source_results)
        saved_count = sum(int(result.get("saved_count", 0)) for result in source_results)
        normalized_count = sum(int(result.get("normalized_count", 0)) for result in source_results)
        if conn is not None:
            if run_id is not None:
                conn.execute(
                    """
                    UPDATE public_data_collection_runs
                    SET finished_at = ?,
                        success = 0,
                        fetched_count = ?,
                        saved_count = ?,
                        normalized_count = ?,
                        error_message = ?
                    WHERE id = ?
                    """,
                    (finished_at, fetched_count, saved_count, normalized_count, message[:1000], run_id),
                )
                conn.commit()
            else:
                conn.rollback()
        _STATE.update(
            {
                "running": False,
                "last_finished_at": finished_at,
                "last_success": False,
                "last_error": message,
                "last_fetched_count": fetched_count,
                "last_saved_count": saved_count,
                "last_normalized_count": normalized_count,
                "sources": source_results,
            }
        )
        LOGGER.warning("public data collection failed: %s", message)
        return _state_copy()
    finally:
        if conn is not None:
            conn.close()
        _RUN_LOCK.release()


async def public_data_scheduler(stop_event: asyncio.Event) -> None:
    interval = max(60, int(settings.public_data_interval_seconds))

    if settings.public_data_collect_on_start and not stop_event.is_set():
        await asyncio.to_thread(collect_public_data_once)

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            await asyncio.to_thread(collect_public_data_once)
