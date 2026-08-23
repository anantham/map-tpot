from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
from src.archive.snapshot import DownloadRecord, RemoteObjectMetadata, build_snapshot_id
from src.archive.snapshot_manifest import (
    create_snapshot_manifest,
    inspect_enriched_tweets_parquet,
    write_snapshot_manifest,
)
from src.evaluation.seed_coverage import (
    build_seed_coverage_report,
)


def _price_card() -> dict:
    return {
        "schema_version": 1,
        "card_id": "test-card",
        "credits_per_usd": 100_000,
        "user_followings": {
            "maximum_page_size": 200,
            "minimum_call_credits": 60,
            "tiers": [
                {"returned_min": 20, "returned_max": 99, "credits_per_item": 3},
                {"returned_min": 100, "returned_max": 199, "credits_per_item": 2},
                {"returned_min": 200, "returned_max": 200, "credits_per_item": 1},
            ],
        },
    }


def _write_json(path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _snapshot(tmp_path, name: str, rows: dict) -> tuple:
    staged = tmp_path / f"{name}.parquet"
    pq.write_table(pa.table(rows), staged)
    size = staged.stat().st_size
    observed_at = "2026-07-30T00:00:00+00:00"
    last_modified = "2026-07-30T00:00:00+00:00"
    url = f"https://example.test/{name}.parquet"
    metadata = RemoteObjectMetadata(
        url=url,
        observed_at=observed_at,
        etag=f'"{name}"',
        last_modified=last_modified,
        content_length=size,
        content_type="application/octet-stream",
        snapshot_id=build_snapshot_id(
            url, f'"{name}"', last_modified, size, observed_at
        ),
    )
    snapshot_dir = tmp_path / metadata.snapshot_id
    snapshot_dir.mkdir()
    data_path = snapshot_dir / "enriched_tweets.parquet"
    staged.replace(data_path)
    download = DownloadRecord(
        data_path,
        size,
        hashlib.sha256(data_path.read_bytes()).hexdigest(),
    )
    manifest = create_snapshot_manifest(
        metadata,
        download,
        inspect_enriched_tweets_parquet(data_path),
        git_sha="test",
        git_dirty=False,
    )
    write_snapshot_manifest(snapshot_dir / "manifest.json", manifest)
    return snapshot_dir, manifest


def _archive_db(path, *, sparse: bool = False) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE account_following "
        "(account_id TEXT, following_account_id TEXT)"
    )
    if not sparse:
        db.execute(
            "CREATE TABLE account_followers "
            "(account_id TEXT, follower_account_id TEXT)"
        )
        db.executemany(
            "INSERT INTO account_following VALUES (?, ?)",
            [("1", "10"), ("1", "11"), ("2", "10")],
        )
        db.executemany(
            "INSERT INTO account_followers VALUES (?, ?)",
            [("10", "1"), ("12", "1")],
        )
    db.execute("CREATE TABLE profiles (account_id TEXT, username TEXT)")
    db.executemany(
        "INSERT INTO profiles VALUES (?, ?)",
        [("999", "Alpha"), ("10", "shared"), ("11", "direct_only")],
    )
    db.commit()
    db.close()


def _cache_db(path) -> None:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE account (account_id TEXT, username TEXT)")
    db.execute(
        "CREATE TABLE shadow_account (account_id TEXT, username TEXT)"
    )
    db.execute(
        "CREATE TABLE shadow_edge "
        "(source_id TEXT, target_id TEXT, direction TEXT, "
        "source_channel TEXT, fetched_at TEXT)"
    )
    db.executemany(
        "INSERT INTO shadow_edge VALUES (?, ?, ?, ?, ?)",
        [
            ("1", "10", "outbound", "fixture", "2026-01-01T00:00:00Z"),
            ("1", "shadow:beta", "outbound", "fixture", "2026-01-01T00:00:00Z"),
            ("shadow:alpha", "13", "inbound", "fixture", "2026-01-02T00:00:00Z"),
        ],
    )
    db.commit()
    db.close()


