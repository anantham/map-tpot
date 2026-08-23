"""Behavioral tests for logical read-only holdout snapshots."""
from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from src.evaluation.holdout_snapshot import (
    HoldoutSnapshotError,
    read_holdout_snapshot,
)


def _database(path: Path, rows: list[tuple[object, object]]) -> Path:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE tpot_directory_holdout (handle TEXT, account_id TEXT)"
        )
        connection.executemany(
            "INSERT INTO tpot_directory_holdout VALUES (?, ?)", rows
        )
    return path


def test_snapshot_is_logical_normalized_and_order_independent(tmp_path: Path) -> None:
    rows = [
        (" @PilotOne ", "001"),
        ("PILOTTWO", "2"),
        ("pilotone", "001"),
        (None, "3"),
    ]
    first = read_holdout_snapshot(
        _database(tmp_path / "first.db", rows),
        frozenset({"pilotone", "notheldout"}),
    )
    second = read_holdout_snapshot(
        _database(tmp_path / "second.db", list(reversed(rows))),
        frozenset({"pilotone", "notheldout"}),
    )

    assert first.logical_sha256 == second.logical_sha256
    assert len(first.logical_sha256) == 64
    assert first.normalized_handle_count == 2
    assert first.account_id_count == 3
    assert first.panel_handle_overlap_count == 1
    assert first.handles == frozenset({"pilotone", "pilottwo"})
    assert first.account_ids == frozenset({"001", "2", "3"})
    assert "001" not in repr(first)
    assert "pilotone" not in repr(first)


def test_logical_digest_changes_only_when_exclusion_sets_change(tmp_path: Path) -> None:
    base = read_holdout_snapshot(
        _database(tmp_path / "base.db", [("pilot", "1")]),
        frozenset({"other"}),
    )
    duplicate = read_holdout_snapshot(
        _database(tmp_path / "duplicate.db", [("pilot", "1"), ("PILOT", "1")]),
        frozenset({"other"}),
    )
    changed = read_holdout_snapshot(
        _database(tmp_path / "changed.db", [("pilot", "1"), (None, "2")]),
        frozenset({"other"}),
    )

    assert duplicate.logical_sha256 == base.logical_sha256
    assert changed.logical_sha256 != base.logical_sha256


@pytest.mark.parametrize(
    "setup,message",
    [
        (lambda path: path, "does not exist"),
        (
            lambda path: sqlite3.connect(path).execute(
                "CREATE TABLE something_else (handle TEXT)"
            ).connection.close() or path,
            "required holdout table",
        ),
        (
            lambda path: sqlite3.connect(path).execute(
                "CREATE TABLE tpot_directory_holdout (handle TEXT)"
            ).connection.close() or path,
            "requires handle and account_id",
        ),
    ],
)
def test_missing_file_table_or_columns_fail_closed(
    tmp_path: Path, setup, message: str
) -> None:
    path = tmp_path / "archive.db"
    setup(path)

    with pytest.raises(HoldoutSnapshotError, match=message):
        read_holdout_snapshot(path, frozenset({"pilot"}))


def test_invalid_account_id_or_empty_snapshot_fails_closed(tmp_path: Path) -> None:
    invalid = _database(tmp_path / "invalid.db", [("pilot", "not-decimal")])
    with pytest.raises(HoldoutSnapshotError, match="decimal"):
        read_holdout_snapshot(invalid, frozenset({"pilot"}))

    empty = _database(tmp_path / "empty.db", [(None, None)])
    with pytest.raises(HoldoutSnapshotError, match="no usable identities"):
        read_holdout_snapshot(empty, frozenset({"pilot"}))
