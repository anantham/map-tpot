"""Behavioral regression tests for the assumption-baseline verifier."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from scripts._assumption_baseline_checks import Report
from scripts._assumption_baseline_data import EXPECTED_DATA, inspect_archive
from scripts.verify_assumption_baseline import main


def _create_empty_archive(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                created_at TEXT
            );
            CREATE TABLE likes (
                liker_account_id TEXT,
                tweet_id TEXT
            );
            CREATE TABLE fetch_log (
                username TEXT PRIMARY KEY,
                account_id TEXT,
                fetched_at TEXT
            );
            """
        )


def test_hash_certification_requires_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_assumption_baseline.py", "--require-data", "--hash-data"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2


def test_certified_set_includes_snapshot_metadata() -> None:
    assert "graph_snapshot.meta.json" in EXPECTED_DATA
    assert "graph_snapshot.spectral_meta.json" in EXPECTED_DATA


def test_empty_archive_fails_descriptively(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    archive_path = tmp_path / "archive_tweets.db"
    _create_empty_archive(archive_path)
    report = Report()

    inspect_archive(archive_path, report, deep=False)

    output = capsys.readouterr().out
    assert report.failed == 1
    assert "✗ archive has a valid newest tweet" in output
    assert "no 19-digit Twitter Snowflake ID found" in output
