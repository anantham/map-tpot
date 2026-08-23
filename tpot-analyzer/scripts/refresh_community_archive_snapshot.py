#!/usr/bin/env python3
"""Probe or download a versioned Community Archive bulk snapshot."""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.archive.snapshot import probe_remote_object  # noqa: E402
from src.archive.snapshot_workflow import (  # noqa: E402
    acquire_enriched_tweets_snapshot,
)


CANONICAL_PARQUET_URL = (
    "https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/"
    "enriched_tweets/enriched_tweets.parquet"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "community_archive" / "snapshots"
DEFAULT_MAX_BYTES = 2_000_000_000


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=CANONICAL_PARQUET_URL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--download",
        action="store_true",
        help="download and inspect the probed object; default is metadata-only",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"hard transfer ceiling (default: {DEFAULT_MAX_BYTES:,})",
    )
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--connect-timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--observed-at",
        help="ISO timestamp override for deterministic diagnostics/tests",
    )
    return parser


def _parse_observed_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--observed-at must include a timezone")
    return parsed


def _git_state() -> tuple[str, bool]:
    sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    status_result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sha_result.stdout.strip(), bool(status_result.stdout.strip())


def _print_metadata(metadata, max_bytes: int) -> None:
    print(
        "✓ remote metadata: "
        f"snapshot={metadata.snapshot_id}, bytes={metadata.content_length:,}"
    )
    print(f"  URL: {metadata.url}")
    print(f"  ETag: {metadata.etag or 'missing'}")
    print(f"  Last-Modified: {metadata.last_modified or 'missing'}")
    within_limit = metadata.content_length <= max_bytes
    marker = "✓" if within_limit else "✗"
    print(
        f"{marker} byte ceiling: remote={metadata.content_length:,}, "
        f"limit={max_bytes:,}"
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    print("Community Archive Snapshot Refresh")
    print("=" * 34)

    try:
        observed_at = _parse_observed_at(args.observed_at)
        if args.max_bytes <= 0:
            raise ValueError(f"--max-bytes must be positive; got {args.max_bytes}")
        timeout = httpx.Timeout(
            args.timeout_seconds,
            connect=args.connect_timeout_seconds,
        )
        with client_factory(
            timeout=timeout,
            headers={"User-Agent": "map-tpot-snapshot/1"},
        ) as client:
            metadata = probe_remote_object(
                client,
                args.url,
                observed_at=observed_at,
            )
            _print_metadata(metadata, args.max_bytes)
            if metadata.content_length > args.max_bytes:
                print("\nNext steps")
                print("1. Raise --max-bytes only after checking available disk space.")
                return 1
            if not args.download:
                print("\nProbe only: no response body was downloaded and no files changed.")
                print("\nNext steps")
                print("1. Re-run this command with --download to capture the snapshot.")
                print("2. Keep the frozen research baseline unchanged for comparison.")
                return 0

            git_sha, git_dirty = _git_state()
            print(
                f"✓ acquisition code: git={git_sha[:12]}, dirty={str(git_dirty).lower()}"
            )
            result = acquire_enriched_tweets_snapshot(
                client,
                metadata,
                args.output_root.resolve(),
                max_bytes=args.max_bytes,
                git_sha=git_sha,
                git_dirty=git_dirty,
            )
    except Exception as exc:
        print(f"✗ snapshot acquisition: {type(exc).__name__}: {exc}")
        print("\nNext steps")
        print("1. Resolve the reported validation or transfer error; do not activate it.")
        print("2. Re-run probe-only mode to check whether the remote object changed.")
        return 1

    print(f"✓ snapshot {result.status}: {result.snapshot_dir}")
    for check in result.checks:
        marker = "✓" if check.passed else "✗"
        print(f"{marker} {check.name}: {check.detail}")
    print("\nMetrics")
    for name, value in result.metrics.items():
        rendered = f"{value:,}" if isinstance(value, int) else value
        print(f"- {name}: {rendered}")
    print("\nNext steps")
    print(
        "1. Run `python -m scripts.verify_community_archive_snapshot "
        f"{result.snapshot_dir}`."
    )
    print("2. Record snapshot ID and SHA-256 with each downstream experiment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
