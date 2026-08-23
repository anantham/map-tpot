from __future__ import annotations

import sqlite3

import pytest

from src.evaluation.seed_coverage import open_readonly_sqlite


def test_readonly_connection_pins_wal_snapshot_and_rejects_writes(tmp_path) -> None:
    path = tmp_path / "live.db"
    writer = sqlite3.connect(path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE evidence (value TEXT)")
    writer.execute("INSERT INTO evidence VALUES ('before-snapshot')")
    writer.commit()

    reader = open_readonly_sqlite(path)
    try:
        writer.execute("INSERT INTO evidence VALUES ('after-snapshot')")
        writer.commit()

        assert reader.execute("PRAGMA query_only").fetchone()[0] == 1
        assert reader.execute("SELECT value FROM evidence").fetchall() == [
            ("before-snapshot",)
        ]
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            reader.execute("INSERT INTO evidence VALUES ('forbidden')")
    finally:
        reader.close()
        writer.close()
