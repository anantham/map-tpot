#!/usr/bin/env python3
"""Relay extension firehose events to an Indra ingestion endpoint."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.firehose_relay.worker import RelayConfig, run_relay  # noqa: E402


CHECK = "✓"
CROSS = "✗"
DEFAULT_INDRA_FIREHOSE_ENDPOINT = "http://localhost:7777/api/firehose/ingest"


def _default_firehose_path() -> Path:
    snapshot_dir = Path(os.getenv("SNAPSHOT_DIR") or (PROJECT_ROOT / "data")).expanduser().resolve()
    return snapshot_dir / "indra_net" / "feed_events.ndjson"


def _default_checkpoint_path(firehose_path: Path) -> Path:
    return firehose_path.parent / "relay_checkpoint.json"


def _default_endpoint_url() -> str:
    configured = os.getenv("INDRA_FIREHOSE_ENDPOINT")
    if configured and configured.strip():
        return configured.strip()
    return DEFAULT_INDRA_FIREHOSE_ENDPOINT


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream local firehose events to an Indra endpoint with checkpoint + retry."
    )
    parser.add_argument("--firehose-path", type=Path, default=_default_firehose_path())
    parser.add_argument("--checkpoint-path", type=Path, default=None)
    parser.add_argument("--endpoint-url", default=_default_endpoint_url())
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--initial-backoff-seconds", type=float, default=0.5)
    parser.add_argument("--max-backoff-seconds", type=float, default=10.0)
    parser.add_argument("--idle-heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--source-id", default="tpot.firehose.relay")
    parser.add_argument("--once", action="store_true", help="Process available batches once, then exit.")
    parser.add_argument("--dry-run", action="store_true", help="Do not POST; simulate forwarding only.")
    parser.add_argument(
        "--allow-participant",
        action="store_true",
        help="Forward participant-tagged events too (default: skip participant).",
    )
    parser.add_argument(
        "--max-idle-loops",
        type=int,
        default=0,
        help="Exit after N idle loops in continuous mode (0 = run forever).",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    firehose_path = args.firehose_path.expanduser().resolve()
    checkpoint_path = (
        args.checkpoint_path.expanduser().resolve()
        if args.checkpoint_path
        else _default_checkpoint_path(firehose_path)
    )

    config = RelayConfig(
        firehose_path=firehose_path,
        checkpoint_path=checkpoint_path,
        endpoint_url=str(args.endpoint_url or ""),
        batch_size=int(args.batch_size),
        poll_interval_seconds=float(args.poll_interval_seconds),
        timeout_seconds=float(args.timeout_seconds),
        max_attempts=int(args.max_attempts),
        initial_backoff_seconds=float(args.initial_backoff_seconds),
        max_backoff_seconds=float(args.max_backoff_seconds),
        idle_heartbeat_seconds=float(args.idle_heartbeat_seconds),
        once=bool(args.once),
        dry_run=bool(args.dry_run),
        allow_participant=bool(args.allow_participant),
        source_id=str(args.source_id),
        max_idle_loops=max(0, int(args.max_idle_loops)),
    )

    print("firehose_relay")
    print("=" * 72)
    print(f"firehose_path: {firehose_path}")
    print(f"checkpoint_path: {checkpoint_path}")
    print(f"endpoint_url: {config.endpoint_url or '<unset>'}")
    print(f"mode: {'once' if config.once else 'continuous'}")
    print(f"dry_run: {config.dry_run}")
    print(f"allow_participant: {config.allow_participant}")
    print("=" * 72)

    try:
        checkpoint = run_relay(config)
    except Exception as exc:
        print(f"{CROSS} relay failed: {exc}")
        return 1

    print(f"{CHECK} relay completed/heartbeat")
    print(f"{CHECK} offset={checkpoint.byte_offset}")
    print(f"{CHECK} events_read_total={checkpoint.events_read_total}")
    print(f"{CHECK} events_forwarded_total={checkpoint.events_forwarded_total}")
    print(f"{CHECK} events_skipped_participant_total={checkpoint.events_skipped_participant_total}")
    print(f"{CHECK} parse_errors_total={checkpoint.parse_errors_total}")
    print(f"{CHECK} batches_sent_total={checkpoint.batches_sent_total}")
    print(f"{CHECK} batches_failed_total={checkpoint.batches_failed_total}")
    print(f"{CHECK} retries_total={checkpoint.retries_total}")
    if checkpoint.last_error:
        print(f"{CROSS} last_error={checkpoint.last_error}")
    print("\nNext steps:")
    print("- Keep this worker running continuously for spectator/firehose sources.")
    print("- Inspect checkpoint JSON to monitor lag and forwarding health.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
