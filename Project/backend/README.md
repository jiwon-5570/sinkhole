# backend (Python)

## 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\scripts\init_db.py
python .\app\main.py
```

## DB

- 기본 DB: `backend/db/app.db` (SQLite)
- 스키마: `backend/db/schema.sql`

