"""Incremental NDJSON reader for firehose relay."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import ReadResult, RelayRecord

logger = logging.getLogger(__name__)


def read_records(
    *,
    firehose_path: Path,
    byte_offset: int,
    max_records: int,
) -> ReadResult:
    if max_records <= 0:
        raise ValueError("max_records must be > 0")
    if not firehose_path.exists():
        return ReadResult(records=[], file_size=0, rotated=False, parse_errors=0)

    file_size = firehose_path.stat().st_size
    rotated = file_size < max(0, byte_offset)
    start_offset = 0 if rotated else max(0, byte_offset)
    parse_errors = 0
    records: list[RelayRecord] = []

    with firehose_path.open("rb") as handle:
        handle.seek(start_offset)
        while len(records) < max_records:
            line = handle.readline()
            if not line:
                break
            end_offset = handle.tell()
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                parse_errors += 1
                logger.warning(
                    "firehose parse error offset=%s snippet=%s",
                    end_offset,
                    text[:120],
                )
                continue
            if not isinstance(payload, dict):
                parse_errors += 1
                logger.warning(
                    "firehose payload not object offset=%s type=%s",
                    end_offset,
                    type(payload).__name__,
                )
                continue
            records.append(
                RelayRecord(
                    line_end_offset=end_offset,
                    raw_line=text,
                    payload=payload,
                )
            )

    return ReadResult(
        records=records,
        file_size=file_size,
        rotated=rotated,
        parse_errors=parse_errors,
    )
