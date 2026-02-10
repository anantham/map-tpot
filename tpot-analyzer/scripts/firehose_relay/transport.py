"""HTTP transport with retry/backoff for firehose relay."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

import requests

from .models import SendResult

logger = logging.getLogger(__name__)


def send_batch(
    *,
    session: requests.Session,
    endpoint_url: str,
    payload: Dict[str, Any],
    timeout_seconds: float,
    max_attempts: int,
    initial_backoff_seconds: float,
    max_backoff_seconds: float,
    dry_run: bool,
) -> SendResult:
    if dry_run:
        logger.info(
            "dry-run relay batch size=%s endpoint=%s",
            len(payload.get("events") or []),
            endpoint_url,
        )
        return SendResult(success=True, attempts=1, status_code=200, error=None)

    attempts = 0
    backoff = max(0.1, initial_backoff_seconds)
    last_error: str | None = None
    last_status: int | None = None
    total_attempts = max(1, max_attempts)

    while attempts < total_attempts:
        attempts += 1
        try:
            response = session.post(endpoint_url, json=payload, timeout=timeout_seconds)
            last_status = int(response.status_code)
            if 200 <= response.status_code < 300:
                return SendResult(success=True, attempts=attempts, status_code=last_status, error=None)
            body = response.text[:200]
            last_error = f"http_{response.status_code}: {body}"
            # Retry only on transient classes.
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "relay transient response status=%s attempt=%s/%s",
                    response.status_code,
                    attempts,
                    total_attempts,
                )
            else:
                return SendResult(
                    success=False,
                    attempts=attempts,
                    status_code=last_status,
                    error=last_error,
                )
        except requests.RequestException as exc:
            last_error = str(exc)
            logger.warning(
                "relay request exception attempt=%s/%s error=%s",
                attempts,
                total_attempts,
                exc,
            )

        if attempts >= total_attempts:
            break
        time.sleep(min(backoff, max_backoff_seconds))
        backoff = min(backoff * 2.0, max_backoff_seconds)

    return SendResult(
        success=False,
        attempts=attempts,
        status_code=last_status,
        error=last_error or "unknown relay failure",
    )
