# Backend

FastAPI 기반 백엔드입니다.

## 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\init_db.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```

## 주요 엔드포인트

- `GET /api/health`
- `GET /api/summary`
- `POST /api/public-data/refresh`
- `GET /api/public-data/ground-layers/status`
- `POST /api/analyze-risk`
- `POST /api/chat`
- `POST /api/generate-report`

## 국토교통부 지반정보 파일데이터

공공데이터포털에서 내려받은 파일은 아래 위치에 둡니다.

```text
data/raw/public/molit_ground_layers/
```

파일명 예시:

```text
국토교통부_지반정보_지층정보_20230831.csv
```

시추공 데이터는 공공데이터포털에서 승인된 OpenAPI를 `PUBLIC_DATA_API_KEY`로 자동 수집합니다. 직접 파일을 넣지 않아도 됩니다.

기본 API:

```text
https://api.odcloud.kr/api/15069365/v1/uddi:e3857d80-b97e-4693-84d5-f2b4f37959f0
```

수집:

```powershell
POST /api/public-data/refresh
```

좌표 변환 기준은 기본 `EPSG:5186`입니다. 다른 좌표계로 확인되면 `.env`에서 변경합니다.

```env
SINKHOLE_MOLIT_BOREHOLE_COORD_CRS=EPSG:5186
SINKHOLE_MOLIT_BOREHOLE_ROWS_PER_PAGE=1000
SINKHOLE_MOLIT_BOREHOLE_MAX_PAGES=500
SINKHOLE_MOLIT_BOREHOLE_REFRESH_DAYS=30
SINKHOLE_MOLIT_BOREHOLE_MIN_CACHED_ROWS=300000
```

아래 폴더는 API 장애 시의 보조 수동 적재용입니다.

```text
data/raw/public/molit_boreholes/
```

적재:

```powershell
python .\scripts\import_molit_ground_data.py
```

적재 후 위치 주변 지층 데이터가 있으면 분석 점수의 `환경` 요인에 지반 보정값으로 반영됩니다.

## 서울시 도로굴착 공사 파일 적재

서울시 도로굴착 공사 정보 파일은 아래 폴더에 넣습니다.

```text
data/raw/public/seoul_road_excavation/
```

지원 형식은 `.csv`, `.tsv`, `.txt`, `.xlsx`, `.xls`입니다. 서버는 기본 30초마다 이 폴더를 스캔하고,
새 파일 또는 수정된 파일을 발견하면 `construction_events`에 적재한 뒤 오늘 날짜 위험도 점수를 다시 계산합니다.

권장 컬럼은 다음과 같습니다.

- 공사명 또는 공사종류
- 도로명주소 또는 공사위치
- 시작일/착공일
- 종료일/준공일
- 굴착연장, 굴착깊이, 굴착폭, 굴착면적
- 위도/경도

수동 적재가 필요하면 다음 명령을 실행합니다.

```powershell
python .\scripts\import_seoul_road_excavation.py
```

적재된 파일 상태는 `/api/public-data/local-construction/status`에서 확인할 수 있습니다.

## 모니터링 지점

대시보드의 `모니터링 지점` 카드를 눌러 최대 10개 지점을 직접 등록할 수 있습니다.
등록된 지점은 DB의 `monitoring_points`에 저장되며, 해제하기 전까지 화면 접속 시 자동으로 위험도를 갱신합니다.

관련 설정:

```env
SINKHOLE_MONITORING_POINTS_MAX_COUNT=10
SINKHOLE_MONITORING_POINTS_REFRESH_SECONDS=900
```

관련 API:

- `GET /api/monitoring-points`
- `POST /api/monitoring-points`
- `POST /api/monitoring-points/refresh`
- `DELETE /api/monitoring-points/{point_id}`

## 운영 원칙

- 데모 seed 데이터는 사용하지 않습니다.
- `scripts/init_db.py`는 스키마만 적용합니다.
- 공공데이터 API 키와 AI 키는 `.env`에만 보관합니다.
- DB, PDF, 로그, 임시 파일은 Git에 포함하지 않습니다.
