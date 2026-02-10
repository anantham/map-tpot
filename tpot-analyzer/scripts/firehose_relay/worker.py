"""Worker loop for relaying firehose events to a configured endpoint."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import requests

from .models import RelayCheckpoint, RelayRecord
from .reader import read_records
from .state import load_checkpoint, now_utc, save_checkpoint
from .transport import send_batch

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelayConfig:
    firehose_path: Path
    checkpoint_path: Path
    endpoint_url: str
    batch_size: int = 100
    poll_interval_seconds: float = 2.0
    timeout_seconds: float = 15.0
    max_attempts: int = 5
    initial_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 10.0
    idle_heartbeat_seconds: float = 30.0
    once: bool = False
    dry_run: bool = False
    allow_participant: bool = False
    source_id: str = "tpot.firehose.relay"
    max_idle_loops: int = 0


def run_relay(config: RelayConfig) -> RelayCheckpoint:
    if not config.endpoint_url and not config.dry_run:
        raise ValueError("endpoint_url is required unless dry_run is enabled")
    if config.batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    checkpoint = load_checkpoint(
        checkpoint_path=config.checkpoint_path,
        firehose_path=config.firehose_path,
    )
    checkpoint = _align_checkpoint_path(checkpoint, firehose_path=config.firehose_path)

    last_heartbeat = time.monotonic()
    idle_loops = 0

    with requests.Session() as session:
        while True:
            checkpoint = _run_single_iteration(
                config=config,
                session=session,
                checkpoint=checkpoint,
            )
            lag_bytes = _compute_lag_bytes(
                firehose_path=config.firehose_path,
                byte_offset=checkpoint.byte_offset,
            )
            logger.info(
                "relay_status offset=%s lag_bytes=%s forwarded=%s skipped_participant=%s parse_errors=%s",
                checkpoint.byte_offset,
                lag_bytes,
                checkpoint.events_forwarded_total,
                checkpoint.events_skipped_participant_total,
                checkpoint.parse_errors_total,
            )

            if config.once:
                break

            has_lag = lag_bytes > 0
            if has_lag:
                idle_loops = 0
            else:
                idle_loops += 1
                now = time.monotonic()
                if now - last_heartbeat >= config.idle_heartbeat_seconds:
                    checkpoint.last_error = None
                    checkpoint.updated_at = now_utc()
                    save_checkpoint(
                        checkpoint_path=config.checkpoint_path,
                        checkpoint=checkpoint,
                    )
                    last_heartbeat = now
                if config.max_idle_loops > 0 and idle_loops >= config.max_idle_loops:
                    break
                time.sleep(max(0.05, config.poll_interval_seconds))

    return checkpoint


def _run_single_iteration(
    *,
    config: RelayConfig,
    session: requests.Session,
    checkpoint: RelayCheckpoint,
) -> RelayCheckpoint:
    read_result = read_records(
        firehose_path=config.firehose_path,
        byte_offset=checkpoint.byte_offset,
        max_records=config.batch_size,
    )
    if read_result.rotated:
        logger.warning(
            "firehose rotated/truncated; resetting offset old=%s new=0 path=%s",
            checkpoint.byte_offset,
            config.firehose_path,
        )
        checkpoint.byte_offset = 0
    checkpoint.parse_errors_total += read_result.parse_errors

    if not read_result.records:
        checkpoint.updated_at = now_utc()
        save_checkpoint(checkpoint_path=config.checkpoint_path, checkpoint=checkpoint)
        return checkpoint

    checkpoint.events_read_total += len(read_result.records)
    forwarded, skipped_participant = _split_records(
        records=read_result.records,
        allow_participant=config.allow_participant,
    )
    checkpoint.events_skipped_participant_total += skipped_participant

    if forwarded:
        payload = {
            "source": config.source_id,
            "sentAt": now_utc(),
            "events": [record.payload for record in forwarded],
        }
        result = send_batch(
            session=session,
            endpoint_url=config.endpoint_url,
            payload=payload,
            timeout_seconds=config.timeout_seconds,
            max_attempts=config.max_attempts,
            initial_backoff_seconds=config.initial_backoff_seconds,
            max_backoff_seconds=config.max_backoff_seconds,
            dry_run=config.dry_run,
        )
        checkpoint.retries_total += max(0, result.attempts - 1)
        if not result.success:
            checkpoint.batches_failed_total += 1
            checkpoint.last_error = result.error
            checkpoint.updated_at = now_utc()
            save_checkpoint(checkpoint_path=config.checkpoint_path, checkpoint=checkpoint)
            logger.error(
                "relay batch failed attempts=%s status=%s error=%s",
                result.attempts,
                result.status_code,
                result.error,
            )
            return checkpoint

        checkpoint.batches_sent_total += 1
        checkpoint.events_forwarded_total += len(forwarded)
        checkpoint.last_success_at = now_utc()
        checkpoint.last_error = None
    else:
        logger.info("relay batch skipped: participant-only records=%s", len(read_result.records))

    checkpoint.byte_offset = read_result.records[-1].line_end_offset
    checkpoint.updated_at = now_utc()
    save_checkpoint(checkpoint_path=config.checkpoint_path, checkpoint=checkpoint)
    return checkpoint


def _split_records(
    *,
    records: List[RelayRecord],
    allow_participant: bool,
) -> Tuple[List[RelayRecord], int]:
    forwarded: List[RelayRecord] = []
    skipped_participant = 0
    for record in records:
        engagement = _detect_engagement(record.payload)
        if not allow_participant and engagement == "participant":
            skipped_participant += 1
            continue
        forwarded.append(record)
    return forwarded, skipped_participant


def _detect_engagement(payload: Dict[str, object]) -> str:
    top = str(payload.get("engagementType") or payload.get("engagement_type") or "").strip().lower()
    inner = payload.get("payload")
    nested = ""
    if isinstance(inner, dict):
        nested = str(inner.get("engagementType") or inner.get("engagement_type") or "").strip().lower()
    engagement = nested or top or "spectator"
    return engagement


def _compute_lag_bytes(*, firehose_path: Path, byte_offset: int) -> int:
    if not firehose_path.exists():
        return 0
    size = firehose_path.stat().st_size
    return max(0, size - max(0, byte_offset))


def _align_checkpoint_path(
    checkpoint: RelayCheckpoint,
    *,
    firehose_path: Path,
) -> RelayCheckpoint:
    if Path(checkpoint.firehose_path) == firehose_path:
        return checkpoint
    logger.warning(
        "checkpoint firehose path changed old=%s new=%s; resetting offset",
        checkpoint.firehose_path,
        firehose_path,
    )
    checkpoint.firehose_path = str(firehose_path)
    checkpoint.byte_offset = 0
    checkpoint.updated_at = now_utc()
    checkpoint.last_error = None
    return checkpoint
