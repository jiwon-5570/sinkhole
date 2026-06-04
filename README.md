# Sinkhole Risk Dashboard

공공데이터와 로컬 원본 파일을 기반으로 서울/수도권 지반침하 위험도를 분석하는 FastAPI 대시보드입니다. 지역별 위험 점수, 원인별 기여도, 지도 기반 위치 확인, What-If 시뮬레이션, AI 채팅, PDF 리포트 생성을 제공합니다.

## 주요 기능

- 지역/도로 단위 지반침하 위험도 분석
- 공공데이터 기반 과거 사고, 시설물, 강우, 지하수, 지층, 공사 영향 반영
- 서울시 도로굴착 공사 파일 자동 감지 및 위험도 재계산
- Google 지도 또는 자체 SVG 지도 기반 위치 확인
- What-If 시뮬레이션으로 강우, 굴착, GPR 이상 신호, 관리 조치 영향 비교
- Gemini API 기반 AI 채팅 및 분석 리포트 생성
- PDF 보고서 생성, 목록 조회, 열기, 다운로드, 삭제
- 최대 10개 모니터링 지점 등록 및 위험도 갱신

## 프로젝트 구조

```text
.
├─ Project/
│  └─ backend/
│     ├─ app/
│     │  ├─ main.py                 # FastAPI 앱 진입점
│     │  ├─ routes/                 # API 라우터
│     │  ├─ services/               # 위험도 계산, 데이터 수집, 리포트, 시뮬레이션
│     │  ├─ config/settings.py      # 환경 변수 설정
│     │  └─ static/                 # 대시보드 HTML/CSS/JavaScript
│     ├─ db/schema.sql              # SQLite 스키마
│     ├─ scripts/                   # 초기화, 데이터 적재, 점검 스크립트
│     └─ data/
│        ├─ raw/public/             # 공공데이터 원본 파일 위치
│        └─ reports/                # 생성 PDF 저장 위치
├─ md/                              # 개발/설계 문서
├─ Install_Sinkhole.cmd             # Windows 설치 실행 파일
└─ Run_Sinkhole.cmd                 # Windows 실행 파일
```

## 데이터 흐름

1. 서버 시작 시 `Project/backend/db/schema.sql`을 적용합니다.
2. `molit_ground_layers`, `molit_ground_boreholes` 등 지반/시추 데이터를 DB에 적재합니다.
3. 서울시 도로굴착 공사 파일을 `construction_events`에 반영합니다.
4. `features.py`가 과거 침하, GPR, 시설물, 강우, 지하수, 환경, 공사 영향 feature를 구성합니다.
5. `risk_scoring.py`가 feature를 0~100점 위험 점수와 등급으로 변환합니다.
6. `analysis.py`가 분석 결과를 저장하고 우선순위를 재계산합니다.
7. UI는 `/api/*` 엔드포인트를 호출해 지도, 차트, 리포트, AI 채팅 화면을 갱신합니다.

위험 등급 기준:

- `낮음`: 30점 미만
- `보통`: 30점 이상 60점 미만
- `높음`: 60점 이상 80점 미만
- `매우 높음`: 80점 이상

## 빠른 실행

Windows에서 처음 실행할 때:

```powershell
.\Install_Sinkhole.cmd
```

설치 후 실행:

```powershell
.\Run_Sinkhole.cmd
```

기본 접속 주소:

```text
http://127.0.0.1:5000
```

## 수동 실행

```powershell
cd .\Project\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\init_db.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```

## 로컬 공공데이터 파일

### 서울시 도로굴착 공사 정보

도로굴착 공사 원본 파일은 아래 폴더에 둡니다.

```text
Project/backend/data/raw/public/seoul_road_excavation/
```

지원 형식:

- `.csv`
- `.tsv`
- `.txt`
- `.xlsx`
- `.xls`

서버는 기본 30초마다 이 폴더를 확인합니다. 파일이 추가, 수정, 삭제되면 `construction_events`와 `road_construction_events`를 갱신하고 feature 캐시를 비운 뒤 오늘 날짜 기준 위험도를 다시 계산합니다.

수동 적재:

```powershell
cd .\Project\backend
python .\scripts\import_seoul_road_excavation.py
```

상태 확인 API:

```text
GET /api/public-data/local-construction/status
POST /api/public-data/local-construction/import
```

### 국토교통부 지반/시추 데이터

지층 CSV 위치:

```text
Project/backend/data/raw/public/molit_ground_layers/
```

시추공 파일 보조 위치:

```text
Project/backend/data/raw/public/molit_boreholes/
```

수동 적재:

```powershell
cd .\Project\backend
python .\scripts\import_molit_ground_data.py
```

상태 확인 API:

```text
GET /api/public-data/ground-layers/status
```

## 환경 변수

실제 키는 `Project/backend/.env`에 저장합니다. `.env` 파일은 Git에 포함하지 않습니다.

```env
PUBLIC_DATA_API_KEY=your_public_data_key
SEOUL_OPEN_DATA_API_KEY=your_seoul_open_data_key
SAFEMAP_API_KEY=your_safemap_key
GEMINI_API_KEY=your_gemini_key
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY=1
SINKHOLE_SEED_DEMO=0
```

주요 설정:

- `SINKHOLE_PORT`: 서버 포트, 기본 `5000`
- `SINKHOLE_DB_PATH`: SQLite DB 경로
- `SINKHOLE_ANALYZE_ON_START`: 시작 시 분석 실행 여부
- `SINKHOLE_PUBLIC_DATA_AUTO_COLLECT`: 공공데이터 자동 수집 여부
- `SINKHOLE_LOCAL_CONSTRUCTION_FILE_IMPORT_ENABLED`: 로컬 도로굴착 파일 자동 적재 여부
- `SINKHOLE_LOCAL_CONSTRUCTION_FILE_IMPORT_INTERVAL_SECONDS`: 로컬 파일 확인 주기
- `SINKHOLE_MONITORING_POINTS_MAX_COUNT`: 모니터링 지점 최대 개수, 기본 `10`

## 주요 API

```text
GET  /api/health
GET  /api/summary
GET  /api/regions
GET  /api/roads
POST /api/analyze-risk
POST /api/analyze-road-risk
GET  /api/top-risk-regions
GET  /api/top-risk-roads
POST /api/simulate-risk
POST /api/ai-chat
POST /api/generate-report
GET  /api/reports
POST /api/reports/delete
GET  /api/monitoring-points
POST /api/monitoring-points
POST /api/monitoring-points/refresh
```

개발 중 API 문서는 서버 실행 후 아래 주소에서 확인합니다.

```text
http://127.0.0.1:5000/docs
```

## 운영 원칙

- 데모 seed 데이터는 사용하지 않습니다. `SINKHOLE_SEED_DEMO=1`이면 서버 시작이 중단됩니다.
- 분석 결과는 실제 DB와 공공데이터/로컬 원본 파일을 기준으로 생성됩니다.
- SQLite DB, API 키, 로그, PDF 결과물, 임시 파일은 운영 산출물이며 Git 관리 대상이 아닙니다.
- 공공데이터 API가 실패해도 기존 DB에 적재된 마지막으로 불러왔던 공공데이터와 로컬 파일을 기준으로 대시보드는 동작합니다.

## 점검 명령

핵심 파이썬 파일 문법 확인:

```powershell
cd .\Project\backend
python -B -m py_compile app\main.py app\config\settings.py app\routes\analysis.py app\services\features.py app\services\risk_scoring.py
```

스모크 체크:

```powershell
cd .\Project\backend
python .\scripts\smoke_check.py
```
