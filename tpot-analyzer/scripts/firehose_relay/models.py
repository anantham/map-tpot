"""Data models for firehose relay runtime."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RelayRecord:
    line_end_offset: int
    raw_line: str
    payload: Dict[str, Any]


@dataclass(frozen=True)
class ReadResult:
    records: List[RelayRecord]
    file_size: int
    rotated: bool
    parse_errors: int


@dataclass(frozen=True)
class SendResult:
    success: bool
    attempts: int
    status_code: Optional[int]
    error: Optional[str]


@dataclass
class RelayCheckpoint:
    firehose_path: str
    byte_offset: int
    events_read_total: int = 0
    events_forwarded_total: int = 0
    events_skipped_participant_total: int = 0
    parse_errors_total: int = 0
    batches_sent_total: int = 0
    batches_failed_total: int = 0
    retries_total: int = 0
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    updated_at: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "firehose_path": self.firehose_path,
            "byte_offset": self.byte_offset,
            "events_read_total": self.events_read_total,
            "events_forwarded_total": self.events_forwarded_total,
            "events_skipped_participant_total": self.events_skipped_participant_total,
            "parse_errors_total": self.parse_errors_total,
            "batches_sent_total": self.batches_sent_total,
            "batches_failed_total": self.batches_failed_total,
            "retries_total": self.retries_total,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }
