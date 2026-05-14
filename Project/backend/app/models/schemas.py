from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRiskRequest(BaseModel):
    region_id: int = Field(..., ge=1)
    analysis_date: str | None = Field(default=None, description="YYYY-MM-DD; default=today")
    client_local_datetime: str | None = Field(default=None, description="Client local datetime (ISO), e.g. 2026-04-20T15:30:00")
    client_timezone: str | None = Field(default=None, description="IANA timezone, e.g. Asia/Seoul")
    client_utc_offset_minutes: int | None = Field(default=None, description="UTC offset minutes, e.g. 540")


class AnalyzeRoadRiskRequest(BaseModel):
    road_id: int = Field(..., ge=1)
    analysis_date: str | None = Field(default=None, description="YYYY-MM-DD; default=today")
    client_local_datetime: str | None = Field(default=None, description="Client local datetime (ISO), e.g. 2026-04-20T15:30:00")
    client_timezone: str | None = Field(default=None, description="IANA timezone, e.g. Asia/Seoul")
    client_utc_offset_minutes: int | None = Field(default=None, description="UTC offset minutes, e.g. 540")


class CompareRegionsRequest(BaseModel):
    region_ids: list[int] = Field(..., min_length=2, max_length=10)
    analysis_date: str | None = None
    client_local_datetime: str | None = None
    client_timezone: str | None = None
    client_utc_offset_minutes: int | None = None


class WhatIfRequest(BaseModel):
    scenario_preset: str = Field(default="custom", max_length=40)
    forecast_horizon_hours: int = Field(default=24, ge=1, le=168)
    extra_rainfall_mm: float = Field(default=0.0, ge=0.0, le=300.0)
    groundwater_delta_m: float = Field(default=0.0, ge=-10.0, le=10.0)
    is_major_construction: bool = False
    excavation_depth_m: float = Field(default=0.0, ge=0.0, le=80.0)
    construction_distance_m: float = Field(default=500.0, ge=0.0, le=5000.0)
    gpr_anomaly_count: int = Field(default=0, ge=0, le=30)
    facility_aging_delta: float = Field(default=0.0, ge=0.0, le=50.0)
    past_sinkhole_delta_count: int = Field(default=0, ge=0, le=10)
    environment_delta_score: float = Field(default=0.0, ge=0.0, le=10.0)
    target_region_id: int | None = Field(default=None, ge=1)


class GenerateReportRequest(BaseModel):
    region_id: int
    analysis_date: str | None = None
    language: str | None = Field(default="ko", description="Language of the report (e.g., 'ko', 'en')")
    client_local_datetime: str | None = Field(default=None, description="Client local datetime (ISO), e.g. 2026-04-20T15:30:00")
    client_timezone: str | None = Field(default=None, description="IANA timezone, e.g. Asia/Seoul")
    client_utc_offset_minutes: int | None = Field(default=None, description="UTC offset minutes, e.g. 540")


class ChatMessage(BaseModel):
    role: str = Field(default="user", max_length=20)
    content: str = Field(..., max_length=2000)


class AiChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class CommercialAnalyzeRequest(BaseModel):
    location_name: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    client_local_datetime: str | None = None
    client_timezone: str | None = None
    client_utc_offset_minutes: int | None = None


class CommercialReportRequest(BaseModel):
    location_name: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    language: str | None = Field(default="ko", description="Language of the report")
    client_local_datetime: str | None = None
    client_timezone: str | None = None
    client_utc_offset_minutes: int | None = None


class MonitoringPointRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class ReportFilesRequest(BaseModel):
    file_names: list[str] = Field(..., min_length=1, max_length=200)
