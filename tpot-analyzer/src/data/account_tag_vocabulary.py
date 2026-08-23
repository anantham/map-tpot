"""Stable curator vocabulary derived from current and historical tag use."""
from __future__ import annotations

import sqlite3
from pathlib import Path


def list_distinct_vocabulary(*, db_path: Path, ego: str) -> list[str]:
    """Return one display spelling per tag key, preserving retracted concepts."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT tag_display, priority
            FROM (
                SELECT tag_display, 0 AS priority
                FROM account_tags WHERE ego = ?
                UNION ALL
                SELECT tag_display, 1 AS priority
                FROM account_tag_events WHERE ego = ?
                UNION ALL
                SELECT tag_display, 2 AS priority
                FROM tag_meta_notes WHERE ego = ?
            )
            ORDER BY priority ASC, tag_display COLLATE NOCASE ASC
            """,
            (ego, ego, ego),
        ).fetchall()

    vocabulary: list[str] = []
    seen: set[str] = set()
    for display, _priority in rows:
        key = str(display).casefold()
        if key in seen:
            continue
        seen.add(key)
        vocabulary.append(str(display))
    return vocabulary
