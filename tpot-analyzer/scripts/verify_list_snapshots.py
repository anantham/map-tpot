#!/usr/bin/env python3
"""Verify that cached Twitter list snapshots align with stored member rows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

DB_PATH = Path("data/cache.db")
MAX_SAMPLE = 5


@dataclass
class SnapshotDiff:
    list_id: str
    recorded_count: int
    actual_count: int
    claimed_count: Optional[int]
    fetched_at: str


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _iter_snapshots(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    query = """
        SELECT
            l.list_id,
            COALESCE(l.member_count, 0) AS captured_count,
            l.claimed_member_total,
            l.fetched_at,
            COUNT(m.member_account_id) AS actual_count
        FROM shadow_list AS l
        LEFT JOIN shadow_list_member AS m
          ON l.list_id = m.list_id
        GROUP BY l.list_id, l.member_count, l.claimed_member_total, l.fetched_at
        ORDER BY datetime(l.fetched_at) DESC
    """
    return conn.execute(query)


def _find_differences(rows: Iterable[sqlite3.Row]) -> List[SnapshotDiff]:
    diffs: List[SnapshotDiff] = []
    for row in rows:
        recorded = row["captured_count"] or 0
        actual = row["actual_count"] or 0
        claimed = row["claimed_member_total"] if "claimed_member_total" in row.keys() else None
        if recorded != actual or (claimed is not None and actual != claimed):
            diffs.append(
                SnapshotDiff(
                    list_id=row["list_id"],
                    recorded_count=recorded,
                    actual_count=actual,
                    claimed_count=claimed,
                    fetched_at=row["fetched_at"],
                )
            )
    return diffs


def _print_status(ok: bool, title: str, details: List[str]) -> None:
    indicator = "✓" if ok else "✗"
    print(f"{indicator} {title}")
    for detail in details:
        print(f"   {detail}")


def main() -> None:
    if not DB_PATH.exists():
        _print_status(
            False,
            "list snapshot database missing",
            [f"Expected SQLite DB at {DB_PATH.resolve()}"],
        )
        print("   Next: Run enrichment at least once to create data/cache.db before rerunning.")
        return

    with _connect(DB_PATH) as conn:
        try:
            rows = list(_iter_snapshots(conn))
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "shadow_list" in message:
                _print_status(
                    False,
                    "list snapshot tables missing",
                    [
                        "shadow_list/shadow_list_member tables not found in cache.db.",
                        "Run enrichment with --center <list_id> once to initialise the schema.",
                    ],
                )
                print("   Next: after the first list scrape, rerun this verifier to confirm counts.")
                return
            if "claimed_member_total" in message or "followers_count" in message:
                _print_status(
                    False,
                    "list snapshot schema outdated",
                    [
                        "shadow_list table missing new columns (claimed_member_total/followers_count).",
                        "Run the latest enrichment script once to auto-migrate schema.",
                    ],
                )
                print("   Next: rerun this verifier after the migration completes.")
                return
            raise

    if not rows:
        _print_status(
            True,
            "no list snapshots recorded",
            ["No entries found in shadow_list; run enrichment with --center <list_id> to capture a snapshot."],
        )
        print("   Next: Re-run after scraping at least one list.")
        return

    diffs = _find_differences(rows)
    if not diffs:
        _print_status(
            True,
            "list snapshots",
            [
                "All cached list snapshots have matching member rows.",
                f"Lists inspected: {len(rows)}",
            ],
        )
        print("   Next: Re-run after future list refreshes to monitor integrity.")
        return

    sample = diffs[:MAX_SAMPLE]
    sample_lines = []
    for item in sample:
        claimed = f" claimed={item.claimed_count}" if item.claimed_count is not None else ""
        line = f"list_id={item.list_id} captured={item.recorded_count} actual_rows={item.actual_count}{claimed}"
        snapshot_info = f" (fetched_at={item.fetched_at})"
        sample_lines.append(line + snapshot_info)
    _print_status(
        False,
        "list snapshots",
        [
            f"{len(diffs)} list snapshots have mismatched member counts.",
            *sample_lines,
        ],
    )
    remaining = len(diffs) - len(sample)
    if remaining > 0:
        print(f"   …and {remaining} more.")
    print("   Next: Force-refresh affected lists with `scripts.enrich_shadow_graph --center <list_id> --force-refresh-list` to rebuild snapshots.")


if __name__ == "__main__":
    main()
