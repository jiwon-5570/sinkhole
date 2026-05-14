from __future__ import annotations

import json
from pathlib import Path
import sys

# Allow `python scripts/import_seoul_road_excavation.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import settings
from app.db.core import connect, query_all
from app.db.migrate import apply_schema
from app.routes.analysis import analyze_region, analyze_road
from app.services.features import today_str
from app.services.local_construction_importer import construction_import_dir, import_local_construction_files


def main() -> None:
    conn = connect(settings.db_path)
    try:
        apply_schema(conn, settings.schema_path)
        result = import_local_construction_files(conn, force=True)
        if result.get("changed"):
            analysis_date = today_str()
            for region in query_all(conn, "SELECT region_id FROM regions ORDER BY region_id"):
                analyze_region(conn, int(region["region_id"]), analysis_date)
            for road in query_all(conn, "SELECT road_id FROM road_segments ORDER BY road_id"):
                analyze_road(conn, int(road["road_id"]), analysis_date)
        conn.commit()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    if not any(construction_import_dir().glob("*")):
        print(f"No files found. Put CSV/XLSX files here: {construction_import_dir()}")
    main()
