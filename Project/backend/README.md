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

시추공 좌표 파일도 승인받았다면 아래 위치에 함께 둡니다.

```text
data/raw/public/molit_boreholes/
```

적재:

```powershell
python .\scripts\import_molit_ground_data.py
```

적재 후 위치 주변 지층 데이터가 있으면 분석 점수의 `환경` 요인에 지반 보정값으로 반영됩니다.

## 운영 원칙

- 데모 seed 데이터는 사용하지 않습니다.
- `scripts/init_db.py`는 스키마만 적용합니다.
- 공공데이터 API 키와 AI 키는 `.env`에만 보관합니다.
- DB, PDF, 로그, 임시 파일은 Git에 포함하지 않습니다.
