from __future__ import annotations

import os
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
    monkeypatch.setenv("MAP_TPOT_ARCHIVE_SOURCE", "local_custody")

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
            "source": "archive",
            "fetchSource": None,
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
@pytest.mark.parametrize("archive_present", [True, False])
def test_dossier_includes_acquired_posts_in_date_order_without_duplicates(
    dossier_client, archive_present,
) -> None:
    db_path = Path(os.environ["ARCHIVE_DB_PATH"])
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE enriched_tweets (
            tweet_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
            username TEXT NOT NULL, text TEXT NOT NULL,
            like_count INTEGER DEFAULT 0, retweet_count INTEGER DEFAULT 0,
            created_at TEXT, fetch_source TEXT NOT NULL, fetched_at TEXT NOT NULL
        )""")
        conn.executemany("INSERT INTO enriched_tweets VALUES (?,?,?,?,?,?,?,?,?)", [
            ("enriched-z", "acct-00", "RomeoStevens76", "New stored post", 7, 1,
             "Wed Jul 29 12:00:00 +0000 2026", "last_tweets", "2026-07-30"),
            ("enriched-a", "acct-00", "RomeoStevens76", "Same date post", 1, 0,
             "2026-07-29T12:00:00+00:00", "advanced_search", "2026-07-30"),
            ("tweet-new", "acct-00", "RomeoStevens76", "Duplicate acquired post", 12, 3,
             "Mon Jul 27 12:00:00 +0000 2026", "last_tweets", "2026-07-30"),
            ("enriched-undated", "acct-00", "RomeoStevens76", "Undated post", 0, 0,
             "not-a-date", "archive", "2026-07-30"),
            ("unrelated", "another-account", "another", "Other account post", 0, 0,
             "Fri Jul 31 12:00:00 +0000 2026", "last_tweets", "2026-07-31"),
        ])
        if not archive_present:
            conn.execute("DELETE FROM tweets")
    before = db_path.read_bytes()
    response = dossier_client.get("/api/research-notes/dossiers/RomeoStevens76?limit=3")
    assert response.status_code == 200
    posts = response.get_json()["tweets"]
    assert [post["tweetId"] for post in posts] == ["enriched-z", "enriched-a", "tweet-new"]
    assert posts[0] == {
        "tweetId": "enriched-z", "text": "New stored post",
        "createdAt": "Wed Jul 29 12:00:00 +0000 2026", "favoriteCount": 7,
        "retweetCount": 1, "fetchedAt": "2026-07-30",
        "source": "enriched", "fetchSource": "last_tweets",
    }
    assert posts[2]["source"] == ("archive" if archive_present else "enriched")
    assert posts[2]["text"] == (
        "A newer authored post" if archive_present else "Duplicate acquired post"
    )
    all_posts = dossier_client.get("/api/research-notes/dossiers/RomeoStevens76").get_json()["tweets"]
    assert all_posts[-1]["tweetId"] == "enriched-undated"
    assert len(all_posts) == (5 if archive_present else 4)
    assert len({post["tweetId"] for post in all_posts}) == len(all_posts)
    assert db_path.read_bytes() == before


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
