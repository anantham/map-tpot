"""Behavioral contracts for the reproducible local development runtime."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.dev_runtime import (
    DevRuntimeError,
    render_shell_assignments,
    resolve_dev_runtime,
)


def _archive_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE profiles "
            "(account_id TEXT, username TEXT, display_name TEXT, bio TEXT, "
            "location TEXT, website TEXT, fetched_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE tweets "
            "(tweet_id TEXT, account_id TEXT, full_text TEXT, created_at TEXT, "
            "favorite_count INTEGER, retweet_count INTEGER, fetched_at TEXT)"
        )
    return path


def test_resolves_archive_from_primary_worktree_when_local_placeholder_is_invalid(
    tmp_path: Path,
) -> None:
    project = tmp_path / "linked" / "tpot-analyzer"
    project_data = project / "data"
    project_data.mkdir(parents=True)
    (project_data / "archive_tweets.db").touch()

    primary = tmp_path / "primary"
    archive = _archive_db(primary / "tpot-analyzer" / "data" / "archive_tweets.db")

    runtime = resolve_dev_runtime(
        project,
        environ={},
        common_git_dir=primary / ".git",
    )

    assert runtime.archive_db == archive.resolve()
    assert runtime.snapshot_dir == project_data.resolve()
    assert runtime.account_tags_db == (project_data / "account_tags.db").resolve()
    assert runtime.ui_origin == "http://localhost:5184"
    assert runtime.api_origin == "http://localhost:5001"
    assert runtime.ui_origin in runtime.cors_origins


def test_explicit_invalid_archive_fails_instead_of_silently_falling_back(
    tmp_path: Path,
) -> None:
    project = tmp_path / "linked" / "tpot-analyzer"
    (project / "data").mkdir(parents=True)
    primary = tmp_path / "primary"
    _archive_db(primary / "tpot-analyzer" / "data" / "archive_tweets.db")
    missing = tmp_path / "operator-selected.db"

    with pytest.raises(DevRuntimeError, match=r"ARCHIVE_DB_PATH.*operator-selected"):
        resolve_dev_runtime(
            project,
            environ={"ARCHIVE_DB_PATH": str(missing)},
            common_git_dir=primary / ".git",
        )


def test_archive_requires_research_notes_schema(tmp_path: Path) -> None:
    project = tmp_path / "tpot-analyzer"
    (project / "data").mkdir(parents=True)
    malformed = project / "data" / "archive_tweets.db"
    with sqlite3.connect(malformed) as conn:
        conn.execute("CREATE TABLE unrelated (value TEXT)")

    with pytest.raises(DevRuntimeError, match=r"profiles.*tweets"):
        resolve_dev_runtime(project, environ={"ARCHIVE_DB_PATH": str(malformed)})


def test_archive_reports_missing_dossier_columns(tmp_path: Path) -> None:
    project = tmp_path / "tpot-analyzer"
    data_dir = project / "data"
    data_dir.mkdir(parents=True)
    malformed = data_dir / "archive_tweets.db"
    with sqlite3.connect(malformed) as conn:
        conn.execute("CREATE TABLE profiles (account_id TEXT, username TEXT)")
        conn.execute("CREATE TABLE tweets (tweet_id TEXT, account_id TEXT)")

    with pytest.raises(DevRuntimeError, match=r"profiles.*missing columns.*bio"):
        resolve_dev_runtime(project, environ={"ARCHIVE_DB_PATH": str(malformed)})


def test_explicit_snapshot_path_must_be_an_existing_directory(tmp_path: Path) -> None:
    project = tmp_path / "tpot-analyzer"
    data_dir = project / "data"
    data_dir.mkdir(parents=True)
    archive = _archive_db(data_dir / "archive_tweets.db")
    missing_state = tmp_path / "missing-state"

    with pytest.raises(DevRuntimeError, match=r"SNAPSHOT_DIR.*does not exist"):
        resolve_dev_runtime(
            project,
            environ={
                "ARCHIVE_DB_PATH": str(archive),
                "SNAPSHOT_DIR": str(missing_state),
            },
        )


def test_existing_tag_path_must_be_sqlite(tmp_path: Path) -> None:
    project = tmp_path / "tpot-analyzer"
    data_dir = project / "data"
    data_dir.mkdir(parents=True)
    archive = _archive_db(data_dir / "archive_tweets.db")
    (data_dir / "account_tags.db").write_text("not sqlite", encoding="utf-8")

    with pytest.raises(DevRuntimeError, match=r"account tag database.*valid SQLite"):
        resolve_dev_runtime(
            project,
            environ={"ARCHIVE_DB_PATH": str(archive)},
        )


def test_shell_contract_contains_paths_and_origins_but_no_curator_secret(
    tmp_path: Path,
) -> None:
    project = tmp_path / "tpot-analyzer"
    data_dir = project / "data"
    data_dir.mkdir(parents=True)
    archive = _archive_db(data_dir / "archive_tweets.db")
    secret = "must-never-appear-in-resolver-output"

    runtime = resolve_dev_runtime(
        project,
        environ={
            "ARCHIVE_DB_PATH": str(archive),
            "TPOT_CURATOR_TOKEN": secret,
        },
    )
    rendered = render_shell_assignments(runtime)

    assert "ARCHIVE_DB_PATH=" in rendered
    assert "SNAPSHOT_DIR=" in rendered
    assert "CORS_ORIGINS=" in rendered
    assert "VITE_API_URL=" in rendered
    assert secret not in rendered


def test_backend_default_cors_accepts_the_fixed_research_notes_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))

    from src.api.server import create_app

    client = create_app({"TESTING": True}).test_client()
    response = client.options(
        "/api/research-notes/dossiers/example",
        headers={
            "Origin": "http://localhost:5184",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-TPOT-Curator-Token",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == (
        "http://localhost:5184"
    )
