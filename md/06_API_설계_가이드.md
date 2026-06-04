# 06_API_설계_가이드

## 1. 목적

이 문서는 FastAPI 백엔드의 API 구조, 응답 형식, 주요 엔드포인트, 확장 기준을 설명한다. 현재 API는 `Project/backend/app/routes`에 기능별 라우터로 분리되어 있다.

## 2. 기본 구조

앱 진입점:

```text
Project/backend/app/main.py
```

공통 DB 의존성:

```text
Project/backend/app/main_deps.py
```

공통 응답 helper:

```text
Project/backend/app/utils/response.py
```

라우터 등록은 `create_app()`에서 수행한다.

## 3. 응답 형식

성공 응답:

```json
{
  "success": true,
  "message": "OK",
  "data": {}
}
```

실패 응답:

```json
{
  "success": false,
  "message": "데이터를 찾을 수 없습니다.",
  "error_code": "NOT_FOUND"
}
```

UI의 `api()` helper는 `success=false`를 오류로 처리한다.

## 4. 인증

운영 환경에서는 Basic Auth를 사용할 수 있다.

환경 변수:

```env
SINKHOLE_ENABLE_BASIC_AUTH=1
SINKHOLE_BASIC_AUTH_USERNAME=...
SINKHOLE_BASIC_AUTH_PASSWORD=...
```

개발 환경에서는 기본 비활성화다.

## 5. 주요 API 목록

### 5.1 상태/설정

```text
GET /api/health
GET /api/app-config
GET /api/summary
```

`/api/app-config`는 Google Maps 노출 설정, 기본 모드, 시나리오 중심 위치를 반환한다. API 키는 `SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY=1`일 때만 반환한다.

### 5.2 분석 대상

```text
GET /api/regions
GET /api/region/{region_id}
GET /api/roads
GET /api/road/{road_id}
```

`/api/roads`는 `region_id` query를 받을 수 있다. 도로 데이터가 없으면 빈 배열을 반환한다.

### 5.3 위험 분석

```text
POST /api/analyze-risk
POST /api/analyze-road-risk
GET  /api/analysis/{region_id}
GET  /api/top-risk-regions
GET  /api/top-risk-roads
```

지역 분석 request:

```json
{
  "region_id": 900002,
  "analysis_date": "2026-05-20",
  "client_local_datetime": "2026-05-20T12:44:00",
  "client_timezone": "Asia/Seoul",
  "client_utc_offset_minutes": 540
}
```

분석 응답은 다음을 포함한다.

- `region` 또는 `road`
- `analysis`
- `features`
- `breakdown`
- `reason_cards`

### 5.4 지도/지오코딩

```text
GET /api/geocode/search
GET /api/geocode/reverse
GET /api/map/risk-layer
GET /api/map/gpr-layer
GET /api/map/hotspots
```

검색은 로컬 분석 대상과 주소/좌표 fallback을 조합한다.

### 5.5 차트

```text
GET /api/charts/risk-distribution
GET /api/charts/risk-trend
GET /api/charts/factor-importance
GET /api/charts/top-priority
GET /api/charts/sinkhole-cause-distribution
GET /api/charts/sinkhole-occurrence-trend
```

지역별 데이터가 부족한 경우 일부 차트는 전체 지역 fallback을 제공할 수 있다.

### 5.6 비교 분석

```text
POST /api/compare-regions
```

request:

```json
{
  "region_ids": [900001, 900002],
  "analysis_date": "2026-05-20"
}
```

### 5.7 What-If 시뮬레이션

```text
POST /api/simulate-risk
```

request는 `WhatIfRequest` 모델을 따른다.

주요 필드:

- `scenario_preset`
- `forecast_horizon_hours`
- `extra_rainfall_mm`
- `groundwater_delta_m`
- `is_major_construction`
- `excavation_depth_m`
- `construction_distance_m`
- `gpr_anomaly_count`
- `facility_aging_delta`
- `past_sinkhole_delta_count`
- `environment_delta_score`
- `mitigation_*`
- `target_region_id`

### 5.8 AI Chat

```text
POST /api/ai-chat
```

request:

```json
{
  "message": "현재 가장 위험한 지역은 어디야?",
  "history": [
    {"role": "user", "content": "..."}
  ]
}
```

Gemini API 키가 없거나 로컬 검증 질문인 경우 규칙 기반 로컬 답변을 생성한다.

### 5.9 리포트/PDF

```text
POST /api/generate-report
GET  /api/report/{region_id}
GET  /api/reports
GET  /api/reports/files/{file_name}
POST /api/reports/delete
```

PDF 파일은 `SINKHOLE_REPORTS_DIR` 또는 기본 `Project/backend/data/reports`에 저장된다.

### 5.10 모니터링 지점

```text
GET    /api/monitoring-points
POST   /api/monitoring-points
POST   /api/monitoring-points/refresh
DELETE /api/monitoring-points/{point_id}
```

최대 개수는 `SINKHOLE_MONITORING_POINTS_MAX_COUNT`로 제어한다.

### 5.11 공공데이터

```text
GET  /api/public-data/status
POST /api/public-data/refresh
GET  /api/public-data/seoul/status
POST /api/public-data/seoul/import
GET  /api/public-data/local-construction/status
POST /api/public-data/local-construction/import
GET  /api/public-data/ground-layers/status
```

데이터 갱신 API는 실행 시간이 길 수 있으므로 UI에서는 상태 표시와 timeout을 고려한다.

### 5.12 현장/상업 위치 분석

```text
POST /api/commercial/analyze
POST /api/commercial/report
```

주소, 장소명, 좌표 기반으로 주변 분석 지점과 날씨/위험 근거를 조합한다.

## 6. API 추가 기준

새 API를 추가할 때는 다음을 지킨다.

- 라우터 파일을 기능 단위로 유지한다.
- request body는 `app/models/schemas.py`에 Pydantic 모델로 정의한다.
- DB 연결은 `Depends(get_db)`를 사용한다.
- 응답은 `ok()` 또는 `fail()`을 사용한다.
- 날짜 입력은 `resolve_analysis_date()` 기준을 따른다.
- API 키나 민감 정보는 응답에 노출하지 않는다.
- UI에서 빈 배열과 null 값을 안전하게 처리할 수 있도록 기본값을 제공한다.

## 7. 오류 처리 기준

- 대상이 없으면 `NOT_FOUND`
- 입력이 잘못되면 Pydantic validation 사용
- 외부 API 실패는 수집 상태에 오류로 기록하되 서비스 전체 장애로 전파하지 않는다.
- 파일 접근 오류는 메시지를 짧게 정리해 응답한다.
- API 키는 오류 메시지에서 redaction한다.

## 8. 문서 확인

서버 실행 후 Swagger 문서:

```text
http://127.0.0.1:5000/docs
```

OpenAPI JSON:

```text
http://127.0.0.1:5000/openapi.json
```
