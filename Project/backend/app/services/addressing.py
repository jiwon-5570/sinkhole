from __future__ import annotations

from math import inf
from typing import Any


REGION_ROAD_ADDRESSES = {
    900001: "서울특별시 강동구 천호대로 1095 인근",
    900002: "서울특별시 강남구 테헤란로 152 인근",
    900003: "서울특별시 송파구 송파대로 167 인근",
    900004: "서울특별시 송파구 올림픽로 300 인근",
    900005: "서울특별시 송파구 중대로 135 인근",
    900006: "서울특별시 강서구 마곡중앙로 161 인근",
    900007: "서울특별시 영등포구 국회대로 608 인근",
    900008: "서울특별시 서초구 서초대로 396 인근",
    900009: "서울특별시 성동구 왕십리로 222 인근",
    900010: "서울특별시 마포구 월드컵북로 400 인근",
    900011: "서울특별시 용산구 한강대로 405 인근",
    900012: "서울특별시 구로구 디지털로 300 인근",
}

ROAD_ROAD_ADDRESSES = {
    1001: "서울특별시 강남구 테헤란로 인근",
    1002: "서울특별시 송파구 송파대로 인근",
    1003: "서울특별시 강동구 천호대로 인근",
    1004: "서울특별시 강서구 마곡중앙로 인근",
    1005: "서울특별시 영등포구 국회대로 인근",
    1006: "서울특별시 서초구 서초대로 인근",
    1007: "서울특별시 마포구 월드컵북로 인근",
}

KNOWN_ADDRESS_POINTS = (
    (37.5640, 127.1738, REGION_ROAD_ADDRESSES[900001]),
    (37.5239, 127.0264, REGION_ROAD_ADDRESSES[900002]),
    (37.4778, 127.1242, REGION_ROAD_ADDRESSES[900003]),
    (37.5223, 127.0762, REGION_ROAD_ADDRESSES[900004]),
    (37.5254, 127.1235, REGION_ROAD_ADDRESSES[900005]),
    (37.5666, 126.8312, REGION_ROAD_ADDRESSES[900006]),
    (37.5275, 126.9269, REGION_ROAD_ADDRESSES[900007]),
    (37.4780, 127.0265, REGION_ROAD_ADDRESSES[900008]),
    (37.5724, 127.0268, REGION_ROAD_ADDRESSES[900009]),
    (37.5734, 126.8783, REGION_ROAD_ADDRESSES[900010]),
    (37.5246, 126.9693, REGION_ROAD_ADDRESSES[900011]),
    (37.5239, 126.8805, REGION_ROAD_ADDRESSES[900012]),
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
            best_address = address if address.endswith("인근") else f"{address} 인근"
    return best_address
