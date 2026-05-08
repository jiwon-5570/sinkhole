-- SQLite prototype schema (derived from docs/03_DB_제작_가이드.md)

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS regions (
    region_id INTEGER PRIMARY KEY,
    region_name TEXT,
    region_type TEXT,
    latitude REAL,
    longitude REAL,
    sido TEXT,
    sigungu TEXT,
    geom TEXT
);

CREATE TABLE IF NOT EXISTS road_segments (
    road_id INTEGER PRIMARY KEY,
    region_id INTEGER,
    road_name TEXT,
    road_type TEXT,
    start_lat REAL,
    start_lon REAL,
    end_lat REAL,
    end_lon REAL,
    center_lat REAL,
    center_lon REAL,
    length_m REAL,
    geometry TEXT,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE IF NOT EXISTS sinkhole_history (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    occurrence_date TEXT,
    cause_type TEXT,
    damage_scale REAL,
    source_name TEXT,
    source_record_id TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE IF NOT EXISTS gpr_inspection (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    inspection_date TEXT,
    cavity_detected INTEGER,
    cavity_count INTEGER,
    depth_estimate REAL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE IF NOT EXISTS road_sinkhole_history (
    id INTEGER PRIMARY KEY,
    road_id INTEGER,
    occurrence_date TEXT,
    section_start TEXT,
    section_end TEXT,
    cause_type TEXT,
    damage_scale REAL,
    FOREIGN KEY (road_id) REFERENCES road_segments(road_id)
);

CREATE TABLE IF NOT EXISTS road_gpr_inspection (
    id INTEGER PRIMARY KEY,
    road_id INTEGER,
    inspection_date TEXT,
    cavity_detected INTEGER,
    cavity_count INTEGER,
    depth_estimate REAL,
    FOREIGN KEY (road_id) REFERENCES road_segments(road_id)
);

CREATE TABLE IF NOT EXISTS facility_safety (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    facility_type TEXT,
    aging_score REAL,
    inspection_count INTEGER,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

-- 새 테이블: 공공시설물 점검진단 실시 정보
CREATE TABLE IF NOT EXISTS facility_inspection (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    inspection_date TEXT,
    facility_type TEXT,
    diagnosis_result TEXT,  -- "안전", "주의", "위험"
    risk_score REAL,
    source_name TEXT,
    source_record_id TEXT,
    facility_name TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

-- 새 테이블: 공공시설물 안전관리 현황
CREATE TABLE IF NOT EXISTS facility_status (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    facility_type TEXT,
    total_count INTEGER,
    aging_count INTEGER,
    inspection_rate REAL,
    source_name TEXT,
    source_record_id TEXT,
    facility_name TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

-- 새 테이블: 지하안전정보
CREATE TABLE IF NOT EXISTS underground_safety (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    safety_level TEXT,
    inspection_date TEXT,
    risk_factors TEXT,
    source_name TEXT,
    source_record_id TEXT,
    project_name TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    max_dig_depth REAL,
    risk_score REAL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

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

CREATE TABLE IF NOT EXISTS road_facility_safety (
    id INTEGER PRIMARY KEY,
    road_id INTEGER,
    facility_type TEXT,
    aging_score REAL,
    inspection_count INTEGER,
    FOREIGN KEY (road_id) REFERENCES road_segments(road_id)
);

CREATE TABLE IF NOT EXISTS road_environment_features (
    id INTEGER PRIMARY KEY,
    road_id INTEGER,
    building_density REAL,
    road_density REAL,
    land_use_type TEXT,
    drainage_quality REAL,
    slope_grade REAL,
    FOREIGN KEY (road_id) REFERENCES road_segments(road_id)
);

CREATE TABLE IF NOT EXISTS road_construction_events (
    id INTEGER PRIMARY KEY,
    road_id INTEGER,
    construction_type TEXT,
    start_date TEXT,
    end_date TEXT,
    scale_score REAL,
    impact_score REAL,
    FOREIGN KEY (road_id) REFERENCES road_segments(road_id)
);

CREATE TABLE IF NOT EXISTS road_feature_dataset (
    road_id INTEGER,
    analysis_date TEXT,
    past_sinkhole_count INTEGER,
    gpr_detected_count INTEGER,
    facility_aging_score REAL,
    rainfall_score REAL,
    groundwater_score REAL,
    environment_score REAL,
    construction_score REAL,
    PRIMARY KEY (road_id, analysis_date),
    FOREIGN KEY (road_id) REFERENCES road_segments(road_id)
);

CREATE TABLE IF NOT EXISTS road_risk_analysis_result (
    id INTEGER PRIMARY KEY,
    road_id INTEGER,
    analysis_date TEXT,
    total_risk_score REAL,
    risk_level TEXT,
    priority_rank INTEGER,
    FOREIGN KEY (road_id) REFERENCES road_segments(road_id)
);

CREATE TABLE IF NOT EXISTS weather_data (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    record_date TEXT,
    rainfall REAL,
    temperature REAL,
    humidity REAL,
    source_name TEXT,
    source_record_id TEXT,
    station_id TEXT,
    station_name TEXT,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE IF NOT EXISTS groundwater_data (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    record_date TEXT,
    groundwater_level REAL,
    variation REAL,
    source_name TEXT,
    source_record_id TEXT,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE IF NOT EXISTS environment_features (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    building_density REAL,
    road_density REAL,
    land_use_type TEXT,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE IF NOT EXISTS construction_events (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    construction_type TEXT,
    start_date TEXT,
    scale_score REAL,
    source_name TEXT,
    source_record_id TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

CREATE TABLE IF NOT EXISTS molit_ground_boreholes (
    id INTEGER PRIMARY KEY,
    borehole_code TEXT,
    project_name TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    raw_x REAL,
    raw_y REAL,
    coordinate_crs TEXT,
    elevation_m REAL,
    total_depth_m REAL,
    groundwater_level_m REAL,
    borehole_method TEXT,
    borehole_type TEXT,
    source_name TEXT,
    source_record_id TEXT,
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    raw_json TEXT,
    UNIQUE(source_file, source_row_number)
);

CREATE TABLE IF NOT EXISTS molit_ground_layers (
    id INTEGER PRIMARY KEY,
    borehole_code TEXT,
    project_name TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    layer_sequence INTEGER,
    top_depth_m REAL,
    bottom_depth_m REAL,
    thickness_m REAL,
    layer_name TEXT,
    layer_color TEXT,
    layer_description TEXT,
    soil_class TEXT,
    n_value REAL,
    source_name TEXT,
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    raw_json TEXT,
    UNIQUE(source_file, source_row_number)
);

CREATE TABLE IF NOT EXISTS feature_dataset (
    region_id INTEGER,
    analysis_date TEXT,
    past_sinkhole_count INTEGER,
    gpr_detected_count INTEGER,
    facility_aging_score REAL,
    rainfall_score REAL,
    groundwater_score REAL,
    environment_score REAL,
    construction_score REAL,
    PRIMARY KEY (region_id, analysis_date)
);

CREATE TABLE IF NOT EXISTS risk_analysis_result (
    id INTEGER PRIMARY KEY,
    region_id INTEGER,
    analysis_date TEXT,
    total_risk_score REAL,
    risk_level TEXT,
    priority_rank INTEGER,
    FOREIGN KEY (region_id) REFERENCES regions(region_id)
);

-- 운영 가이드(10)에서 언급한 캐싱(선택)
CREATE TABLE IF NOT EXISTS ai_report (
    region_id INTEGER,
    analysis_date TEXT,
    report_text TEXT,
    created_at TEXT,
    PRIMARY KEY (region_id, analysis_date)
);

CREATE INDEX IF NOT EXISTS idx_sinkhole_history_region ON sinkhole_history(region_id);
CREATE INDEX IF NOT EXISTS idx_road_sinkhole_history_road ON road_sinkhole_history(road_id);
CREATE INDEX IF NOT EXISTS idx_weather_date ON weather_data(record_date);
CREATE INDEX IF NOT EXISTS idx_risk_region_date ON risk_analysis_result(region_id, analysis_date);
CREATE INDEX IF NOT EXISTS idx_risk_road_date ON road_risk_analysis_result(road_id, analysis_date);
CREATE INDEX IF NOT EXISTS idx_raw_source_records_source ON raw_source_records(source_name, fetched_at);
CREATE INDEX IF NOT EXISTS idx_public_data_collection_runs_started ON public_data_collection_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_molit_ground_boreholes_code ON molit_ground_boreholes(borehole_code);
CREATE INDEX IF NOT EXISTS idx_molit_ground_boreholes_coord ON molit_ground_boreholes(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_molit_ground_boreholes_source_record ON molit_ground_boreholes(source_name, source_record_id);
CREATE INDEX IF NOT EXISTS idx_molit_ground_layers_code ON molit_ground_layers(borehole_code);
CREATE INDEX IF NOT EXISTS idx_molit_ground_layers_coord ON molit_ground_layers(latitude, longitude);
