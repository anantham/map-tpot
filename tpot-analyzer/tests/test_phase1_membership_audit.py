from __future__ import annotations

import json
import sqlite3
import csv
from pathlib import Path
from types import SimpleNamespace

from scripts.import_phase1_gold_labels import validate_pending_rows
import scripts.run_phase1_membership_audit as audit_runner
from scripts.phase1_community_audit.db import connect_db, load_sample_posts
from scripts.phase1_community_audit.io import (
    load_review_csv,
    merge_grok_results_into_review_csv,
    write_review_csv,
)
from scripts.phase1_community_audit.prompting import normalize_membership_result, parse_json_content


def test_parse_membership_response_strips_code_fences() -> None:
    raw = """```json
    {
      "tpot_status": "adjacent",
      "top_communities": [{"community": "LLM-Whisperers", "score": 0.82}],
      "bridge_account": false,
      "confidence": 0.61,
      "rationale": "mentions ```inline``` code"
    }
    ```"""
    parsed = parse_json_content(raw)
    normalized = normalize_membership_result(parsed)
    assert normalized["tpot_status"] == "adjacent"
    assert normalized["top_communities"][0]["community"] == "LLM-Whisperers"
    assert normalized["confidence"] == 0.61
    assert normalized["rationale"] == "mentions ```inline``` code"


def test_load_sample_posts_falls_back_to_enriched_tweets(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE tweets (
            tweet_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            username TEXT NOT NULL,
            full_text TEXT NOT NULL,
            created_at TEXT,
            favorite_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0
        );
        CREATE TABLE enriched_tweets (
            tweet_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            username TEXT NOT NULL,
            text TEXT NOT NULL,
            like_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            created_at TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO enriched_tweets (tweet_id, account_id, username, text, like_count, retweet_count, view_count, created_at)
        VALUES ('e1', 'acct-1', 'user1', 'fallback text', 4, 1, 99, '2026-03-26')
        """
    )
    conn.commit()
    conn.close()

    audit_conn = connect_db(db_path)
    try:
        posts = load_sample_posts(audit_conn, account_id="acct-1", limit=2)
    finally:
        audit_conn.close()

    assert len(posts) == 1
    assert posts[0]["source"] == "enriched_tweets"
    assert posts[0]["text"] == "fallback text"


def test_merge_grok_results_preserves_human_columns(tmp_path: Path) -> None:
    review_csv = tmp_path / "review.csv"
    manifest = [
        {
            "review_id": "row-1",
            "bucket": "core",
            "username": "alice",
            "display_name": "Alice",
            "account_id": "1",
            "target_community_short_name": "AI-Safety",
            "target_community_id": "community-1",
            "likely_confusions": ["Tech-Intellectuals"],
            "expected_judgment": "in",
        }
    ]
    write_review_csv(review_csv, manifest)

    rows = load_review_csv(review_csv)
    rows[0]["review_reason"] = "custom reviewer column"
    rows[0]["human_judgment"] = "in"
    rows[0]["human_note"] = "strong signal"
    with review_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    merge_grok_results_into_review_csv(
        review_csv,
        {
            "row-1": {
                "tpot_status": "in",
                "top_communities": [{"community": "AI-Safety", "score": 0.97}],
                "confidence": 0.88,
                "bridge_account": False,
                "rationale": "clear fit",
            }
        },
    )

    merged = load_review_csv(review_csv)
    assert merged[0]["grok_tpot_status"] == "in"
    assert merged[0]["grok_top_communities"] == "AI-Safety:0.970"
    assert merged[0]["human_judgment"] == "in"
    assert merged[0]["human_note"] == "strong signal"
    assert merged[0]["review_reason"] == "custom reviewer column"


def test_validate_pending_rows_rejects_bad_judgment_before_write() -> None:
    with_communities = {
        "AI-Safety": {
            "id": "community-1",
            "short_name": "AI-Safety",
            "name": "AI Safety",
            "description": "",
        }
    }
    rows = [
        {
            "review_id": "row-1",
            "target_community_id": "community-1",
            "target_community_short_name": "AI-Safety",
            "human_judgment": "definitely",
            "human_confidence": "0.7",
        }
    ]
    try:
        validate_pending_rows(
            rows,
            communities=with_communities,
            community_id_to_short={"community-1": "AI-Safety"},
        )
    except ValueError as exc:
        assert "judgment must be one of" in str(exc)
    else:
        raise AssertionError("Expected validate_pending_rows to reject invalid human_judgment")


def test_run_membership_mode_writes_error_sentinel_on_bad_json(tmp_path: Path, monkeypatch) -> None:
    class DummyConn:
        def close(self) -> None:
            return None

    manifest = [
        {
            "review_id": "row-1",
            "bucket": "core",
            "username": "alice",
            "bio": "bio",
            "sample_posts": [],
            "target_community_short_name": "AI-Safety",
        }
    ]
    review_csv = tmp_path / "review.csv"
    write_review_csv(
        review_csv,
        [
            {
                "review_id": "row-1",
                "bucket": "core",
                "username": "alice",
                "display_name": "Alice",
                "account_id": "1",
                "target_community_short_name": "AI-Safety",
                "target_community_id": "community-1",
                "likely_confusions": [],
                "expected_judgment": "in",
            }
        ],
    )
    results_path = tmp_path / "results.jsonl"

    monkeypatch.setattr(audit_runner, "load_template", lambda _path: "Account {{account_handle}} {{community_definitions}}")
    monkeypatch.setattr(audit_runner, "connect_db", lambda _path: DummyConn())
    monkeypatch.setattr(
        audit_runner,
        "load_community_lookup",
        lambda _conn: {"AI-Safety": {"short_name": "AI-Safety", "name": "AI Safety", "description": "desc"}},
    )
    monkeypatch.setattr(
        audit_runner,
        "call_openrouter",
        lambda **_kwargs: {"choices": [{"message": {"content": "{not json"}}], "usage": {}},
    )

    args = SimpleNamespace(
        db_path=tmp_path / "audit.db",
        bucket="",
        limit=0,
        dry_run=False,
        api_key="test-key",
        model="test-model",
        temperature=0.1,
        max_tokens=50,
        results_jsonl=results_path,
        review_csv=review_csv,
    )

    rc = audit_runner.run_membership_mode(args, manifest)
    assert rc == 0
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["tpot_status"] == "error"
    assert rows[0]["error_type"] == "JSONDecodeError"
