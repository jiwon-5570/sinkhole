from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() in {"1", "true", "True", "yes", "YES", "on", "ON"}


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("SINKHOLE_ENV", "development")
    app_host: str = os.getenv("SINKHOLE_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("PORT", os.getenv("SINKHOLE_PORT", "5000")))
    app_reload: bool = _bool_env("SINKHOLE_RELOAD", os.getenv("SINKHOLE_ENV", "development") != "production")

    db_path: Path = Path(os.getenv("SINKHOLE_DB_PATH", str(BASE_DIR / "db" / "app.db")))
    schema_path: Path = Path(os.getenv("SINKHOLE_SCHEMA_PATH", str(BASE_DIR / "db" / "schema.sql")))
    reports_dir: Path = Path(os.getenv("SINKHOLE_REPORTS_DIR", str(BASE_DIR / "data" / "reports")))

    apply_schema_on_start: bool = _bool_env("SINKHOLE_APPLY_SCHEMA_ON_START", True)
    # 운영 기준에서는 임의 seed 데이터가 실제 위험도에 섞이면 안 됩니다.
    # 남아 있는 데모 seed 경로는 실행하지 않으며, true이면 앱 시작을 중단합니다.
    seed_demo_data: bool = _bool_env("SINKHOLE_SEED_DEMO", False)
    analyze_on_start: bool = _bool_env("SINKHOLE_ANALYZE_ON_START", True)

    basic_auth_enabled: bool = _bool_env(
        "SINKHOLE_ENABLE_BASIC_AUTH",
        os.getenv("SINKHOLE_ENV", "development") == "production",
    )
    basic_auth_username: str | None = os.getenv("SINKHOLE_BASIC_AUTH_USERNAME")
    basic_auth_password: str | None = os.getenv("SINKHOLE_BASIC_AUTH_PASSWORD")

    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    google_maps_api_key: str | None = os.getenv("GOOGLE_MAPS_API_KEY")
    expose_google_maps_api_key: bool = _bool_env("SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY", False)

    # 공공데이터포털 API 키 추가
    public_data_api_key: str | None = os.getenv("PUBLIC_DATA_API_KEY")
    external_request_timeout_seconds: float = _float_env("SINKHOLE_EXTERNAL_TIMEOUT_SECONDS", 15.0)
    gemini_timeout_seconds: float = _float_env("SINKHOLE_GEMINI_TIMEOUT_SECONDS", 30.0)
    public_data_timeout_seconds: float = _float_env("SINKHOLE_PUBLIC_DATA_TIMEOUT_SECONDS", 20.0)
    public_data_auto_collect: bool = _bool_env("SINKHOLE_PUBLIC_DATA_AUTO_COLLECT", True)
    public_data_collect_on_start: bool = _bool_env("SINKHOLE_PUBLIC_DATA_COLLECT_ON_START", True)
    public_data_interval_seconds: int = _int_env("SINKHOLE_PUBLIC_DATA_INTERVAL_SECONDS", 3600)
    public_data_rows_per_page: int = _int_env("SINKHOLE_PUBLIC_DATA_ROWS_PER_PAGE", 100)
    public_data_max_pages: int = _int_env("SINKHOLE_PUBLIC_DATA_MAX_PAGES", 3)
    public_data_match_radius_m: float = _float_env("SINKHOLE_PUBLIC_DATA_MATCH_RADIUS_M", 5000.0)
    public_data_accident_lookback_days: int = _int_env("SINKHOLE_PUBLIC_DATA_ACCIDENT_LOOKBACK_DAYS", 3650)
    public_data_weather_lookback_days: int = _int_env("SINKHOLE_PUBLIC_DATA_WEATHER_LOOKBACK_DAYS", 14)
    public_data_construction_lookback_days: int = _int_env("SINKHOLE_PUBLIC_DATA_CONSTRUCTION_LOOKBACK_DAYS", 1095)
    molit_borehole_api_enabled: bool = _bool_env("SINKHOLE_MOLIT_BOREHOLE_API_ENABLED", True)
    molit_borehole_api_url: str = os.getenv(
        "SINKHOLE_MOLIT_BOREHOLE_API_URL",
        "https://api.odcloud.kr/api/15069365/v1/uddi:e3857d80-b97e-4693-84d5-f2b4f37959f0",
    )
    molit_borehole_rows_per_page: int = _int_env("SINKHOLE_MOLIT_BOREHOLE_ROWS_PER_PAGE", 1000)
    molit_borehole_max_pages: int = _int_env("SINKHOLE_MOLIT_BOREHOLE_MAX_PAGES", 500)
    molit_borehole_refresh_days: int = _int_env("SINKHOLE_MOLIT_BOREHOLE_REFRESH_DAYS", 30)
    molit_borehole_min_cached_rows: int = _int_env("SINKHOLE_MOLIT_BOREHOLE_MIN_CACHED_ROWS", 300000)
    molit_borehole_coord_crs: str = os.getenv("SINKHOLE_MOLIT_BOREHOLE_COORD_CRS", "EPSG:5186")
    kalis_public_facility_safety_url: str = os.getenv(
        "SINKHOLE_KALIS_PUBLIC_FACILITY_SAFETY_URL",
        "http://apis.data.go.kr/B552016/PublicFacilSafetyMngService/getPublicFacilSafetyMngList",
    )
    kalis_public_facility_diagnosis_url: str = os.getenv(
        "SINKHOLE_KALIS_PUBLIC_FACILITY_DIAGNOSIS_URL",
        "http://apis.data.go.kr/B552016/PublicFacilDignService/getArDignList",
    )
    kalis_old_facility_url: str = os.getenv(
        "SINKHOLE_KALIS_OLD_FACILITY_URL",
        "http://apis.data.go.kr/B552016/OldFacilService/getFacil30YearsOldList",
    )
    kalis_facility_accident_url: str = os.getenv(
        "SINKHOLE_KALIS_FACILITY_ACCIDENT_URL",
        "http://apis.data.go.kr/B552016/FacilAccidentService/getFacilAccidentList",
    )
    underground_safety_info_url: str = os.getenv(
        "SINKHOLE_UNDERGROUND_SAFETY_INFO_URL",
        "http://apis.data.go.kr/1613000/undergroundsafetyinfo01/getImpatEvalutionList01",
    )
    ground_subsidence_accident_url: str = os.getenv(
        "SINKHOLE_GROUND_SUBSIDENCE_ACCIDENT_URL",
        "http://apis.data.go.kr/1613000/undergroundsafetyinfo01/getSubsidenceList01",
    )
    kma_asos_hourly_url: str = os.getenv(
        "SINKHOLE_KMA_ASOS_HOURLY_URL",
        "http://apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList",
    )
    kma_asos_station_ids: str = os.getenv("SINKHOLE_KMA_ASOS_STATION_IDS", "192")
    kma_asos_target_sigungus: str = os.getenv("SINKHOLE_KMA_ASOS_TARGET_SIGUNGUS", "진주시")
    building_permit_url: str = os.getenv(
        "SINKHOLE_BUILDING_PERMIT_URL",
        "http://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo",
    )

    def validate(self) -> None:
        if self.basic_auth_enabled and not (self.basic_auth_username and self.basic_auth_password):
            raise RuntimeError(
                "Basic auth is enabled. Set SINKHOLE_BASIC_AUTH_USERNAME and "
                "SINKHOLE_BASIC_AUTH_PASSWORD."
            )


settings = Settings()
