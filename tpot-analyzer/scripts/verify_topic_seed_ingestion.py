#!/usr/bin/env python3
"""Verify topic-seed ingestion and export explicit review handles."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _check(label: str, ok: bool, detail: str) -> bool:
    status = "✓" if ok else "✗"
    print(f"{status} {label}: {detail}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify topic-seed rows and export explicit candidates."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "archive_tweets.db",
        help="Path to archive_tweets.db",
    )
    parser.add_argument(
        "--handles-output",
        type=Path,
        help="Optional file to write, one review candidate handle per line",
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
    candidate_rows = conn.execute(
        """
        SELECT et.account_id,
               COALESCE(NULLIF(p.username, ''), NULLIF(et.username, ''))
        FROM enriched_tweets et
        LEFT JOIN profiles p ON p.account_id = et.account_id
        WHERE et.fetch_source = 'topic_seed'
        GROUP BY et.account_id
        HAVING COALESCE(NULLIF(p.username, ''), NULLIF(et.username, ''))
               IS NOT NULL
        ORDER BY LOWER(
            COALESCE(NULLIF(p.username, ''), NULLIF(et.username, ''))
        )
        """
    ).fetchall()
    logged_calls = conn.execute(
        "SELECT COUNT(*) FROM enrichment_log WHERE action = 'advanced_search_topic_seed'"
    ).fetchone()[0]

    ok &= _check(
        "topic tweets stored",
        topic_tweets[0] > 0,
        f"{topic_tweets[0]} rows across {topic_tweets[1]} authors",
    )
    ok &= _check(
        "explicit review candidates",
        len(candidate_rows) > 0,
        f"{len(candidate_rows)} resolvable topic_seed authors; no ranking implied",
    )
    ok &= _check(
        "API logging",
        logged_calls > 0,
        f"{logged_calls} advanced_search_topic_seed calls logged",
    )

    print("Sample explicit candidates:")
    if candidate_rows:
        for account_id, username in candidate_rows[:5]:
            print(f"  - @{username} ({account_id})")
    else:
        print("  - none")

    if args.handles_output and candidate_rows:
        handles = [str(row[1]).lstrip("@") for row in candidate_rows]
        args.handles_output.parent.mkdir(parents=True, exist_ok=True)
        args.handles_output.write_text(
            "\n".join(handles) + "\n",
            encoding="utf-8",
        )
        print(
            f"✓ handles file: wrote {len(handles)} candidates to "
            f"{args.handles_output}"
        )

    print(
        "✓ acquisition quarantine: unversioned frontier_ranking rows are "
        "ignored; automatic selection remains blocked"
    )
    print("Next steps:")
    if ok:
        if args.handles_output:
            print(
                "  - Review the handles file, then run "
                "`python -m scripts.active_learning --round 1 "
                f"--accounts-file {args.handles_output}`."
            )
        else:
            print(
                "  - Re-run with `--handles-output <path>`, review that file, "
                "then pass it to active_learning with `--accounts-file`."
            )
        print("  - Paste this output into chat if you want a quick integrity review.")
        return 0

    print("  - Re-run `scripts/fetch_topic_seeds.py` and confirm the query set produced parsable tweets.")
    print("  - Inspect `enrichment_log` rows with action='advanced_search_topic_seed' for failed or empty searches.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
