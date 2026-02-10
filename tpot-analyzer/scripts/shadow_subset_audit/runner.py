"""Main audit loop orchestration for shadow subset verification."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from .console import print_header, print_relation_summary, write_checkpoint
from .constants import CHECK, CROSS
from .local_db import local_relation_usernames
from .observability import AuditRuntime
from .remote import fetch_remote_relation
from .reporting import summarize_overlap

Target = Tuple[str, Optional[str], List[str]]


def run_audit(
    *,
    args: Any,
    conn: sqlite3.Connection,
    id_to_username: Dict[str, str],
    targets: Sequence[Target],
    session: requests.Session,
    runtime: AuditRuntime,
    logger,
    key_source: Optional[str],
    results: List[Dict[str, object]],
    total_targets: int,
    completed_offset: int,
    starting_total_remote_requests: int,
) -> Tuple[Dict[str, object], int]:
    total_remote_requests = max(0, starting_total_remote_requests)

    def maybe_checkpoint_periodic() -> None:
        reason = runtime.due_checkpoint_reason()
        if reason:
            write_checkpoint(
                reason=f"periodic:{reason}",
                output_path=args.output,
                db_path=args.db_path,
                total_targets=total_targets,
                total_remote_requests=total_remote_requests,
                results=results,
                runtime=runtime,
                is_complete=False,
            )

    print_header(db_path=str(args.db_path), key_source=key_source, targets_count=total_targets)
    logger.info(
        "audit_start db_path=%s targets=%s pending=%s output=%s",
        args.db_path,
        total_targets,
        len(targets),
        args.output,
    )
    write_checkpoint(
        reason="run_start",
        output_path=args.output,
        db_path=args.db_path,
        total_targets=total_targets,
        total_remote_requests=total_remote_requests,
        results=results,
        runtime=runtime,
        is_complete=False,
    )

    for index, (username, numeric_id, account_ids) in enumerate(targets, start=completed_offset + 1):
        runtime.begin_account(username=username, index=index, total=total_targets)
        print(f"\n[{index}/{total_targets}] @{username} ids={account_ids}")
        account_result: Dict[str, object] = {
            "username": username,
            "numeric_id": numeric_id,
            "local_account_ids": account_ids,
        }

        local_followers = local_relation_usernames(conn, account_ids, "followers", id_to_username)
        local_followings = local_relation_usernames(conn, account_ids, "followings", id_to_username)
        print(f"{CHECK} local followers={len(local_followers)} followings={len(local_followings)}")

        def on_remote_event(event: Dict[str, object]) -> None:
            runtime.observe_remote_event(event)
            maybe_checkpoint_periodic()

        runtime.begin_relation("followers")
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
            event_callback=on_remote_event,
        )
        runtime.complete_relation(
            relation="followers",
            pages_fetched=remote_followers.pages_fetched,
            requests_made=remote_followers.requests_made,
        )
        write_checkpoint(
            reason=f"relation_complete:{username}:followers",
            output_path=args.output,
            db_path=args.db_path,
            total_targets=total_targets,
            total_remote_requests=total_remote_requests,
            results=results,
            runtime=runtime,
            is_complete=False,
        )

        runtime.begin_relation("followings")
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
            event_callback=on_remote_event,
        )
        runtime.complete_relation(
            relation="followings",
            pages_fetched=remote_followings.pages_fetched,
            requests_made=remote_followings.requests_made,
        )
        write_checkpoint(
            reason=f"relation_complete:{username}:followings",
            output_path=args.output,
            db_path=args.db_path,
            total_targets=total_targets,
            total_remote_requests=total_remote_requests,
            results=results,
            runtime=runtime,
            is_complete=False,
        )

        total_remote_requests += remote_followers.requests_made + remote_followings.requests_made
        followers_summary = summarize_overlap(local_followers, remote_followers.usernames)
        followings_summary = summarize_overlap(local_followings, remote_followings.usernames)

        if remote_followers.pages_fetched > 0:
            print_relation_summary(
                relation="followers",
                remote_count=len(remote_followers.usernames),
                pages=remote_followers.pages_fetched,
                requests_made=remote_followers.requests_made,
                summary=followers_summary,
            )
        else:
            print(f"{CROSS} remote followers fetch failed: {remote_followers.errors[:2]}")

        if remote_followings.pages_fetched > 0:
            print_relation_summary(
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
        runtime.complete_account(username=username, index=index, total=total_targets)
        write_checkpoint(
            reason=f"account_complete:{username}",
            output_path=args.output,
            db_path=args.db_path,
            total_targets=total_targets,
            total_remote_requests=total_remote_requests,
            results=results,
            runtime=runtime,
            is_complete=False,
        )

    runtime.mark_complete()
    report = write_checkpoint(
        reason="run_complete",
        output_path=args.output,
        db_path=args.db_path,
        total_targets=total_targets,
        total_remote_requests=total_remote_requests,
        results=results,
        runtime=runtime,
        is_complete=True,
    )
    return report, total_remote_requests
