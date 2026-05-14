from __future__ import annotations

if __name__ == "__main__" and __package__ is None:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.db.core import connect, query_all, query_one
from app.db.migrate import apply_schema
from app.routes.analysis import analyze_region, analyze_road, router as analysis_router
from app.routes.chat import router as chat_router
from app.routes.charts import router as charts_router
from app.routes.commercial import router as commercial_router
from app.routes.compare import router as compare_router
from app.routes.health import router as health_router
from app.routes.map import router as map_router
from app.routes.monitoring import router as monitoring_router
from app.routes.public_data import router as public_data_router
from app.routes.regions import router as regions_router
from app.routes.roads import router as roads_router
from app.routes.report import router as report_router
from app.routes.simulation import router as simulation_router
from app.security import BasicAuthMiddleware
from app.services.features import today_str
from app.services.local_construction_importer import import_local_construction_files
from app.services.monitoring_points import (
    active_monitoring_count,
    ensure_monitoring_table,
    recent_monitoring_detection_count,
)
from app.services.public_data_collector import public_data_scheduler
from app.services.real_data_targets import ensure_public_ground_regions


STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGGER = logging.getLogger(__name__)


def _reanalyze_all_targets(conn, analysis_date: str) -> None:
    regions = query_all(conn, "SELECT region_id FROM regions ORDER BY region_id")
    for region in regions:
        analyze_region(conn, int(region["region_id"]), analysis_date)
    roads = query_all(conn, "SELECT road_id FROM road_segments ORDER BY road_id")
    for road in roads:
        analyze_road(conn, int(road["road_id"]), analysis_date)


def import_local_construction_and_reanalyze() -> dict:
    conn = connect(settings.db_path)
    try:
        result = import_local_construction_files(conn)
        if result.get("changed"):
            _reanalyze_all_targets(conn, today_str())
        conn.commit()
        return result
    finally:
        conn.close()


def initialize_app_data() -> None:
    conn = connect(settings.db_path)
    try:
        if settings.apply_schema_on_start:
            apply_schema(conn, settings.schema_path)
        if settings.seed_demo_data:
            raise RuntimeError("SINKHOLE_SEED_DEMO is disabled for real-data operation.")

        ensure_public_ground_regions(conn)
        ensure_monitoring_table(conn)

        if settings.local_construction_file_import_enabled:
            import_local_construction_files(conn)

        if settings.analyze_on_start:
            analysis_date = today_str()
            _reanalyze_all_targets(conn, analysis_date)

        conn.commit()
    finally:
        conn.close()


