from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.api.server import create_app

CURATOR_TOKEN = "research-notes-test-token"


def _tweet(
    tweet_id: str,
    text: str,
    created_at: str | None,
    *,
    favorite_count: int = 0,
    retweet_count: int = 0,
) -> tuple[Any, ...]:
    return (
        tweet_id,
        "acct-00",
        text,
        created_at,
        favorite_count,
        retweet_count,
        created_at,
    )


def _seed_dossier_rows(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE profiles (
                account_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                display_name TEXT,
                bio TEXT,
                location TEXT,
                website TEXT,
                fetched_at TEXT
            );
            CREATE TABLE tweets (
                tweet_id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                full_text TEXT,
                created_at TEXT,
                favorite_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0,
                fetched_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO profiles
            (account_id, username, display_name, bio, location, website,
             fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "acct-00",
                "RomeoStevens76",
                "Romeo Stevens",
                "Meditation and minds",
                "Internet",
                "https://example.test/romeo",
                "2026-07-25T00:00:00+00:00",
            ),
        )
        conn.executemany(
            """
            INSERT INTO tweets
            (tweet_id, account_id, full_text, created_at, favorite_count,
             retweet_count, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                _tweet(
                    "tweet-new",
                    "A newer authored post",
                    "2026-07-27T12:00:00+00:00",
                    favorite_count=9,
                    retweet_count=2,
                ),
                _tweet(
                    "tweet-old",
                    "An older authored reply",
                    "2026-07-24T12:00:00+00:00",
                    favorite_count=3,
                ),
            ],
        )
        conn.commit()


@pytest.fixture
def dossier_client(
    tmp_path: Path,
    temp_snapshot_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    db_path = tmp_path / "archive tweets.db"
    _seed_dossier_rows(db_path)
    monkeypatch.setenv("ARCHIVE_DB_PATH", str(db_path))
    monkeypatch.setenv("TPOT_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("TPOT_CURATOR_TOKEN", CURATOR_TOKEN)

    app = create_app({"TESTING": True})
    with app.test_client() as client:
        client.environ_base["HTTP_X_TPOT_CURATOR_TOKEN"] = CURATOR_TOKEN
        yield client


@pytest.mark.integration
def test_dossier_requires_curator_auth(dossier_client) -> None:
    dossier_client.environ_base.pop("HTTP_X_TPOT_CURATOR_TOKEN")
    response = dossier_client.get(
        "/api/research-notes/dossiers/RomeoStevens76"
    )
    assert response.status_code == 401
    assert "curator token" in response.get_json()["error"]


@pytest.mark.integration
def test_unbound_dossier_is_case_insensitive_raw_and_blind(
    dossier_client,
) -> None:
    response = dossier_client.get(
        "/api/research-notes/dossiers/romeostevens76?limit=1"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["bindingStatus"] == "unbound"
    assert payload["provenance"] == {
        "source": "mutable_local_archive",
        "snapshotBound": False,
    }
    assert payload["account"] == {
        "accountId": "acct-00",
        "username": "RomeoStevens76",
        "displayName": "Romeo Stevens",
        "bio": "Meditation and minds",
        "location": "Internet",
        "website": "https://example.test/romeo",
        "fetchedAt": "2026-07-25T00:00:00+00:00",
    }
    assert payload["tweets"] == [
        {
            "tweetId": "tweet-new",
            "text": "A newer authored post",
            "createdAt": "2026-07-27T12:00:00+00:00",
            "favoriteCount": 9,
            "retweetCount": 2,
            "fetchedAt": "2026-07-27T12:00:00+00:00",
        }
    ]
    forbidden = {
        "community",
        "communities",
        "weight",
        "accountNote",
        "labels",
        "role",
        "snapshotId",
        "snapshotHash",
    }
    assert forbidden.isdisjoint(payload)


@pytest.mark.integration
def test_unknown_handle_returns_descriptive_404(dossier_client) -> None:
    response = dossier_client.get(
        "/api/research-notes/dossiers/does-not-exist"
    )
    assert response.status_code == 404
    assert "does-not-exist" in response.get_json()["error"]


@pytest.mark.integration
def test_dossier_rejects_unimplemented_frame_binding(dossier_client) -> None:
    response = dossier_client.get(
        "/api/research-notes/dossiers/RomeoStevens76?frameId=frame-a"
    )
    assert response.status_code == 400
    assert (
        "frame-bound dossiers are not implemented"
        in response.get_json()["error"]
    )


@pytest.mark.integration
@pytest.mark.parametrize("limit", ["0", "101", "not-a-number"])
def test_dossier_rejects_invalid_limits(dossier_client, limit: str) -> None:
    response = dossier_client.get(
        f"/api/research-notes/dossiers/RomeoStevens76?limit={limit}"
    )
    assert response.status_code == 400
    assert "limit" in response.get_json()["error"]
