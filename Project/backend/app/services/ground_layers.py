from __future__ import annotations

from collections import Counter
from math import atan2, cos, radians, sin, sqrt
import sqlite3
from typing import Any


DEFAULT_RADIUS_M = 1500.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = radians(lat1)
    phi2 = radians(lat2)
    d_phi = radians(lat2 - lat1)
    d_lambda = radians(lon2 - lon1)
    a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
    return 2 * radius * atan2(sqrt(a), sqrt(1 - a))


def _layer_risk_score(row: dict[str, Any]) -> float:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("layer_name", "soil_class", "layer_description")
    ).lower()
    weights = (
        ("폐기", 5.5),
        ("매립", 5.0),
        ("성토", 4.5),
        ("연약", 4.5),
        ("점토", 3.5),
        ("clay", 3.5),
        ("실트", 3.0),
        ("silt", 3.0),
        ("충적", 3.0),
        ("풍화토", 2.5),
        ("모래", 2.0),
        ("sand", 2.0),
        ("사질", 2.0),
        ("자갈", 1.2),
        ("gravel", 1.2),
        ("풍화암", 1.0),
        ("연암", 0.6),
        ("경암", 0.0),
        ("암반", 0.0),
        ("rock", 0.0),
    )
    score = 0.0
    for keyword, weight in weights:
        if keyword in text:
            score = max(score, weight)

    n_value = row.get("n_value")
    if n_value is not None:
        n = _num(n_value)
        if 0 < n < 4:
            score += 1.2
        elif 0 < n < 10:
            score += 0.6

    thickness = _num(row.get("thickness_m"))
    if thickness >= 5.0 and score >= 2.0:
        score += 0.5
    return max(0.0, min(6.0, score))


def summarize_ground_layers_near(
    conn: sqlite3.Connection,
    latitude: float | None,
    longitude: float | None,
    *,
    radius_m: float = DEFAULT_RADIUS_M,
    limit: int = 20,
) -> dict[str, Any]:
    if latitude is None or longitude is None:
        return {"available": False, "reason": "missing target coordinate", "score": 0.0}

    lat = float(latitude)
    lon = float(longitude)
    lat_delta = radius_m / 111320.0
    lon_delta = radius_m / max(111320.0 * cos(radians(lat)), 1.0)

    rows = conn.execute(
        """
        SELECT
            l.borehole_code,
            COALESCE(l.project_name, b.project_name) AS project_name,
            COALESCE(l.address, b.address) AS address,
            COALESCE(l.latitude, b.latitude) AS latitude,
            COALESCE(l.longitude, b.longitude) AS longitude,
            l.layer_sequence,
            l.top_depth_m,
            l.bottom_depth_m,
            l.thickness_m,
            l.layer_name,
            l.layer_color,
            l.layer_description,
            l.soil_class,
            l.n_value,
            l.source_file
        FROM molit_ground_layers l
        LEFT JOIN molit_ground_boreholes b
          ON b.borehole_code IS NOT NULL
         AND l.borehole_code IS NOT NULL
         AND b.borehole_code = l.borehole_code
        WHERE COALESCE(l.latitude, b.latitude) BETWEEN ? AND ?
          AND COALESCE(l.longitude, b.longitude) BETWEEN ? AND ?
        LIMIT 5000
        """,
        (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta),
    ).fetchall()

    nearby: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item_lat = _num(item.get("latitude"), None)
        item_lon = _num(item.get("longitude"), None)
        if item_lat is None or item_lon is None:
            continue
        distance_m = _haversine_m(lat, lon, item_lat, item_lon)
        if distance_m <= radius_m:
            item["distance_m"] = round(distance_m, 1)
            item["risk_score"] = round(_layer_risk_score(item), 2)
            nearby.append(item)

    if not nearby:
        total_rows = conn.execute("SELECT COUNT(*) FROM molit_ground_layers").fetchone()[0]
        return {
            "available": total_rows > 0,
            "reason": "no nearby layer with coordinates",
            "score": 0.0,
            "nearby_count": 0,
            "total_layer_rows": int(total_rows),
            "radius_m": radius_m,
        }

    nearby.sort(key=lambda item: (item["distance_m"], -item["risk_score"]))
    scoring_rows = nearby[: max(limit, 1)]
    max_score = max(float(item["risk_score"]) for item in scoring_rows)
    avg_score = sum(float(item["risk_score"]) for item in scoring_rows) / len(scoring_rows)
    score = min(6.0, max(max_score, avg_score + min(len(scoring_rows), 10) * 0.08))

    layer_counter = Counter(
        str(item.get("layer_name") or item.get("soil_class") or "미분류").strip() or "미분류"
        for item in scoring_rows
    )
    return {
        "available": True,
        "score": round(score, 2),
        "nearby_count": len(nearby),
        "radius_m": radius_m,
        "dominant_layers": [
            {"name": name, "count": count}
            for name, count in layer_counter.most_common(5)
        ],
        "nearest_layers": [
            {
                "borehole_code": item.get("borehole_code"),
                "layer_name": item.get("layer_name") or item.get("soil_class"),
                "top_depth_m": item.get("top_depth_m"),
                "bottom_depth_m": item.get("bottom_depth_m"),
                "distance_m": item.get("distance_m"),
                "risk_score": item.get("risk_score"),
                "address": item.get("address"),
            }
            for item in scoring_rows[:5]
        ],
    }


def summarize_ground_layers_for_region(conn: sqlite3.Connection, region_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT latitude, longitude FROM regions WHERE region_id = ?",
        (region_id,),
    ).fetchone()
    if not row:
        return {"available": False, "reason": "region not found", "score": 0.0}
    return summarize_ground_layers_near(conn, row["latitude"], row["longitude"])


def summarize_ground_layers_for_road(conn: sqlite3.Connection, road_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT center_lat, center_lon FROM road_segments WHERE road_id = ?",
        (road_id,),
    ).fetchone()
    if not row:
        return {"available": False, "reason": "road not found", "score": 0.0}
    return summarize_ground_layers_near(conn, row["center_lat"], row["center_lon"])

