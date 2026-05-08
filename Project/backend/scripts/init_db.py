from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/init_db.py` from backend/ without PYTHONPATH tweaks.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import settings
from app.db.core import connect
from app.db.migrate import apply_schema


def main() -> None:
    conn = connect(settings.db_path)
    try:
        apply_schema(conn, settings.schema_path)
        conn.commit()
    finally:
        conn.close()
    print(f"OK: db schema initialized at {settings.db_path}; no demo data was inserted")


if __name__ == "__main__":
    main()
