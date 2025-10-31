#!/usr/bin/env python3
"""Verify that small-account profile totals align with captured edges."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

DB_PATH = Path("data/cache.db")
SMALL_THRESHOLD = 13
MAX_SAMPLE = 5


@dataclass
class Shortfall:
    seed_account_id: str
    seed_username: str
    run_at: str
    claimed_total: int
    captured: int
    list_type: str


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _latest_metrics(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    query = """
        WITH ranked AS (
            SELECT
                seed_account_id,
                seed_username,
                run_at,
                following_captured,
                followers_captured,
                ROW_NUMBER() OVER (
                    PARTITION BY seed_account_id
                    ORDER BY run_at DESC
                ) AS rn
            FROM scrape_run_metrics
            WHERE skipped = 0
        )
        SELECT
            r.seed_account_id,
            r.seed_username,
            r.run_at,
            r.following_captured,
            r.followers_captured,
            sa.following_count,
            sa.followers_count
        FROM ranked r
        LEFT JOIN shadow_account sa
          ON sa.account_id = r.seed_account_id
        WHERE r.rn = 1
    """
    return conn.execute(query)


def _detect_shortfalls(rows: Iterable[sqlite3.Row]) -> List[Shortfall]:
    findings: List[Shortfall] = []
    for row in rows:
        username = row["seed_username"] or "?"
        account_id = row["seed_account_id"]
        run_at = row["run_at"]

        following_total = row["following_count"]
        following_captured = row["following_captured"]
        if (
            following_total is not None
            and following_total <= SMALL_THRESHOLD
            and following_total >= 0
        ):
            if following_captured is None or following_captured < following_total:
                findings.append(
                    Shortfall(
                        seed_account_id=account_id,
                        seed_username=username,
                        run_at=run_at,
                        claimed_total=following_total,
                        captured=following_captured or 0,
                        list_type="following",
                    )
                )

        followers_total = row["followers_count"]
        followers_captured = row["followers_captured"]
        if (
            followers_total is not None
            and followers_total <= SMALL_THRESHOLD
            and followers_total >= 0
        ):
            if followers_captured is None or followers_captured < followers_total:
                findings.append(
                    Shortfall(
                        seed_account_id=account_id,
                        seed_username=username,
                        run_at=run_at,
                        claimed_total=followers_total,
                        captured=followers_captured or 0,
                        list_type="followers",
                    )
                )
    return findings


def _print_status(ok: bool, title: str, details: List[str]) -> None:
    indicator = "✓" if ok else "✗"
    print(f"{indicator} {title}")
    for detail in details:
        print(f"   {detail}")


def main() -> None:
    if not DB_PATH.exists():
        _print_status(
            False,
            "cache database not found",
            [f"Expected SQLite DB at {DB_PATH.resolve()}"],
        )
        print("   Next: run an enrichment cycle to populate the cache before rerunning.")
        return

    with _connect(DB_PATH) as conn:
        rows = list(_latest_metrics(conn))

    if not rows:
        _print_status(
            True,
            "no scrape metrics available",
            ["Nothing to check yet — run enrichment to create baseline metrics."],
        )
        print("   Next: rerun this script after enrichment produces scrape_run_metrics rows.")
        return

    shortfalls = _detect_shortfalls(rows)
    if not shortfalls:
        _print_status(
            True,
            "small-account coverage",
            [
                "All seeds with profile totals ≤ 13 show captured counts meeting or exceeding the totals.",
                f"Rows inspected: {len(rows)}",
            ],
        )
        print("   Next: rerun periodically after enrichment batches to monitor for regressions.")
        return

    samples = shortfalls[:MAX_SAMPLE]
    sample_lines = [
        f"@{item.seed_username} ({item.list_type}) captured {item.captured}/{item.claimed_total} — run_at={item.run_at} id={item.seed_account_id}"
        for item in samples
    ]
    _print_status(
        False,
        "small-account coverage",
        [
            f"{len(shortfalls)} seed lists below threshold show incomplete captures.",
            *sample_lines,
        ],
    )
    remaining = len(shortfalls) - len(samples)
    if remaining > 0:
        print(f"   …and {remaining} more.")
    print("   Next: re-run enrichment for listed seeds or inspect scrape_run_metrics for anomalies.")


if __name__ == "__main__":
    main()
