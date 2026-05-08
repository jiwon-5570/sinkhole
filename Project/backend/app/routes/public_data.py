from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.main_deps import get_db
from app.services.public_data_collector import collect_public_data_once, get_public_data_status
from app.utils.response import ok


router = APIRouter()


@router.get("/api/public-data/status")
def public_data_status() -> dict:
    return ok(get_public_data_status())


@router.post("/api/public-data/refresh")
def refresh_public_data() -> dict:
    return ok(collect_public_data_once())


@router.get("/api/public-data/ground-layers/status")
def ground_layers_status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    layer_count = conn.execute("SELECT COUNT(*) FROM molit_ground_layers").fetchone()[0]
    borehole_count = conn.execute("SELECT COUNT(*) FROM molit_ground_boreholes").fetchone()[0]
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
            "ground_layers_with_coordinates": int(layer_coord_count),
            "layers_file_dir": "Project/backend/data/raw/public/molit_ground_layers",
            "boreholes_file_dir": "Project/backend/data/raw/public/molit_boreholes",
        }
    )
