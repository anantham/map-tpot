#!/usr/bin/env python3
"""Verify topic-seed ingestion and active-learning handoff."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _check(conn: sqlite3.Connection, label: str, ok: bool, detail: str) -> bool:
    status = "✓" if ok else "✗"
    print(f"{status} {label}: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify topic-seed ingestion rows and round-1 eligibility."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "archive_tweets.db",
        help="Path to archive_tweets.db",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"✗ database: not found at {args.db_path}")
        print("Next step: pass --db-path with the correct SQLite file.")
        return 1

    conn = sqlite3.connect(str(args.db_path))
    ok = True

    topic_tweets = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT account_id) FROM enriched_tweets WHERE fetch_source = 'topic_seed'"
    ).fetchone()
    topic_accounts = conn.execute(
        "SELECT COUNT(*) FROM frontier_ranking WHERE band = 'topic_seed'"
    ).fetchone()[0]
    eligible_accounts = conn.execute(
        """
        SELECT COUNT(*)
        FROM frontier_ranking fr
        WHERE fr.band = 'topic_seed'
        AND EXISTS (
            SELECT 1 FROM enriched_tweets et
            WHERE et.account_id = fr.account_id
            AND et.fetch_source = 'topic_seed'
        )
        AND NOT EXISTS (
            SELECT 1 FROM enriched_tweets et
            WHERE et.account_id = fr.account_id
            AND COALESCE(et.fetch_source, '') != 'topic_seed'
        )
        """
    ).fetchone()[0]
    logged_calls = conn.execute(
        "SELECT COUNT(*) FROM enrichment_log WHERE action = 'advanced_search_topic_seed'"
    ).fetchone()[0]

    ok &= _check(
        conn,
        "topic tweets stored",
        topic_tweets[0] > 0,
        f"{topic_tweets[0]} rows across {topic_tweets[1]} authors",
    )
    ok &= _check(
        conn,
        "frontier staging",
        topic_accounts > 0,
        f"{topic_accounts} topic_seed accounts in frontier_ranking",
    )
    ok &= _check(
        conn,
        "round-1 eligibility",
        eligible_accounts > 0,
        f"{eligible_accounts} topic_seed accounts remain eligible for account-level fetch",
    )
    ok &= _check(
        conn,
        "API logging",
        logged_calls > 0,
        f"{logged_calls} advanced_search_topic_seed calls logged",
    )

    sample_rows = conn.execute(
        """
        SELECT fr.account_id, COALESCE(p.username, fr.account_id), fr.info_value
        FROM frontier_ranking fr
        LEFT JOIN profiles p ON p.account_id = fr.account_id
        WHERE fr.band = 'topic_seed'
        ORDER BY fr.info_value DESC, fr.account_id
        LIMIT 5
        """
    ).fetchall()
    print("Sample staged accounts:")
    if sample_rows:
        for account_id, username, info_value in sample_rows:
            print(f"  - @{username} ({account_id}) info_value={info_value:.1f}")
    else:
        print("  - none")

    print("Next steps:")
    if ok:
        print("  - Run `python -m scripts.active_learning --round 1 --top N` to fetch full account timelines.")
        print("  - Paste this output into chat if you want a quick integrity review.")
        return 0

    print("  - Re-run `scripts/fetch_topic_seeds.py` and confirm the query set produced parsable tweets.")
    print("  - Inspect `enrichment_log` rows with action='advanced_search_topic_seed' for failed or empty searches.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
