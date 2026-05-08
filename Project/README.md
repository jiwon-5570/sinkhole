# sinkhole 프로젝트 (개발 시작)

`project/`는 `md/` 가이드(10개)를 기반으로 만든 실제 개발 작업공간이다.

## 구조

- `backend/`: Python 백엔드(API/DB/분석/리포트)
- `docs/`: 원본 가이드 복사본 + 파생 스펙
- `frontend/`: (추후) React UI 작업공간

## 빠른 시작 (Backend)

```powershell
cd .\project\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# DB 초기화 + 더미 데이터 시드
python .\scripts\init_db.py

# 서버 실행 (FastAPI)
python .\app\main.py
```

기본 주소:
- `http://localhost:5000`
- `GET http://localhost:5000/api/health`

