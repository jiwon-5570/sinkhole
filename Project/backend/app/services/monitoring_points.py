from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3
from typing import Any

from app.config.settings import settings
from app.db.core import query_all, query_one
from app.services.commercial import build_commercial_analysis


def ensure_monitoring_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitoring_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            address TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            risk_score REAL,
            risk_level TEXT,
            last_checked_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def active_monitoring_count(conn: sqlite3.Connection) -> int:
    ensure_monitoring_table(conn)
    row = query_one(conn, "SELECT COUNT(*) AS count FROM monitoring_points WHERE active = 1")
    return int((row or {}).get("count") or 0)


def recent_monitoring_detection_count(conn: sqlite3.Connection, *, hours: int = 24) -> int:
    ensure_monitoring_table(conn)
    interval = f"-{max(1, int(hours))} hours"
    row = query_one(
        conn,
        """
        SELECT COUNT(*) AS count
        FROM monitoring_points
        WHERE active = 1
          AND last_checked_at IS NOT NULL
          AND risk_score IS NOT NULL
          AND datetime(REPLACE(last_checked_at, 'T', ' ')) >= datetime('now', 'localtime', ?)
        """,
        (interval,),
    )
    return int((row or {}).get("count") or 0)


def list_monitoring_points(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_monitoring_table(conn)
    return query_all(
        conn,
        """
        SELECT
            id, name, address, latitude, longitude, active,
            risk_score, risk_level, last_checked_at, last_error,
            created_at, updated_at
        FROM monitoring_points
        WHERE active = 1
        ORDER BY created_at ASC, id ASC
        """,
    )


def add_monitoring_point(
    conn: sqlite3.Connection,
    *,
    name: str | None,
    address: str | None,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    ensure_monitoring_table(conn)
    count = active_monitoring_count(conn)
    max_count = max(1, int(settings.monitoring_points_max_count))
    if count >= max_count:
        raise ValueError(f"모니터링 지점은 최대 {max_count}개까지 등록할 수 있습니다.")

    label = (name or address or "모니터링 지점").strip()
    addr = (address or label).strip()
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO monitoring_points(
            name, address, latitude, longitude, active, created_at, updated_at
        )
        VALUES(?, ?, ?, ?, 1, ?, ?)
        """,
        (label, addr, float(latitude), float(longitude), now, now),
    )
    point_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    refresh_monitoring_point(conn, point_id, force=True)
    row = query_one(conn, "SELECT * FROM monitoring_points WHERE id = ?", (point_id,))
    return dict(row or {})


def deactivate_monitoring_point(conn: sqlite3.Connection, point_id: int) -> bool:
    ensure_monitoring_table(conn)
    now = datetime.now().isoformat(timespec="seconds")
    cur = conn.execute(
        """
        UPDATE monitoring_points
        SET active = 0, updated_at = ?
        WHERE id = ? AND active = 1
        """,
        (now, int(point_id)),
    )
    return cur.rowcount > 0


def _needs_refresh(row: dict[str, Any], *, force: bool) -> bool:
    if force:
        return True
    checked = row.get("last_checked_at")
    if not checked:
        return True
    try:
        checked_at = datetime.fromisoformat(str(checked))
    except ValueError:
        return True
    interval = max(60, int(settings.monitoring_points_refresh_seconds))
    return datetime.now() - checked_at >= timedelta(seconds=interval)


def refresh_monitoring_point(conn: sqlite3.Connection, point_id: int, *, force: bool = False) -> dict[str, Any] | None:
    ensure_monitoring_table(conn)
    row = query_one(conn, "SELECT * FROM monitoring_points WHERE id = ? AND active = 1", (int(point_id),))
    if not row:
        return None
    if not _needs_refresh(row, force=force):
        return dict(row)

    now = datetime.now().isoformat(timespec="seconds")
    try:
        payload = build_commercial_analysis(
            row.get("address") or row.get("name"),
            float(row["latitude"]),
            float(row["longitude"]),
        )
        analysis = payload.get("analysis") or {}
        conn.execute(
            """
            UPDATE monitoring_points
            SET risk_score = ?, risk_level = ?, last_checked_at = ?,
                last_error = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                float(analysis.get("total_risk_score") or 0.0),
                str(analysis.get("risk_level") or ""),
                now,
                now,
                int(point_id),
            ),
        )
    except Exception as exc:
        conn.execute(
            """
            UPDATE monitoring_points
            SET last_error = ?, last_checked_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (str(exc)[:500], now, now, int(point_id)),
        )
    return query_one(conn, "SELECT * FROM monitoring_points WHERE id = ?", (int(point_id),))


def refresh_monitoring_points(conn: sqlite3.Connection, *, force: bool = False) -> list[dict[str, Any]]:
    rows = list_monitoring_points(conn)
    for row in rows:
        refresh_monitoring_point(conn, int(row["id"]), force=force)
    return list_monitoring_points(conn)
