"""Runtime observability helpers for shadow subset audits."""
from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, Optional

from .constants import now_utc


def resolve_log_path(*, output_path: Path, log_file: Optional[Path]) -> Path:
    if log_file:
        return log_file
    return Path(f"{output_path}.log")


def configure_logger(*, log_level: str, log_path: Path) -> logging.Logger:
    logger = logging.getLogger("shadow_subset_audit")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


class AuditRuntime:
    def __init__(
        self,
        *,
        checkpoint_every_requests: int,
        checkpoint_min_seconds: int,
        max_event_history: int,
        logger: logging.Logger,
    ) -> None:
        self.logger = logger
        self.checkpoint_every_requests = max(0, checkpoint_every_requests)
        self.checkpoint_min_seconds = max(0, checkpoint_min_seconds)
        self.start_time_utc = now_utc()
        self.start_monotonic = time.monotonic()
        self.last_checkpoint_monotonic = self.start_monotonic
        self.last_checkpoint_request_count = 0
        self.checkpoint_count = 0
        self.last_checkpoint_at: Optional[str] = None
        self.last_checkpoint_reason: Optional[str] = None

        self.status = "running"
        self.failure_reason: Optional[str] = None
        self.termination_reason: Optional[str] = None
        self.current_account: Optional[str] = None
        self.current_relation: Optional[str] = None
        self.remote_requests_observed = 0
        self.remote_pages_observed = 0
        self.completed_accounts = 0

        self._event_history: Deque[Dict[str, object]] = deque(maxlen=max(1, max_event_history))

    def begin_account(self, username: str, index: int, total: int) -> None:
        self.current_account = username
        self.current_relation = None
        self.log_event("account_start", username=username, index=index, total=total)
        self.logger.info("account_start username=%s index=%s/%s", username, index, total)

    def complete_account(self, username: str, index: int, total: int) -> None:
        self.completed_accounts += 1
        self.current_account = username
        self.current_relation = None
        self.log_event("account_complete", username=username, index=index, total=total)
        self.logger.info("account_complete username=%s index=%s/%s", username, index, total)

    def begin_relation(self, relation: str) -> None:
        self.current_relation = relation
        self.log_event("relation_start", relation=relation)
        self.logger.info("relation_start account=%s relation=%s", self.current_account, relation)

    def complete_relation(self, relation: str, pages_fetched: int, requests_made: int) -> None:
        self.current_relation = relation
        self.log_event(
            "relation_complete",
            relation=relation,
            pages_fetched=pages_fetched,
            requests_made=requests_made,
        )
        self.logger.info(
            "relation_complete account=%s relation=%s pages=%s requests=%s",
            self.current_account,
            relation,
            pages_fetched,
            requests_made,
        )

    def observe_remote_event(self, event: Dict[str, object]) -> None:
        event_name = str(event.get("event", "remote_event"))
        self.log_event(event_name, **event)
        if event_name in {"response", "request_exception"}:
            self.remote_requests_observed += 1
            status_code = event.get("status_code")
            if event_name == "request_exception":
                self.logger.error(
                    "remote_exception account=%s relation=%s detail=%s",
                    self.current_account,
                    self.current_relation,
                    event.get("detail"),
                )
            elif isinstance(status_code, int) and status_code >= 400:
                self.logger.warning(
                    "remote_response account=%s relation=%s status=%s cursor=%s",
                    self.current_account,
                    self.current_relation,
                    status_code,
                    event.get("cursor"),
                )
            else:
                self.logger.debug(
                    "remote_response account=%s relation=%s status=%s",
                    self.current_account,
                    self.current_relation,
                    status_code,
                )
        elif event_name == "page_complete":
            self.remote_pages_observed += 1
            self.logger.debug(
                "page_complete account=%s relation=%s page_index=%s gathered=%s",
                self.current_account,
                self.current_relation,
                event.get("page_index"),
                event.get("gathered_count"),
            )
        elif event_name == "rate_limit_wait":
            self.logger.warning(
                "rate_limit_wait account=%s relation=%s sleep_seconds=%s",
                self.current_account,
                self.current_relation,
                event.get("sleep_seconds"),
            )
        elif event_name == "request_failed":
            self.logger.error(
                "request_failed account=%s relation=%s status=%s detail=%s",
                self.current_account,
                self.current_relation,
                event.get("status_code"),
                event.get("detail"),
            )

    def due_checkpoint_reason(self) -> Optional[str]:
        request_delta = self.remote_requests_observed - self.last_checkpoint_request_count
        if self.checkpoint_every_requests > 0 and request_delta >= self.checkpoint_every_requests:
            return f"remote_requests+{request_delta}"

        elapsed_seconds = time.monotonic() - self.last_checkpoint_monotonic
        if self.checkpoint_min_seconds > 0 and elapsed_seconds >= self.checkpoint_min_seconds:
            return f"elapsed_{int(elapsed_seconds)}s"
        return None

    def mark_checkpoint(self, reason: str) -> None:
        self.checkpoint_count += 1
        self.last_checkpoint_at = now_utc()
        self.last_checkpoint_reason = reason
        self.last_checkpoint_monotonic = time.monotonic()
        self.last_checkpoint_request_count = self.remote_requests_observed
        self.log_event("checkpoint", reason=reason, checkpoint_count=self.checkpoint_count)
        self.logger.info(
            "checkpoint reason=%s checkpoints=%s observed_requests=%s",
            reason,
            self.checkpoint_count,
            self.remote_requests_observed,
        )

    def mark_failed(self, reason: str) -> None:
        self.status = "failed"
        self.failure_reason = reason
        self.termination_reason = reason
        self.log_event("run_failed", reason=reason)
        self.logger.error("run_failed reason=%s", reason)

    def mark_interrupted(self, reason: str) -> None:
        self.status = "interrupted"
        self.failure_reason = reason
        self.termination_reason = reason
        self.log_event("run_interrupted", reason=reason)
        self.logger.warning("run_interrupted reason=%s", reason)

    def mark_complete(self) -> None:
        self.status = "complete"
        self.log_event("run_complete")
        self.logger.info("run_complete")

    def snapshot(self, *, total_accounts: int) -> Dict[str, object]:
        uptime_seconds = int(time.monotonic() - self.start_monotonic)
        return {
            "status": self.status,
            "started_at": self.start_time_utc,
            "updated_at": now_utc(),
            "uptime_seconds": uptime_seconds,
            "current_account": self.current_account,
            "current_relation": self.current_relation,
            "completed_accounts_runtime": self.completed_accounts,
            "total_accounts": total_accounts,
            "remote_requests_observed": self.remote_requests_observed,
            "remote_pages_observed": self.remote_pages_observed,
            "checkpoint_count": self.checkpoint_count,
            "last_checkpoint_at": self.last_checkpoint_at,
            "last_checkpoint_reason": self.last_checkpoint_reason,
            "failure_reason": self.failure_reason,
            "termination_reason": self.termination_reason,
            "recent_events": list(self._event_history),
        }

    def log_event(self, event_name: str, **payload: object) -> None:
        event_payload: Dict[str, object] = {
            "at": now_utc(),
            "event": event_name,
            "account": self.current_account,
            "relation": self.current_relation,
        }
        event_payload.update(payload)
        self._event_history.append(event_payload)
