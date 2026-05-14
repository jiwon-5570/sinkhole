from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.config.settings import settings
from app.db.core import query_all
from app.main_deps import get_db
from app.routes.analysis import analyze_region, analyze_road
from app.services.features import today_str
from app.services.local_construction_importer import (
    import_local_construction_files,
    local_construction_import_status,
)
from app.services.public_data_collector import collect_public_data_once, get_public_data_status
from app.services.seoul_open_data_collector import collect_seoul_open_data_once
from app.utils.response import ok


router = APIRouter()


@router.get("/api/public-data/status")
def public_data_status() -> dict:
    return ok(get_public_data_status())


@router.post("/api/public-data/refresh")
def refresh_public_data() -> dict:
    return ok(collect_public_data_once())


@router.get("/api/public-data/seoul/status")
def seoul_open_data_status() -> dict:
    return ok(
        {
            "enabled": bool(settings.seoul_open_data_enabled),
            "key_loaded": bool(settings.seoul_open_data_api_key),
            "base_url": settings.seoul_open_data_base_url,
            "services": {
                "groundwater_observations": settings.seoul_groundwater_observation_service,
                "rainfall": settings.seoul_rainfall_service,
                "sewer_levels": settings.seoul_sewer_level_service,
                "road_excavation": settings.seoul_road_excavation_service,
            },
            "tables": {
                "seoul_groundwater_observations": "groundwater observations normalized into groundwater_data",
                "seoul_sewer_levels": "sewer levels normalized into environment_features",
                "weather_data": "Seoul rainfall observations",
                "construction_events": "Seoul road excavation events",
            },
        }
    )


@router.post("/api/public-data/seoul/import")
def refresh_seoul_open_data(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    result = collect_seoul_open_data_once(conn)
    analysis_date = today_str()
    conn.execute("DELETE FROM feature_dataset WHERE analysis_date = ?", (analysis_date,))
    conn.execute("DELETE FROM road_feature_dataset WHERE analysis_date = ?", (analysis_date,))
    for region in query_all(conn, "SELECT region_id FROM regions ORDER BY region_id"):
        analyze_region(conn, int(region["region_id"]), analysis_date)
    for road in query_all(conn, "SELECT road_id FROM road_segments ORDER BY road_id"):
        analyze_road(conn, int(road["road_id"]), analysis_date)
    return ok(result)


@router.get("/api/public-data/local-construction/status")
def local_construction_status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return ok(local_construction_import_status(conn))


@router.post("/api/public-data/local-construction/import")
def refresh_local_construction(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    result = import_local_construction_files(conn, force=True)
    if result.get("changed"):
        analysis_date = today_str()
        for region in query_all(conn, "SELECT region_id FROM regions ORDER BY region_id"):
            analyze_region(conn, int(region["region_id"]), analysis_date)
        for road in query_all(conn, "SELECT road_id FROM road_segments ORDER BY road_id"):
            analyze_road(conn, int(road["road_id"]), analysis_date)
    return ok(result)


@router.get("/api/public-data/ground-layers/status")
def ground_layers_status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    layer_count = conn.execute("SELECT COUNT(*) FROM molit_ground_layers").fetchone()[0]
    borehole_count = conn.execute("SELECT COUNT(*) FROM molit_ground_boreholes").fetchone()[0]
    borehole_coord_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM molit_ground_boreholes
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """
    ).fetchone()[0]
    layer_coord_count = conn.execute(
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
    return ok(
        {
            "ground_layers": int(layer_count),
            "ground_boreholes": int(borehole_count),
            "ground_boreholes_with_coordinates": int(borehole_coord_count),
            "ground_layers_with_coordinates": int(layer_coord_count),
            "borehole_api_enabled": bool(settings.molit_borehole_api_enabled),
            "borehole_api_url": settings.molit_borehole_api_url,
            "borehole_coord_crs": settings.molit_borehole_coord_crs,
            "layers_file_dir": "Project/backend/data/raw/public/molit_ground_layers",
            "boreholes_file_dir": "Project/backend/data/raw/public/molit_boreholes",
            "boreholes_file_dir_note": "fallback only; the approved OpenAPI is collected with PUBLIC_DATA_API_KEY",
        }
    )
