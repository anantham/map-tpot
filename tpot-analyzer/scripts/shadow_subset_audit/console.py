"""Console output and checkpoint persistence helpers for shadow subset audit."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .constants import CHECK, now_utc
from .observability import AuditRuntime
from .reporting import write_report


def print_header(*, db_path: str, key_source: str | None, targets_count: int) -> None:
    print("shadow_subset_vs_twitterapiio")
    print("=" * 72)
    print(f"Generated: {now_utc()}")
    print(f"DB path: {db_path}")
    print(f"Key source: {key_source}")
    print(f"Targets: {targets_count}")
    print("=" * 72)


def print_relation_summary(
    *,
    relation: str,
    remote_count: int,
    pages: int,
    requests_made: int,
    summary: Dict[str, object],
) -> None:
    print(f"{CHECK} remote {relation}={remote_count} pages={pages} requests={requests_made}")
    print(
        f"{CHECK} {relation} coverage={summary['coverage_pct']}% "
        f"precision={summary['precision_pct']}% "
        f"missing={summary['missing_in_local_count']} "
        f"extra={summary['extra_in_local_count']}"
    )


def print_footer(
    *,
    account_count: int,
    total_remote_requests: int,
    follower_cov: object,
    following_cov: object,
    output_path: str,
) -> None:
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


def write_checkpoint(
    *,
    reason: str,
    output_path: Path,
    db_path: Path,
    total_targets: int,
    total_remote_requests: int,
    results: List[Dict[str, object]],
    runtime: AuditRuntime,
    is_complete: bool,
) -> Dict[str, object]:
    runtime.mark_checkpoint(reason)
    report = write_report(
        output_path=output_path,
        db_path=db_path,
        total_targets=total_targets,
        total_remote_requests=max(total_remote_requests, runtime.remote_requests_observed),
        results=results,
        is_complete=is_complete,
        runtime=runtime.snapshot(total_accounts=total_targets),
    )
    print(
        f"{CHECK} checkpoint written ({len(results)}/{total_targets}): "
        f"{output_path} reason={reason}"
    )
    return report