def recent_detection_count(conn) -> int:
    recent_sinkholes = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM sinkhole_history
        WHERE occurrence_date IS NOT NULL
          AND date(occurrence_date) >= date('now', 'localtime', '-1 day')
        """,
    )
    return int((recent_sinkholes or {}).get("count") or 0) + recent_monitoring_detection_count(conn)


async def local_construction_file_scheduler(stop_event: asyncio.Event) -> None:
    interval = max(5, int(settings.local_construction_file_import_interval_seconds))
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            try:
                result = await asyncio.to_thread(import_local_construction_and_reanalyze)
                if result.get("changed"):
                    LOGGER.info("local construction files imported: %s", result)
            except Exception as exc:
                LOGGER.warning("local construction file import failed: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_app_data()
    stop_event = asyncio.Event()
    public_data_task: asyncio.Task | None = None
    local_construction_task: asyncio.Task | None = None
    if settings.public_data_auto_collect:
        public_data_task = asyncio.create_task(public_data_scheduler(stop_event))
    if settings.local_construction_file_import_enabled:
        local_construction_task = asyncio.create_task(local_construction_file_scheduler(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        if public_data_task:
            public_data_task.cancel()
            with suppress(asyncio.CancelledError):
                await public_data_task
        if local_construction_task:
            local_construction_task.cancel()
            with suppress(asyncio.CancelledError):
                await local_construction_task


def create_app() -> FastAPI:
    load_dotenv()
    settings.validate()
    api = FastAPI(title="sinkhole backend", version="0.1.0", lifespan=lifespan)
    api.add_middleware(BasicAuthMiddleware)

    @api.get("/")
    def root() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @api.get("/ui")
    def ui() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @api.get("/index.html")
    def index_html() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @api.get("/api/summary")
    def summary() -> dict:
        conn = connect(settings.db_path)
        try:
            latest_date_row = query_one(conn, "SELECT MAX(analysis_date) AS analysis_date FROM risk_analysis_result")
            analysis_date = latest_date_row["analysis_date"] if latest_date_row else None
            if not analysis_date:
                return {
                    "success": True,
                    "message": "요청이 정상적으로 처리되었습니다.",
                    "data": {
                        "analysis_date": None,
                        "region_count": 0,
                        "high_risk_count": 0,
                        "very_high_risk_count": 0,
                        "average_risk_score": 0,
                        "monitoring_point_count": active_monitoring_count(conn),
                        "recent_detection_count": recent_detection_count(conn),
                    },
                }

            metrics = query_one(
                conn,
                """
                WITH latest AS (
                    SELECT *
                    FROM (
                        SELECT
                            r.*,
                            ROW_NUMBER() OVER (
                                PARTITION BY r.region_id
                                ORDER BY r.analysis_date DESC, r.id DESC
                            ) AS latest_rank
                        FROM risk_analysis_result r
                    )
                    WHERE latest_rank = 1
                )
                SELECT
                    COUNT(*) AS region_count,
                    COALESCE(SUM(CASE WHEN total_risk_score >= 60 THEN 1 ELSE 0 END), 0) AS high_risk_count,
                    COALESCE(SUM(CASE WHEN total_risk_score >= 80 THEN 1 ELSE 0 END), 0) AS very_high_risk_count,
                    COALESCE(AVG(total_risk_score), 0) AS average_risk_score
                FROM latest
                """,
            )
            return {
                "success": True,
                "message": "요청이 정상적으로 처리되었습니다.",
                "data": {
                    "analysis_date": analysis_date,
                    "region_count": int(metrics["region_count"]),
                    "high_risk_count": int(metrics["high_risk_count"]),
                    "very_high_risk_count": int(metrics["very_high_risk_count"]),
                    "average_risk_score": round(float(metrics["average_risk_score"]), 1),
                    "monitoring_point_count": active_monitoring_count(conn),
                    "recent_detection_count": recent_detection_count(conn),
                },
            }
        finally:
            conn.close()

    @api.get("/api/app-config")
    def app_config() -> dict:
        return {
            "success": True,
            "message": "OK",
            "data": {
                "google_maps_enabled": bool(settings.google_maps_api_key and settings.expose_google_maps_api_key),
                "google_maps_api_key": (
                    settings.google_maps_api_key
                    if settings.google_maps_api_key and settings.expose_google_maps_api_key
                    else None
                ),
                "default_mode": "live",
                "scenario_center": {
                    "name": "Seoul Metropolitan Risk Center",
                    "latitude": 37.54,
                    "longitude": 127.04,
                },
            },
        }

    api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    api.include_router(health_router)
    api.include_router(regions_router)
    api.include_router(roads_router)
    api.include_router(map_router)
    api.include_router(monitoring_router)
    api.include_router(public_data_router)
    api.include_router(analysis_router)
    api.include_router(chat_router)
    api.include_router(charts_router)
    api.include_router(compare_router)
    api.include_router(report_router)
    api.include_router(commercial_router)
    api.include_router(simulation_router)
    return api


app = create_app()


def run() -> None:
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover
        raise SystemExit("uvicorn is required. Run `pip install -r requirements.txt` and try again.") from exc

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
    )


if __name__ == "__main__":
    run()
