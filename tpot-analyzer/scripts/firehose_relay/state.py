"""Checkpoint persistence for firehose relay."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .models import RelayCheckpoint


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_checkpoint(*, firehose_path: Path) -> RelayCheckpoint:
    return RelayCheckpoint(
        firehose_path=str(firehose_path),
        byte_offset=0,
        updated_at=now_utc(),
    )


def load_checkpoint(*, checkpoint_path: Path, firehose_path: Path) -> RelayCheckpoint:
    if not checkpoint_path.exists():
        return default_checkpoint(firehose_path=firehose_path)
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except Exception:
        return default_checkpoint(firehose_path=firehose_path)
    return _checkpoint_from_payload(payload=payload, firehose_path=firehose_path)


def save_checkpoint(*, checkpoint_path: Path, checkpoint: RelayCheckpoint) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    payload = checkpoint.as_dict()
    payload["updated_at"] = now_utc()
    tmp_path = checkpoint_path.with_suffix(f"{checkpoint_path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(checkpoint_path)


def _checkpoint_from_payload(*, payload: Dict[str, Any], firehose_path: Path) -> RelayCheckpoint:
    firehose = str(payload.get("firehose_path") or firehose_path)
    try:
        offset = max(0, int(payload.get("byte_offset") or 0))
    except Exception:
        offset = 0

    def _int_field(name: str) -> int:
        try:
            return max(0, int(payload.get(name) or 0))
        except Exception:
            return 0

    return RelayCheckpoint(
        firehose_path=firehose,
        byte_offset=offset,
        events_read_total=_int_field("events_read_total"),
        events_forwarded_total=_int_field("events_forwarded_total"),
        events_skipped_participant_total=_int_field("events_skipped_participant_total"),
        parse_errors_total=_int_field("parse_errors_total"),
        batches_sent_total=_int_field("batches_sent_total"),
        batches_failed_total=_int_field("batches_failed_total"),
        retries_total=_int_field("retries_total"),
        last_success_at=_optional_text(payload.get("last_success_at")),
        last_error=_optional_text(payload.get("last_error")),
        updated_at=_optional_text(payload.get("updated_at")) or now_utc(),
    )


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
