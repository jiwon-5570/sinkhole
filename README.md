# Sinkhole Risk Dashboard

공공데이터 기반 지반침하 위험도 분석 대시보드입니다. FastAPI 백엔드와 정적 HTML/CSS/JavaScript UI로 구성되어 있으며, 지역별 위험 점수, 기여 요인, 지도, AI 리포트, PDF 보고서를 제공합니다.

## 주요 기능

- 진주권 분석 지점 위험도 산정
- Google Maps 기반 위치 선택 및 지도 표시
- 공공데이터포털 API 자동 수집
- 위험 기여 요인 분해
- Gemini 기반 AI 채팅/리포트 생성
- PDF 보고서 생성 및 다운로드

## 실제 데이터 원칙

운영 기준에서는 임의 데모 데이터가 분석 점수에 섞이지 않도록 구성했습니다. DB 초기화는 스키마만 적용하며, 분석 데이터는 승인된 공공데이터 API와 사용자가 입력한 실제 데이터에서만 생성합니다.

현재 연결된 공공데이터 소스:

- KALIS 공공시설물 안전관리/점검진단
- MOLIT 지하안전정보
- MOLIT 지반침하 사고 이력
- MOLIT 지반정보: 지층정보 CSV 수동 적재, 시추공 OpenAPI 자동 수집
- KMA ASOS 시간 강우
- MOLIT 건축HUB 건축 인허가

## 파일데이터 적재

공공데이터포털의 `국토교통부_지반정보_지층정보`처럼 CSV로 제공되는 파일데이터는 API 자동 호출 대상이 아니라 로컬 원본 파일을 DB에 적재해서 사용합니다.

지층정보 CSV 위치:

```text
Project/backend/data/raw/public/molit_ground_layers/
```

시추공 데이터는 승인된 OpenAPI를 `PUBLIC_DATA_API_KEY`로 자동 수집합니다. 별도 파일을 직접 넣지 않아도 됩니다.

기본 API:

```text
https://api.odcloud.kr/api/15069365/v1/uddi:e3857d80-b97e-4693-84d5-f2b4f37959f0
```

좌표 변환 기준은 기본 `EPSG:5181`입니다. 필요하면 `.env`에서 `SINKHOLE_MOLIT_BOREHOLE_COORD_CRS`로 바꿀 수 있습니다.

시추공 CSV 위치는 API 장애 시의 보조 수동 적재용입니다.

```text
Project/backend/data/raw/public/molit_boreholes/
```

적재 명령:

```powershell
cd .\Project\backend
python .\scripts\import_molit_ground_data.py
```

API 수집은 대시보드 시작/주기 수집 또는 아래 엔드포인트로 실행됩니다.

```text
POST /api/public-data/refresh
```

## 빠른 실행

Windows에서 처음 설치:

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

## 환경 변수

실제 키는 `Project/backend/.env`에만 둡니다. 이 파일은 Git에 포함하지 않습니다.

```env
PUBLIC_DATA_API_KEY=your_public_data_key
GEMINI_API_KEY=your_gemini_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY=1
SINKHOLE_SEED_DEMO=0
```

## 정리 기준

이 저장소는 실행에 필요한 코드, 스키마, 설치/실행 스크립트, 운영 문서만 포함합니다. 다음 항목은 Git에서 제외합니다.

- `.env`, API 키
- SQLite DB 파일
- 가상환경
- 브라우저 테스트 프로필
- 로그, 임시 파일
- 생성된 PDF 보고서
