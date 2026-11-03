"""Small reusable helpers for named-account acquisition verification."""
from __future__ import annotations

from datetime import datetime
import sqlite3


TWITTER_TIME = "%a %b %d %H:%M:%S %z %Y"


class Verification:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, passed: bool, detail: str) -> None:
        symbol = "✓" if passed else "✗"
        print(f"{symbol} {label}: {detail}")
        if not passed:
            self.failures += 1


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, TWITTER_TIME)
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


def count_if_present(
    conn: sqlite3.Connection,
    tables: set[str],
    table: str,
    sql: str,
    account_id: str,
) -> int:
    if table not in tables:
        return 0
    return int(conn.execute(sql, (account_id,)).fetchone()[0])
