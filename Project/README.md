# Project

실제 애플리케이션 작업공간입니다.

## 구조

- `backend/`: FastAPI API, SQLite 스키마, 분석/리포트/공공데이터 수집 로직
- `backend/app/static/`: 정적 대시보드 UI
- `backend/db/schema.sql`: 운영 DB 스키마
- `backend/scripts/`: DB 초기화, 공공데이터 수동 수집, 스모크 체크

상위 `md/` 폴더는 기획/설계 문서 보관용이며, 런타임에는 필요하지 않습니다.

## 실행

루트 폴더에서:

```powershell
.\Run_Sinkhole.cmd
```

또는 백엔드 폴더에서:

```powershell
cd .\Project\backend
python .\scripts\init_db.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```
