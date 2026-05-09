from __future__ import annotations

if __name__ == "__main__" and __package__ is None:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from contextlib import asynccontextmanager, suppress
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
from app.routes.public_data import router as public_data_router
from app.routes.regions import router as regions_router
from app.routes.roads import router as roads_router
from app.routes.report import router as report_router
from app.routes.simulation import router as simulation_router
from app.security import BasicAuthMiddleware
from app.services.features import today_str
from app.services.public_data_collector import public_data_scheduler
from app.services.real_data_targets import ensure_public_ground_regions


STATIC_DIR = Path(__file__).resolve().parent / "static"


def initialize_app_data() -> None:
    conn = connect(settings.db_path)
    try:
        if settings.apply_schema_on_start:
            apply_schema(conn, settings.schema_path)
        if settings.seed_demo_data:
            raise RuntimeError("SINKHOLE_SEED_DEMO is disabled for real-data operation.")

        ensure_public_ground_regions(conn)

        if settings.analyze_on_start:
            analysis_date = today_str()
            regions = query_all(conn, "SELECT region_id FROM regions ORDER BY region_id")
            for region in regions:
                analyze_region(conn, int(region["region_id"]), analysis_date)
            roads = query_all(conn, "SELECT road_id FROM road_segments ORDER BY road_id")
            for road in roads:
                analyze_road(conn, int(road["road_id"]), analysis_date)

        conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_app_data()
    stop_event = asyncio.Event()
    public_data_task: asyncio.Task | None = None
    if settings.public_data_auto_collect:
        public_data_task = asyncio.create_task(public_data_scheduler(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        if public_data_task:
            public_data_task.cancel()
            with suppress(asyncio.CancelledError):
                await public_data_task


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
                        "monitoring_point_count": 0,
                        "recent_detection_count": 0,
                    },
                }

            metrics = query_one(
                conn,
                """
                SELECT
                    COUNT(*) AS region_count,
                    COALESCE(SUM(CASE WHEN total_risk_score >= 60 THEN 1 ELSE 0 END), 0) AS high_risk_count,
                    COALESCE(SUM(CASE WHEN total_risk_score >= 80 THEN 1 ELSE 0 END), 0) AS very_high_risk_count,
                    COALESCE(AVG(total_risk_score), 0) AS average_risk_score
                FROM risk_analysis_result
                WHERE analysis_date = ?
                """,
                (analysis_date,),
            )
            recent_detection = query_one(
                conn,
                """
                SELECT COUNT(*) AS count
                FROM sinkhole_history
                WHERE occurrence_date IS NOT NULL
                  AND date(occurrence_date) >= date('now', '-1 day')
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
                    "monitoring_point_count": 0,
                    "recent_detection_count": int((recent_detection or {}).get("count") or 0),
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
                    "name": "GNU Gajwa Campus, Jinju",
                    "latitude": 35.1525,
                    "longitude": 128.1049,
                },
            },
        }

    api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    api.include_router(health_router)
    api.include_router(regions_router)
    api.include_router(roads_router)
    api.include_router(map_router)
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
