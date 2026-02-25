from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from src.api.routes.golden import golden_bp
import src.api.routes.golden as golden_routes
from src.archive.store import SCHEMA as ARCHIVE_SCHEMA


@pytest.fixture
def golden_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    db_path = tmp_path / "archive_tweets.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(ARCHIVE_SCHEMA)
        tweets = []
        for idx in range(1, 13):
            tweet_id = f"t{idx:03d}"
            reply_to = "parent_1" if tweet_id == "t003" else None
            tweets.append(
                (
                    tweet_id,
                    f"acct_{idx:03d}",
                    f"user_{idx:03d}",
                    f"tweet text {idx}",
                    f"2026-02-{idx:02d}T00:00:00+00:00",
                    reply_to,
                    None,
                    0,
                    0,
                    "en",
                    0,
                    "2026-02-25T00:00:00+00:00",
                )
            )
        conn.executemany(
            """
            INSERT INTO tweets
            (tweet_id, account_id, username, full_text, created_at, reply_to_tweet_id,
             reply_to_username, favorite_count, retweet_count, lang, is_note_tweet, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tweets,
        )
        conn.execute(
            "INSERT INTO thread_context_cache (tweet_id, raw_json, fetched_at) VALUES (?, ?, ?)",
            (
                "t003",
                json.dumps(
                    [
                        {"id": "parent_1", "author": {"userName": "other"}, "text": "parent context"},
                        {"id": "t003", "author": {"userName": "user_003"}, "text": "tweet text 3"},
                    ]
                ),
                "2026-02-25T00:00:00+00:00",
            ),
        )
        conn.commit()

    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path))
    golden_routes._golden_store = None

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(golden_bp)
    return app


@pytest.mark.integration
def test_candidates_bootstrap_splits_and_context(golden_app: Flask) -> None:
    client = golden_app.test_client()

    resp = client.get("/api/golden/candidates?axis=simulacrum&status=unlabeled&limit=50")
    assert resp.status_code == 200
    payload = resp.get_json()

    assert payload["axis"] == "simulacrum"
    assert payload["splitCounts"]["total"] == 12
    assert len(payload["candidates"]) == 12
    assert all(item["labelStatus"] == "unlabeled" for item in payload["candidates"])

    t003 = next(item for item in payload["candidates"] if item["tweetId"] == "t003")
    assert t003["threadContext"]
    assert t003["contextSource"] == "t003"


@pytest.mark.integration
def test_label_upsert_changes_candidate_status(golden_app: Flask) -> None:
    client = golden_app.test_client()

    label_payload = {
        "axis": "simulacrum",
        "tweet_id": "t001",
        "reviewer": "human",
        "distribution": {"l1": 0.7, "l2": 0.1, "l3": 0.2, "l4": 0.0},
        "note": "initial label",
    }
    resp = client.post("/api/golden/labels", json=label_payload)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"

    labeled = client.get("/api/golden/candidates?status=labeled&limit=50").get_json()["candidates"]
    unlabeled = client.get("/api/golden/candidates?status=unlabeled&limit=50").get_json()["candidates"]

    assert any(item["tweetId"] == "t001" for item in labeled)
    assert all(item["tweetId"] != "t001" for item in unlabeled)


@pytest.mark.integration
def test_predictions_queue_and_eval_roundtrip(golden_app: Flask, tmp_path: Path) -> None:
    client = golden_app.test_client()

    # Ensure split rows exist, then pin two labeled tweets to dev for deterministic eval coverage.
    bootstrap = client.get("/api/golden/candidates?status=all&limit=50")
    assert bootstrap.status_code == 200
    db_path = tmp_path / "archive_tweets.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE curation_split SET split = 'dev' WHERE axis = 'simulacrum' AND tweet_id IN ('t001', 't002')"
        )
        conn.commit()

    label_dist_1 = {"l1": 0.8, "l2": 0.1, "l3": 0.1, "l4": 0.0}
    label_dist_2 = {"l1": 0.2, "l2": 0.5, "l3": 0.3, "l4": 0.0}
    for tweet_id, dist in [("t001", label_dist_1), ("t002", label_dist_2)]:
        resp = client.post(
            "/api/golden/labels",
            json={
                "axis": "simulacrum",
                "tweet_id": tweet_id,
                "reviewer": "human",
                "distribution": dist,
            },
        )
        assert resp.status_code == 200

    model_a = client.post(
        "/api/golden/predictions/run",
        json={
            "axis": "simulacrum",
            "model_name": "model_a",
            "prompt_version": "v1",
            "run_id": "run_a",
            "predictions": [
                {"tweet_id": "t001", "distribution": label_dist_1},
                {"tweet_id": "t002", "distribution": label_dist_2},
                {"tweet_id": "t003", "distribution": {"l1": 0.1, "l2": 0.2, "l3": 0.7, "l4": 0.0}},
            ],
        },
    )
    assert model_a.status_code == 200
    assert model_a.get_json()["inserted"] == 3

    model_b = client.post(
        "/api/golden/predictions/run",
        json={
            "axis": "simulacrum",
            "model_name": "model_b",
            "prompt_version": "v1",
            "run_id": "run_b",
            "predictions": [
                {"tweet_id": "t003", "distribution": {"l1": 0.7, "l2": 0.1, "l3": 0.2, "l4": 0.0}},
            ],
        },
    )
    assert model_b.status_code == 200

    queue = client.get("/api/golden/queue?status=pending&limit=50")
    assert queue.status_code == 200
    pending_items = queue.get_json()["queue"]
    t003 = next(item for item in pending_items if item["tweetId"] == "t003")
    assert t003["disagreement"] > 0.0

    eval_resp = client.post(
        "/api/golden/eval/run",
        json={
            "axis": "simulacrum",
            "model_name": "model_a",
            "prompt_version": "v1",
            "split": "dev",
            "threshold": 0.18,
            "run_id": "eval_a_dev",
        },
    )
    assert eval_resp.status_code == 200
    eval_payload = eval_resp.get_json()
    assert eval_payload["status"] == "ok"
    assert eval_payload["sampleSize"] >= 2
    assert eval_payload["passed"] is True
    assert eval_payload["brierScore"] <= 0.18

    metrics = client.get("/api/golden/metrics")
    assert metrics.status_code == 200
    metrics_payload = metrics.get_json()
    assert metrics_payload["labeledCount"] >= 2
    assert "dev" in metrics_payload["latestEvaluation"]
