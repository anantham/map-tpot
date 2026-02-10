#!/usr/bin/env python3
"""Verify shadow edge completeness against twitterapi.io followers/followings.

Compares local `shadow_edge` coverage to remote followers/followings snapshots
for a selected subset of accounts and prints human-friendly diagnostics.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, List

import requests
from dotenv import load_dotenv

try:
    from scripts.shadow_subset_audit.cli import parse_args, resolve_api_key
    from scripts.shadow_subset_audit.constants import (
        CHECK,
        CROSS,
        KEY_ENV_CANDIDATES,
        PROJECT_ROOT,
        now_utc,
    )
    from scripts.shadow_subset_audit.local_db import (
        load_id_to_username,
        load_targets,
        local_relation_usernames,
    )
    from scripts.shadow_subset_audit.remote import fetch_remote_relation
    from scripts.shadow_subset_audit.reporting import summarize_overlap, write_report
except ImportError:  # pragma: no cover - supports direct script execution from scripts/
    from shadow_subset_audit.cli import parse_args, resolve_api_key
    from shadow_subset_audit.constants import CHECK, CROSS, KEY_ENV_CANDIDATES, PROJECT_ROOT, now_utc
    from shadow_subset_audit.local_db import load_id_to_username, load_targets, local_relation_usernames
    from shadow_subset_audit.remote import fetch_remote_relation
    from shadow_subset_audit.reporting import summarize_overlap, write_report


def _print_header(*, db_path: str, key_source: str | None, targets_count: int) -> None:
    print("shadow_subset_vs_twitterapiio")
    print("=" * 72)
    print(f"Generated: {now_utc()}")
    print(f"DB path: {db_path}")
    print(f"Key source: {key_source}")
    print(f"Targets: {targets_count}")
    print("=" * 72)


def _print_relation_summary(*, relation: str, remote_count: int, pages: int, requests_made: int, summary: Dict[str, object]) -> None:
    print(f"{CHECK} remote {relation}={remote_count} pages={pages} requests={requests_made}")
    print(
        f"{CHECK} {relation} coverage={summary['coverage_pct']}% "
        f"precision={summary['precision_pct']}% "
        f"missing={summary['missing_in_local_count']} "
        f"extra={summary['extra_in_local_count']}"
    )


def _print_footer(*, account_count: int, total_remote_requests: int, follower_cov: object, following_cov: object, output_path: str) -> None:
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"{CHECK} accounts audited: {account_count}")
    print(f"{CHECK} total remote requests: {total_remote_requests}")
    print(f"{CHECK} avg followers coverage: {follower_cov}%")
    print(f"{CHECK} avg followings coverage: {following_cov}%")
    print(f"{CHECK} report written: {output_path}")
    print("\nNext steps:")
    print("- If coverage is low, re-scrape specific seeds with incomplete follow lists.")
    print("- Raise --max-pages for higher confidence on large accounts.")
    print("- Keep this script output in chat for before/after enrichment comparisons.")


def main() -> int:
    args = parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    api_key, key_source = resolve_api_key(args.api_key)
    if not api_key:
        print(f"{CROSS} Missing twitterapi.io key.")
        print(f"Checked env vars: {', '.join(KEY_ENV_CANDIDATES)}")
        print("Next step: export one of those vars or pass --api-key.")
        return 2

    if not args.db_path.exists():
        print(f"{CROSS} Database not found: {args.db_path}")
        return 2

    conn = sqlite3.connect(str(args.db_path))
    conn.row_factory = sqlite3.Row
    id_to_username = load_id_to_username(conn)
    targets = load_targets(conn, args.usernames, args.sample_size)
    if not targets:
        print(f"{CROSS} No target accounts found for audit.")
        conn.close()
        return 2

    session = requests.Session()
    session.headers.update({"X-API-Key": api_key, "User-Agent": "TPOTShadowSubsetAudit/1.0"})

    results: List[Dict[str, object]] = []
    total_remote_requests = 0

    _print_header(db_path=str(args.db_path), key_source=key_source, targets_count=len(targets))

    for index, (username, numeric_id, account_ids) in enumerate(targets, start=1):
        print(f"\n[{index}/{len(targets)}] @{username} ids={account_ids}")
        account_result: Dict[str, object] = {
            "username": username,
            "numeric_id": numeric_id,
            "local_account_ids": account_ids,
        }

        local_followers = local_relation_usernames(conn, account_ids, "followers", id_to_username)
        local_followings = local_relation_usernames(conn, account_ids, "followings", id_to_username)
        print(f"{CHECK} local followers={len(local_followers)} followings={len(local_followings)}")

        remote_followers = fetch_remote_relation(
            session=session,
            base_url=args.base_url,
            relation="followers",
            username=username,
            user_id=numeric_id,
            identifier_mode=args.identifier_mode,
            page_size=args.page_size,
            max_pages=args.max_pages,
            timeout_seconds=args.timeout_seconds,
            wait_on_rate_limit=args.wait_on_rate_limit,
        )
        remote_followings = fetch_remote_relation(
            session=session,
            base_url=args.base_url,
            relation="followings",
            username=username,
            user_id=numeric_id,
            identifier_mode=args.identifier_mode,
            page_size=args.page_size,
            max_pages=args.max_pages,
            timeout_seconds=args.timeout_seconds,
            wait_on_rate_limit=args.wait_on_rate_limit,
        )
        total_remote_requests += remote_followers.requests_made + remote_followings.requests_made

        followers_summary = summarize_overlap(local_followers, remote_followers.usernames)
        followings_summary = summarize_overlap(local_followings, remote_followings.usernames)

        if remote_followers.pages_fetched > 0:
            _print_relation_summary(
                relation="followers",
                remote_count=len(remote_followers.usernames),
                pages=remote_followers.pages_fetched,
                requests_made=remote_followers.requests_made,
                summary=followers_summary,
            )
        else:
            print(f"{CROSS} remote followers fetch failed: {remote_followers.errors[:2]}")

        if remote_followings.pages_fetched > 0:
            _print_relation_summary(
                relation="followings",
                remote_count=len(remote_followings.usernames),
                pages=remote_followings.pages_fetched,
                requests_made=remote_followings.requests_made,
                summary=followings_summary,
            )
        else:
            print(f"{CROSS} remote followings fetch failed: {remote_followings.errors[:2]}")

        print(f"  sample missing followers: {followers_summary['missing_in_local'][:args.sample_output_count]}")
        print(f"  sample missing followings: {followings_summary['missing_in_local'][:args.sample_output_count]}")

        account_result["followers"] = {
            "remote": {
                **remote_followers.__dict__,
                "usernames": sorted(remote_followers.usernames),
            },
            "summary": followers_summary,
        }
        account_result["followings"] = {
            "remote": {
                **remote_followings.__dict__,
                "usernames": sorted(remote_followings.usernames),
            },
            "summary": followings_summary,
        }
        results.append(account_result)

        write_report(
            output_path=args.output,
            db_path=args.db_path,
            total_targets=len(targets),
            total_remote_requests=total_remote_requests,
            results=results,
            is_complete=False,
        )
        print(f"{CHECK} checkpoint written ({len(results)}/{len(targets)}): {args.output}")

    conn.close()

    report = write_report(
        output_path=args.output,
        db_path=args.db_path,
        total_targets=len(targets),
        total_remote_requests=total_remote_requests,
        results=results,
        is_complete=True,
    )
    average_coverage = report.get("average_coverage_pct", {})
    follower_cov = average_coverage.get("followers") if isinstance(average_coverage, dict) else None
    following_cov = average_coverage.get("followings") if isinstance(average_coverage, dict) else None

    _print_footer(
        account_count=len(results),
        total_remote_requests=total_remote_requests,
        follower_cov=follower_cov,
        following_cov=following_cov,
        output_path=str(args.output),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
