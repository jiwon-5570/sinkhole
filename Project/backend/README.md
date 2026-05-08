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
- `POST /api/analyze-risk`
- `POST /api/chat`
- `POST /api/generate-report`

## 운영 원칙

- 데모 seed 데이터는 사용하지 않습니다.
- `scripts/init_db.py`는 스키마만 적용합니다.
- 공공데이터 API 키와 AI 키는 `.env`에만 보관합니다.
- DB, PDF, 로그, 임시 파일은 Git에 포함하지 않습니다.
