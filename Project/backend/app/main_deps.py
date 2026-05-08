from __future__ import annotations

import sqlite3

from app.config.settings import settings
from app.db.core import session


def get_db() -> sqlite3.Connection:
    with session(settings.db_path) as conn:
        yield conn

