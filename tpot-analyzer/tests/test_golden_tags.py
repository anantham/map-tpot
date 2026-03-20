"""Tests for tweet tagging endpoints and store methods."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.golden import golden_bp
import src.api.routes.golden as golden_routes
from src.archive.store import SCHEMA as ARCHIVE_SCHEMA
from src.data.golden_store import GoldenStore


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def golden_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    """Flask app with archive_tweets.db seeded with sample data."""
    db_path = tmp_path / "archive_tweets.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(ARCHIVE_SCHEMA)
        tweets = []
        for idx in range(1, 6):
            tweet_id = f"t{idx:03d}"
            tweets.append((
                tweet_id, f"acct_{idx:03d}", f"user_{idx:03d}",
                f"tweet text {idx}", f"2026-02-{idx:02d}T00:00:00+00:00",
                None, None, 0, 0, "en", 0, "2026-02-25T00:00:00+00:00",
            ))
        conn.executemany(
            """INSERT INTO tweets
            (tweet_id, account_id, username, full_text, created_at, reply_to_tweet_id,
             reply_to_username, favorite_count, retweet_count, lang, is_note_tweet, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tweets,
        )
        conn.commit()

    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.delenv("GOLDEN_INTERPRET_ALLOWED_MODELS", raising=False)
    monkeypatch.delenv("GOLDEN_INTERPRET_ALLOW_REMOTE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    golden_routes._golden_store = None

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(golden_bp)
    return app


@pytest.fixture
def store(tmp_path: Path) -> GoldenStore:
    """Standalone GoldenStore with an archive_tweets.db for unit tests."""
    db_path = tmp_path / "archive_tweets.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(ARCHIVE_SCHEMA)
        conn.execute(
            """INSERT INTO tweets
            (tweet_id, account_id, username, full_text, created_at,
             favorite_count, retweet_count, lang, is_note_tweet, fetched_at)
            VALUES ('tw1', 'a1', 'u1', 'hello', '2026-01-01', 0, 0, 'en', 0, '2026-01-01')"""
        )
        conn.commit()
    return GoldenStore(db_path)


# ─── Store unit tests ────────────────────────────────────────────────────────

class TestTagMixin:
    def test_save_and_retrieve_tags(self, store: GoldenStore) -> None:
        count = store.save_tags(tweet_id="tw1", tags=["alignment", "RLHF", "AI safety"])
        assert count == 3

        tags = store.get_tags_for_tweet("tw1")
        assert len(tags) == 3
        tag_names = [t["tag"] for t in tags]
        assert "alignment" in tag_names
        assert "rlhf" in tag_names  # lowercased
        assert "ai safety" in tag_names

    def test_save_tags_deduplicates(self, store: GoldenStore) -> None:
        count = store.save_tags(tweet_id="tw1", tags=["alignment", "ALIGNMENT", " alignment "])
        assert count == 1

        tags = store.get_tags_for_tweet("tw1")
        assert len(tags) == 1

    def test_save_tags_upserts(self, store: GoldenStore) -> None:
        store.save_tags(tweet_id="tw1", tags=["alignment"])
        store.save_tags(tweet_id="tw1", tags=["alignment", "rlhf"])
        tags = store.get_tags_for_tweet("tw1")
        assert len(tags) == 2

    def test_save_tags_with_category(self, store: GoldenStore) -> None:
        store.save_tags(tweet_id="tw1", tags=["alignment"], category="ai safety")
        tags = store.get_tags_for_tweet("tw1")
        assert tags[0]["category"] == "ai safety"

    def test_save_tags_skips_empty(self, store: GoldenStore) -> None:
        count = store.save_tags(tweet_id="tw1", tags=["", "  ", "valid"])
        assert count == 1
        tags = store.get_tags_for_tweet("tw1")
        assert tags[0]["tag"] == "valid"

    def test_save_tags_empty_list(self, store: GoldenStore) -> None:
        count = store.save_tags(tweet_id="tw1", tags=[])
        assert count == 0

    def test_save_tags_requires_tweet_id(self, store: GoldenStore) -> None:
        with pytest.raises(ValueError, match="tweet_id is required"):
            store.save_tags(tweet_id="", tags=["x"])

    def test_save_tags_requires_list(self, store: GoldenStore) -> None:
        with pytest.raises(ValueError, match="tags must be a list"):
            store.save_tags(tweet_id="tw1", tags="not a list")

    def test_get_tags_returns_empty_for_untagged(self, store: GoldenStore) -> None:
        tags = store.get_tags_for_tweet("nonexistent")
        assert tags == []

    def test_vocabulary(self, store: GoldenStore) -> None:
        store.save_tags(tweet_id="tw1", tags=["alignment", "rlhf"])
        # Tag a second "tweet" (even if not in tweets table, tweet_tags doesn't FK)
        store.save_tags(tweet_id="tw2", tags=["alignment", "forecasting"])
        store.save_tags(tweet_id="tw3", tags=["alignment"])

        vocab = store.get_tag_vocabulary()
        assert len(vocab) >= 3
        # alignment has count 3, rlhf 1, forecasting 1
        assert vocab[0]["tag"] == "alignment"
        assert vocab[0]["count"] == 3

    def test_remove_tag(self, store: GoldenStore) -> None:
        store.save_tags(tweet_id="tw1", tags=["alignment", "rlhf"])
        removed = store.remove_tag(tweet_id="tw1", tag="rlhf")
        assert removed is True

        tags = store.get_tags_for_tweet("tw1")
        assert len(tags) == 1
        assert tags[0]["tag"] == "alignment"

    def test_remove_nonexistent_tag(self, store: GoldenStore) -> None:
        removed = store.remove_tag(tweet_id="tw1", tag="nonexistent")
        assert removed is False

    def test_seed_community_tags_without_community_table(self, store: GoldenStore) -> None:
        # community table doesn't exist, should return 0
        count = store.seed_community_tags()
        assert count == 0

    def test_seed_community_tags(self, tmp_path: Path) -> None:
        db_path = tmp_path / "seed_test.db"
        with sqlite3.connect(db_path) as conn:
            conn.executescript(ARCHIVE_SCHEMA)
            conn.execute(
                """INSERT INTO tweets
                (tweet_id, account_id, username, full_text, created_at,
                 favorite_count, retweet_count, lang, is_note_tweet, fetched_at)
                VALUES ('tw1', 'a1', 'u1', 'hello', '2026-01-01', 0, 0, 'en', 0, '2026-01-01')"""
            )
            # Create community table
            conn.execute("""CREATE TABLE IF NOT EXISTS community (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                color TEXT
            )""")
            conn.executemany(
                "INSERT INTO community (id, name, color) VALUES (?, ?, ?)",
                [(1, "EA, AI Safety & Forecasting", "#ff0000"),
                 (2, "LLM Whisperers", "#00ff00")],
            )
            conn.commit()

        s = GoldenStore(db_path)
        count = s.seed_community_tags()
        assert count == 2

        vocab = s.get_tag_vocabulary()
        tag_names = [v["tag"] for v in vocab]
        assert "ea, ai safety & forecasting" in tag_names
        assert "llm whisperers" in tag_names
        # They should have category='community'
        for v in vocab:
            assert v["category"] == "community"


# ─── Route integration tests ─────────────────────────────────────────────────

class TestTagRoutes:
    @pytest.mark.integration
    def test_save_and_get_tags(self, golden_app: Flask) -> None:
        client = golden_app.test_client()

        resp = client.post("/api/golden/tags", json={
            "tweet_id": "t001",
            "tags": ["alignment", "RLHF", "AI safety"],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["count"] == 3

        resp = client.get("/api/golden/tags/t001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["tweetId"] == "t001"
        assert len(data["tags"]) == 3

    @pytest.mark.integration
    def test_save_tags_validation(self, golden_app: Flask) -> None:
        client = golden_app.test_client()

        # Missing tweet_id
        resp = client.post("/api/golden/tags", json={"tags": ["x"]})
        assert resp.status_code == 400
        assert "tweet_id" in resp.get_json()["error"]

        # Missing tags
        resp = client.post("/api/golden/tags", json={"tweet_id": "t001"})
        assert resp.status_code == 400
        assert "tags" in resp.get_json()["error"]

        # Tags not a list
        resp = client.post("/api/golden/tags", json={"tweet_id": "t001", "tags": "oops"})
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_vocabulary(self, golden_app: Flask) -> None:
        client = golden_app.test_client()

        # Tag two tweets
        client.post("/api/golden/tags", json={"tweet_id": "t001", "tags": ["alignment", "rlhf"]})
        client.post("/api/golden/tags", json={"tweet_id": "t002", "tags": ["alignment"]})

        resp = client.get("/api/golden/tags/vocabulary")
        assert resp.status_code == 200
        vocab = resp.get_json()["tags"]
        assert len(vocab) >= 2
        assert vocab[0]["tag"] == "alignment"
        assert vocab[0]["count"] == 2

    @pytest.mark.integration
    def test_delete_tag(self, golden_app: Flask) -> None:
        client = golden_app.test_client()
        client.post("/api/golden/tags", json={"tweet_id": "t001", "tags": ["alignment", "rlhf"]})

        resp = client.delete("/api/golden/tags/t001/rlhf")
        assert resp.status_code == 200
        assert resp.get_json()["removed"] is True

        tags = client.get("/api/golden/tags/t001").get_json()["tags"]
        assert len(tags) == 1
        assert tags[0]["tag"] == "alignment"

    @pytest.mark.integration
    def test_delete_nonexistent_tag(self, golden_app: Flask) -> None:
        client = golden_app.test_client()
        resp = client.delete("/api/golden/tags/t001/nosuch")
        assert resp.status_code == 200
        assert resp.get_json()["removed"] is False

    @pytest.mark.integration
    def test_get_tags_for_untagged_tweet(self, golden_app: Flask) -> None:
        client = golden_app.test_client()
        resp = client.get("/api/golden/tags/t999")
        assert resp.status_code == 200
        assert resp.get_json()["tags"] == []
