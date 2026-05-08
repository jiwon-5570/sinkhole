from __future__ import annotations

from pathlib import Path
import sqlite3


def apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)

