#!/usr/bin/env python3
"""Verify shadow edge completeness against twitterapi.io followers/followings."""
from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional, Set, Tuple

import requests
from dotenv import load_dotenv

try:
    from scripts.shadow_subset_audit.cli import parse_args, resolve_api_key
    from scripts.shadow_subset_audit.console import print_footer, write_checkpoint
    from scripts.shadow_subset_audit.constants import CHECK, CROSS, KEY_ENV_CANDIDATES, PROJECT_ROOT
    from scripts.shadow_subset_audit.local_db import load_id_to_username, load_targets
    from scripts.shadow_subset_audit.observability import AuditRuntime, configure_logger, resolve_log_path
    from scripts.shadow_subset_audit.resume import load_resume_state
    from scripts.shadow_subset_audit.runner import run_audit
except ImportError:  # pragma: no cover - supports direct script execution from scripts/
    from shadow_subset_audit.cli import parse_args, resolve_api_key
    from shadow_subset_audit.console import print_footer, write_checkpoint
    from shadow_subset_audit.constants import CHECK, CROSS, KEY_ENV_CANDIDATES, PROJECT_ROOT
    from shadow_subset_audit.local_db import load_id_to_username, load_targets
    from shadow_subset_audit.observability import AuditRuntime, configure_logger, resolve_log_path
    from shadow_subset_audit.resume import load_resume_state
    from shadow_subset_audit.runner import run_audit

Target = Tuple[str, Optional[str], List[str]]


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

    log_path = resolve_log_path(output_path=args.output, log_file=args.log_file)
    logger = configure_logger(log_level=args.log_level, log_path=log_path)
    runtime = AuditRuntime(
        checkpoint_every_requests=args.checkpoint_every_requests,
        checkpoint_min_seconds=args.checkpoint_min_seconds,
        max_event_history=args.max_event_history,
        logger=logger,
    )

    conn = sqlite3.connect(str(args.db_path))
    conn.row_factory = sqlite3.Row
    session = requests.Session()
    session.headers.update({"X-API-Key": api_key, "User-Agent": "TPOTShadowSubsetAudit/1.0"})

    all_targets: List[Target] = []
    targets_to_run: List[Target] = []
    results: List[Dict[str, object]] = []
    total_remote_requests = 0

    try:
        id_to_username = load_id_to_username(conn)
        all_targets = load_targets(conn, args.usernames, args.sample_size)
        if not all_targets:
            print(f"{CROSS} No target accounts found for audit.")
            return 2

        completed_usernames: Set[str] = set()
        if args.resume_from_output:
            allowed_usernames = {username for username, _, _ in all_targets}
            resume_state = load_resume_state(output_path=args.output, allowed_usernames=allowed_usernames)
            for note in resume_state.notes:
                logger.info(note)
            if resume_state.results:
                results.extend(resume_state.results)
                completed_usernames = set(resume_state.completed_usernames)
                total_remote_requests = resume_state.total_remote_requests
                print(
                    f"{CHECK} resume loaded: {len(results)} completed accounts, "
                    f"starting request count={total_remote_requests}"
                )
                if resume_state.previous_generated_at:
                    print(f"{CHECK} previous snapshot generated_at={resume_state.previous_generated_at}")
            else:
                print(f"{CHECK} resume requested, but no reusable completed rows found in {args.output}")

        targets_to_run = [target for target in all_targets if target[0] not in completed_usernames]
        if args.resume_from_output:
            print(
                f"{CHECK} resume targets: completed={len(completed_usernames)} "
                f"remaining={len(targets_to_run)} total={len(all_targets)}"
            )

        if not targets_to_run:
            runtime.mark_complete()
            report = write_checkpoint(
                reason="resume_noop_complete",
                output_path=args.output,
                db_path=args.db_path,
                total_targets=len(all_targets),
                total_remote_requests=total_remote_requests,
                results=results,
                runtime=runtime,
                is_complete=True,
            )
            average_coverage = report.get("average_coverage_pct", {})
            follower_cov = average_coverage.get("followers") if isinstance(average_coverage, dict) else None
            following_cov = average_coverage.get("followings") if isinstance(average_coverage, dict) else None
            print_footer(
                account_count=len(results),
                total_remote_requests=max(total_remote_requests, runtime.remote_requests_observed),
                follower_cov=follower_cov,
                following_cov=following_cov,
                output_path=str(args.output),
            )
            logger.info("resume_noop_complete targets=%s output=%s", len(all_targets), args.output)
            return 0

        report, total_remote_requests = run_audit(
            args=args,
            conn=conn,
            id_to_username=id_to_username,
            targets=targets_to_run,
            session=session,
            runtime=runtime,
            logger=logger,
            key_source=key_source,
            results=results,
            total_targets=len(all_targets),
            completed_offset=len(results),
            starting_total_remote_requests=total_remote_requests,
        )

        average_coverage = report.get("average_coverage_pct", {})
        follower_cov = average_coverage.get("followers") if isinstance(average_coverage, dict) else None
        following_cov = average_coverage.get("followings") if isinstance(average_coverage, dict) else None

        print_footer(
            account_count=len(results),
            total_remote_requests=max(total_remote_requests, runtime.remote_requests_observed),
            follower_cov=follower_cov,
            following_cov=following_cov,
            output_path=str(args.output),
        )
        logger.info(
            "audit_complete accounts=%s remote_requests=%s output=%s log=%s",
            len(results),
            max(total_remote_requests, runtime.remote_requests_observed),
            args.output,
            log_path,
        )
        return 0
    except KeyboardInterrupt:
        runtime.mark_interrupted("KeyboardInterrupt")
        target_count = len(all_targets) if all_targets else len(targets_to_run)
        write_checkpoint(
            reason="run_interrupted",
            output_path=args.output,
            db_path=args.db_path,
            total_targets=target_count,
            total_remote_requests=max(total_remote_requests, runtime.remote_requests_observed),
            results=results,
            runtime=runtime,
            is_complete=False,
        )
        print(f"{CROSS} Run interrupted. Checkpoint persisted to {args.output}")
        return 130
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        runtime.mark_failed(f"{type(exc).__name__}: {exc}")
        logger.exception("audit_failed")
        target_count = len(all_targets) if all_targets else len(targets_to_run)
        write_checkpoint(
            reason="run_failed",
            output_path=args.output,
            db_path=args.db_path,
            total_targets=target_count,
            total_remote_requests=max(total_remote_requests, runtime.remote_requests_observed),
            results=results,
            runtime=runtime,
            is_complete=False,
        )
        print(f"{CROSS} Run failed. Checkpoint persisted to {args.output}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
