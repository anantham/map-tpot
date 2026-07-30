"""Spend-boundary regressions for the quarantined frontier ranking."""

from __future__ import annotations

import sqlite3
import sys

import pytest

from scripts.active_learning import main as active_learning_main
from scripts.active_learning import select_accounts
from scripts.active_learning import select_accounts_by_handle
from scripts.active_learning_schema import create_tables
from scripts.fetch_following_for_frontier import select_frontier_targets
from scripts.resolve_band_usernames import load_unresolved_ids


def _write_selection_schema(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
        create_tables(conn)
        conn.executescript(
            """
            CREATE TABLE frontier_ranking (
                account_id TEXT PRIMARY KEY,
                band TEXT,
                info_value REAL,
                top_community TEXT,
                top_weight REAL,
                degree INTEGER,
                in_holdout INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE tpot_directory_holdout (
                handle TEXT,
                account_id TEXT
            );
            CREATE TABLE profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT,
                bio TEXT
            );
            CREATE TABLE resolved_accounts (
                account_id TEXT PRIMARY KEY,
                username TEXT,
                bio TEXT
            );
            CREATE TABLE user_profile_cache (
                account_id TEXT PRIMARY KEY,
                following INTEGER
            );
            CREATE TABLE account_following (
                account_id TEXT,
                following_account_id TEXT
            );
            """
        )


def test_active_learning_cli_rejects_automatic_frontier_selection(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "archive.db"
    _write_selection_schema(db_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "active_learning",
            "--round",
            "1",
            "--archive-only",
            "--db-path",
            str(db_path),
        ],
    )

    with pytest.raises(RuntimeError, match="frontier_ranking.*quarantined"):
        active_learning_main()


def test_frontier_follow_fetch_selection_is_quarantined(tmp_path) -> None:
    db_path = tmp_path / "archive.db"
    _write_selection_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(RuntimeError, match="frontier_ranking.*quarantined"):
            select_frontier_targets(conn, top=10)


def test_frontier_account_selection_api_is_quarantined(tmp_path) -> None:
    db_path = tmp_path / "archive.db"
    _write_selection_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(RuntimeError, match="frontier_ranking.*quarantined"):
            select_accounts(conn, top_n=10, round_num=1)


def test_band_username_resolution_selection_is_quarantined() -> None:
    with sqlite3.connect(":memory:") as conn:
        with pytest.raises(RuntimeError, match="account_band.*quarantined"):
            load_unresolved_ids(conn)


def test_manual_handle_selection_ignores_stale_frontier_metadata(tmp_path) -> None:
    db_path = tmp_path / "archive.db"
    _write_selection_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO profiles VALUES ('account-1', 'example', '')"
        )
        conn.execute(
            "INSERT INTO frontier_ranking VALUES "
            "('account-1', 'frontier', 999, 'Legacy-Group', 5, 10, 0, '')"
        )
        conn.commit()

        selected = select_accounts_by_handle(conn, ["example"])

    assert len(selected) == 1
    assert selected[0]["info_value"] == 0.0
    assert selected[0]["top_community"] == "unknown"
    assert selected[0]["proximity"] == "manual"