def _report_inputs(tmp_path, *, sparse: bool = False) -> dict:
    panel_path = tmp_path / "panel.json"
    _write_json(
        panel_path,
        {
            "schema_version": 1,
            "panel_id": "fixture",
            "panel_version": 1,
            "created_at": "2026-07-30T00:00:00Z",
            "scope": "retrieval probes, not labels",
            "seeds": [
                {
                    "account_id": "1",
                    "handle_at_freeze": "Alpha",
                    "claimed_following": 4,
                },
                {
                    "account_id": "2",
                    "handle_at_freeze": "Beta",
                    "claimed_following": 2,
                },
            ],
        },
    )
    price_path = tmp_path / "price.json"
    _write_json(price_path, _price_card())
    archive_path, cache_path = tmp_path / "archive.db", tmp_path / "cache.db"
    _archive_db(archive_path, sparse=sparse)
    _cache_db(cache_path)
    snapshot_dir, manifest = _snapshot(
        tmp_path,
        "selected",
        {
            "tweet_id": ["100", "101", "102", "103"],
            "account_id": ["1", "1", "3", "2"],
            "username": ["Alpha", "Alpha", "Other", "Beta"],
            "created_at": pa.array(
                [
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 2, 1, tzinfo=timezone.utc),
                    datetime(2026, 3, 1, tzinfo=timezone.utc),
                    datetime(2026, 4, 1, tzinfo=timezone.utc),
                ],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "full_text": ["post", "reply", "incoming", "beta"],
            "reply_to_user_id": [None, "20", "1", None],
            "reply_to_username": [None, "Target", "Alpha", None],
            "archive_upload_id": [1, 1, 2, 3],
        },
    )
    return {
        "seed_panel_path": panel_path,
        "cache_db_path": cache_path,
        "archive_db_path": archive_path,
        "archive_snapshot_dir": snapshot_dir,
        "api_price_card_path": price_path,
        "_snapshot_id": manifest["snapshot_id"],
    }


def test_report_separates_sources_deduplicates_and_pins_identity(tmp_path) -> None:
    inputs = _report_inputs(tmp_path)
    snapshot_id = inputs.pop("_snapshot_id")

    started_at = datetime.now(timezone.utc)
    report = build_seed_coverage_report(**inputs)
    finished_at = datetime.now(timezone.utc)

    alpha = next(row for row in report["seeds"] if row["account_id"] == "1")
    report_time = datetime.fromisoformat(report["generated_at"])
    assert started_at <= report_time <= finished_at
    assert alpha["identity"]["status"] == "conflicting"
    assert alpha["identity"]["conflicting_numeric_ids"] == ["999"]
    assert alpha["follows"]["merged_sqlite_direct"]["distinct_targets"] == 2
    assert alpha["follows"]["merged_sqlite_inverse"]["distinct_targets"] == 2
    assert alpha["follows"]["shadow_direct_following"]["distinct_targets"] == 2
    assert alpha["follows"]["shadow_inverse_following"]["distinct_targets"] == 1
    assert alpha["follows"]["stored_key_union"]["distinct_targets"] == 5
    assert "claimed_minus_stored_key_union" not in alpha["follows"]
    assert "observed_to_claimed_proxy" not in alpha["follows"]
    assert alpha["follows"]["full_refresh_estimate"]["estimated_credits"] == 60
    assert alpha["content"]["authored_rows"] == 2
    assert alpha["content"]["authored_reply_rows"] == 1
    assert alpha["content"]["incoming_nonself_reply_rows"] == 1
    assert report["inputs"]["archive_snapshot"]["snapshot_id"] == snapshot_id
    assert report["ranking"]["semantic_status"] == "uncalibrated_ranking_signal"
    assert report["ranking"]["top_candidates"][0]["account_id"] == "10"
    assert report["ranking"]["top_candidates"][0]["raw_support"] == 2
    assert "shadow:beta" not in {
        row["account_id"] for row in report["ranking"]["top_candidates"]
    }
    assert "membership_probability" not in json.dumps(report)
    assert "coverage_pct" not in json.dumps(report)


def test_missing_follow_table_is_unavailable_not_observed_zero(tmp_path) -> None:
    inputs = _report_inputs(tmp_path, sparse=True)
    inputs.pop("_snapshot_id")

    report = build_seed_coverage_report(**inputs)

    alpha = next(row for row in report["seeds"] if row["account_id"] == "1")
    assert alpha["follows"]["merged_sqlite_inverse"] == {
        "status": "unavailable",
        "distinct_targets": None,
        "reason": "missing table account_followers",
        "timestamp_status": "not_recorded",
    }
    assert alpha["follows"]["stored_key_union"]["status"] == "partial"
