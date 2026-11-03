#!/usr/bin/env python3
"""Verify a named account's raw API acquisition without exposing tweet text.

The verifier opens the archive database read-only and checks identity binding,
holdout exclusion, profile metadata, recent-tweet coverage, following-edge
coverage, and API cost receipts. It deliberately treats missing interpretation
rows as an expected next-step state rather than inventing a card classification.

Test intent exception: this is an operational verification CLI, which this
repository's TDD convention classifies as default-off for new unit tests. Its
public behavior is exercised against the real read-only database after each
named-account acquisition.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3

from _named_account_verification import (
    Verification,
    count_if_present,
    parse_time,
    table_names,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "archive_tweets.db"


def verify(args: argparse.Namespace) -> int:
    result = Verification()
    db_path = args.db_path.resolve()
    result.check("database exists", db_path.is_file(), str(db_path))
    if not db_path.is_file():
        print("Next: pass --db-path for the archive_tweets.db that received the fetch.")
        return 1

    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as error:
        result.check("database opens read-only", False, str(error))
        print("Next: resolve the SQLite/filesystem error before retrying acquisition.")
        return 1

    conn.row_factory = sqlite3.Row
    handle = args.username.strip().lstrip("@")
    account_id = args.account_id.strip()
    try:
        tables = table_names(conn)
        required = {
            "profiles",
            "user_profile_cache",
            "tpot_directory_holdout",
            "enriched_tweets",
            "account_following",
            "enrichment_log",
        }
        missing = sorted(required - tables)
        result.check(
            "required acquisition tables",
            not missing,
            "all present" if not missing else f"missing={missing}",
        )
        if missing:
            print("Next: use the canonical archive database or run its schema initializer.")
            return 1

        profiles = conn.execute(
            """SELECT account_id, username, display_name, fetched_at
               FROM profiles
               WHERE account_id = ? AND lower(username) = lower(?)""",
            (account_id, handle),
        ).fetchall()
        conflicts = conn.execute(
            """SELECT account_id, username FROM profiles
               WHERE lower(username) = lower(?) AND account_id <> ?""",
            (handle, account_id),
        ).fetchall()
        result.check(
            "canonical profile binding",
            len(profiles) == 1 and not conflicts,
            f"matches={len(profiles)} conflicting_ids={len(conflicts)}",
        )

        holdout = conn.execute(
            """SELECT COUNT(*) FROM tpot_directory_holdout
               WHERE account_id = ? OR lower(handle) = lower(?)""",
            (account_id, handle),
        ).fetchone()[0]
        result.check("holdout exclusion", holdout == 0, f"matches={holdout}")

        cache = conn.execute(
            """SELECT username, followers, following, statuses, fetched_at
               FROM user_profile_cache WHERE account_id = ?""",
            (account_id,),
        ).fetchone()
        result.check(
            "profile metadata receipt",
            cache is not None and str(cache["username"]).casefold() == handle.casefold(),
            (
                f"followers={cache['followers']} following={cache['following']} "
                f"statuses={cache['statuses']} fetched_at={cache['fetched_at']}"
                if cache is not None
                else "missing"
            ),
        )

        tweets = conn.execute(
            """SELECT tweet_id, created_at, text, is_reply, fetch_source
               FROM enriched_tweets WHERE account_id = ?""",
            (account_id,),
        ).fetchall()
        distinct_tweets = len({row["tweet_id"] for row in tweets})
        nonempty_text = sum(bool((row["text"] or "").strip()) for row in tweets)
        parsed_times = [
            parsed
            for parsed in (parse_time(row["created_at"]) for row in tweets)
            if parsed is not None
        ]
        result.check(
            "recent tweet coverage",
            len(tweets) > 0
            and distinct_tweets == len(tweets)
            and nonempty_text == len(tweets),
            (
                f"rows={len(tweets)} distinct={distinct_tweets} "
                f"nonempty={nonempty_text} replies={sum(int(row['is_reply'] or 0) for row in tweets)}"
            ),
        )
        result.check(
            "tweet timestamps parse",
            len(parsed_times) == len(tweets),
            (
                f"parsed={len(parsed_times)}/{len(tweets)} "
                f"range={min(parsed_times).isoformat()}..{max(parsed_times).isoformat()}"
                if parsed_times
                else "no parseable timestamps"
            ),
        )

        edge_count, distinct_edges = conn.execute(
            """SELECT COUNT(*), COUNT(DISTINCT following_account_id)
               FROM account_following WHERE account_id = ?""",
            (account_id,),
        ).fetchone()
        expected_following = (
            args.expected_following
            if args.expected_following is not None
            else int(cache["following"] or 0) if cache is not None else None
        )
        edges_complete = (
            edge_count == distinct_edges
            and edge_count > 0
            and (expected_following is None or edge_count == expected_following)
        )
        result.check(
            "following-edge coverage",
            edges_complete,
            f"rows={edge_count} distinct={distinct_edges} expected={expected_following}",
        )

        logs = conn.execute(
            """SELECT action, COUNT(*) AS calls,
                      COALESCE(SUM(tweets_fetched), 0) AS tweets,
                      COALESCE(SUM(estimated_cost), 0) AS usd
               FROM enrichment_log WHERE account_id = ? GROUP BY action""",
            (account_id,),
        ).fetchall()
        actions = {row["action"] for row in logs}
        required_actions = {"user_info", "last_tweets", "followings"}
        result.check(
            "API request receipts",
            required_actions <= actions,
            "; ".join(
                f"{row['action']} calls={row['calls']} tweets={row['tweets']} usd={row['usd']:.6f}"
                for row in logs
            ),
        )

        label_counts = {
            "tweet_tags": count_if_present(
                conn,
                tables,
                "tweet_tags",
                """SELECT COUNT(*) FROM tweet_tags WHERE tweet_id IN
                   (SELECT tweet_id FROM enriched_tweets WHERE account_id = ?)""",
                account_id,
            ),
            "account_community_bits": count_if_present(
                conn,
                tables,
                "account_community_bits",
                "SELECT COUNT(*) FROM account_community_bits WHERE account_id = ?",
                account_id,
            ),
            "account_fingerprint": count_if_present(
                conn,
                tables,
                "account_fingerprint",
                "SELECT COUNT(*) FROM account_fingerprint WHERE account_id = ?",
                account_id,
            ),
        }
        print(
            "✓ interpretation boundary: "
            + " ".join(f"{name}={count}" for name, count in label_counts.items())
        )

        if args.quick_check:
            integrity = conn.execute("PRAGMA quick_check(1)").fetchone()[0]
            result.check("SQLite quick_check", integrity == "ok", integrity)
    except sqlite3.Error as error:
        result.check("SQLite verification queries", False, str(error))
    finally:
        conn.close()

    print(f"\nSummary: {result.failures} failed check(s).")
    if result.failures:
        print("Next: inspect the failed receipt before labeling or exporting this account.")
        return 1
    print("Next: raw acquisition is ready for model labeling and explicit human review.")
    print("Do not export or deploy a card until that interpretation gate is accepted.")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--username", required=True)
    value.add_argument("--account-id", required=True)
    value.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    value.add_argument("--expected-following", type=int)
    value.add_argument(
        "--quick-check",
        action="store_true",
        help="Run SQLite PRAGMA quick_check(1); this can take about a minute on the full DB.",
    )
    return value


if __name__ == "__main__":
    raise SystemExit(verify(parser().parse_args()))
