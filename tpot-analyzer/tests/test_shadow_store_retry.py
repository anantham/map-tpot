"""Regression tests for ShadowStore retry helpers."""
from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from src.data.shadow_store import ShadowStore


@pytest.fixture()
def shadow_store() -> ShadowStore:
    engine = create_engine("sqlite:///:memory:", future=True)
    return ShadowStore(engine)


def test_execute_with_retry_recovers_from_disk_io(shadow_store: ShadowStore) -> None:
    attempts: dict[str, int] = {"count": 0}

    def flaky(_: Any) -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OperationalError(
                "insert into shadow_account",
                {},
                sqlite3.OperationalError("disk I/O error"),
            )
        return "ok"

    result = shadow_store._execute_with_retry(  # type: ignore[attr-defined]
        "test_op",
        flaky,
        max_attempts=3,
        base_delay_seconds=0.0,
    )

    assert result == "ok"
    assert attempts["count"] == 2


def test_execute_with_retry_bubbles_non_retryable(shadow_store: ShadowStore) -> None:
    def boom(_: Any) -> str:
        raise OperationalError(
            "insert into shadow_account",
            {},
            sqlite3.OperationalError("some other failure"),
        )

    with pytest.raises(OperationalError):
        shadow_store._execute_with_retry(  # type: ignore[attr-defined]
            "test_op",
            boom,
            max_attempts=2,
            base_delay_seconds=0.0,
        )
