from __future__ import annotations

from math import inf
from typing import Any


REGION_ROAD_ADDRESSES = {
    101: "경상남도 진주시 진주대로 501",
    102: "경상남도 진주시 진주역로 130",
    103: "경상남도 진주시 충의로 19",
    104: "경상남도 진주시 남강로1번길 146",
    105: "경상남도 사천시 사천읍 사천대로 1971",
}

ROAD_ROAD_ADDRESSES = {
    1001: "경상남도 진주시 진주대로 501 동측 도로",
    1002: "경상남도 진주시 진주대로 501 서문 인근",
    1003: "경상남도 진주시 진주역로 130 중앙로 인근",
    1004: "경상남도 진주시 진주역로 130 환승로 인근",
    1005: "경상남도 진주시 충의로 19 인근",
    1006: "경상남도 진주시 남강로1번길 146 인근",
    1007: "경상남도 사천시 사천읍 사천대로 1971 인근",
}

KNOWN_ADDRESS_POINTS = (
    (35.1525, 128.1049, REGION_ROAD_ADDRESSES[101]),
    (35.1801, 128.1074, REGION_ROAD_ADDRESSES[102]),
    (35.1815, 128.1698, REGION_ROAD_ADDRESSES[103]),
    (35.1730, 128.0418, REGION_ROAD_ADDRESSES[104]),
    (35.0880, 128.0725, REGION_ROAD_ADDRESSES[105]),
)


def region_road_address(region: dict[str, Any] | None) -> str:
    if not region:
        return "도로명 주소 확인 필요"
    region_id = int(region.get("region_id") or 0)
    return REGION_ROAD_ADDRESSES.get(region_id) or str(region.get("region_name") or "도로명 주소 확인 필요")


def road_road_address(road: dict[str, Any] | None) -> str:
    if not road:
        return "도로명 주소 확인 필요"
    road_id = int(road.get("road_id") or 0)
    if road_id in ROAD_ROAD_ADDRESSES:
        return ROAD_ROAD_ADDRESSES[road_id]
    region_id = int(road.get("region_id") or 0)
    base = REGION_ROAD_ADDRESSES.get(region_id)
    road_name = str(road.get("road_name") or "").strip()
    if base and road_name:
        return f"{base} {road_name} 인근"
    return base or road_name or "도로명 주소 확인 필요"


def with_region_address(row: dict[str, Any]) -> dict[str, Any]:
    next_row = dict(row)
    next_row["road_address"] = region_road_address(next_row)
    return next_row


def with_road_address(row: dict[str, Any]) -> dict[str, Any]:
    next_row = dict(row)
    next_row["road_address"] = road_road_address(next_row)
    return next_row


def nearest_road_address(lat: float, lng: float) -> str:
    best_address = "도로명 주소 확인 필요"
    best_distance = inf
    for point_lat, point_lng, address in KNOWN_ADDRESS_POINTS:
        distance = (float(lat) - point_lat) ** 2 + (float(lng) - point_lng) ** 2
        if distance < best_distance:
            best_distance = distance
            best_address = f"{address} 인근"
    return best_address
