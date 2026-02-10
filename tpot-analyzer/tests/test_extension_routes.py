from __future__ import annotations

import json
from pathlib import Path

from flask import Flask
import pytest

from src.api.routes.extension import extension_bp
from src.api.routes.extension_runtime import reset_extension_runtime
from src.data.account_tags import AccountTagStore


@pytest.fixture
def extension_app(monkeypatch, tmp_path) -> Flask:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SNAPSHOT_DIR", str(snapshot_dir))
    reset_extension_runtime()
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(extension_bp)
    return app


@pytest.mark.unit
def test_extension_ingest_validates_scope_and_body(extension_app) -> None:
    client = extension_app.test_client()

    missing_ego = client.post("/api/extension/feed_events", json={"events": []})
    assert missing_ego.status_code == 400
    assert "ego" in missing_ego.get_json()["error"]

    bad_body = client.post("/api/extension/feed_events?ego=adityaarpitha", json={"events": "oops"})
    assert bad_body.status_code == 400
    assert "events must be an array" in bad_body.get_json()["error"]


@pytest.mark.integration
def test_extension_settings_default_and_update(extension_app) -> None:
    client = extension_app.test_client()
    scope = "ego=adityaarpitha&workspace_id=default"

    default_resp = client.get(f"/api/extension/settings?{scope}")
    assert default_resp.status_code == 200
    defaults = default_resp.get_json()
    assert defaults["ingestionMode"] == "open"
    assert defaults["retentionMode"] == "infinite"
    assert defaults["processingMode"] == "continuous"
    assert defaults["allowlistEnabled"] is False

    update_resp = client.put(
        f"/api/extension/settings?{scope}",
        json={
            "allowlistEnabled": True,
            "allowlistAccounts": ["acct_1", "acct_1", "acct_2"],
            "allowlistTags": ["trusted", " trusted "],
            "firehoseEnabled": True,
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()["settings"]
    assert updated["allowlistEnabled"] is True
    assert updated["allowlistAccounts"] == ["acct_1", "acct_2"]
    assert updated["allowlistTags"] == ["trusted"]


@pytest.mark.integration
def test_extension_ingest_raw_and_firehose_roundtrip(extension_app) -> None:
    client = extension_app.test_client()
    scope = "ego=adityaarpitha&workspace_id=default"

    ingest_resp = client.post(
        f"/api/extension/feed_events?{scope}",
        json={
            "events": [
                {
                    "accountId": "acct_1",
                    "username": "alice",
                    "tweetId": "tweet_1",
                    "tweetText": "Post-rational themes and meditation memes",
                    "surface": "home",
                    "position": 1,
                    "seenAt": "2026-02-10T00:00:00Z",
                },
                {
                    "accountId": "acct_1",
                    "username": "alice",
                    "tweetId": "tweet_2",
                    "tweetText": "Kegan stage discourse appears again",
                    "surface": "home",
                    "position": 4,
                    "seenAt": "2026-02-10T01:00:00Z",
                },
                {
                    "accountId": "acct_2",
                    "username": "bob",
                    "tweetId": "tweet_3",
                    "tweetText": "AI safety doomposting",
                    "surface": "following",
                    "position": 2,
                    "seenAt": "2026-02-10T01:30:00Z",
                },
            ]
        },
    )
    assert ingest_resp.status_code == 200
    ingest_payload = ingest_resp.get_json()
    assert ingest_payload["status"] == "ok"
    assert ingest_payload["ingest"]["inserted"] == 3
    assert ingest_payload["firehose"]["written"] == 3

    raw_resp = client.get(f"/api/extension/feed_events/raw?{scope}&limit=10")
    assert raw_resp.status_code == 200
    raw_payload = raw_resp.get_json()
    assert len(raw_payload["events"]) == 3
    assert isinstance(raw_payload["events"][0]["rawPayload"], dict)

    firehose_path = Path(ingest_payload["firehose"]["path"])
    assert firehose_path.exists()
    lines = firehose_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    first = json.loads(lines[0])
    assert first["eventType"] == "feed_impression"

    summary_resp = client.get(f"/api/extension/accounts/acct_1/summary?{scope}&days=365")
    assert summary_resp.status_code == 200
    summary = summary_resp.get_json()
    assert summary["impressions"] == 2
    assert summary["uniqueTweetsSeen"] == 2

    top_resp = client.get(f"/api/extension/exposure/top?{scope}&days=365&limit=5")
    assert top_resp.status_code == 200
    top_payload = top_resp.get_json()
    assert top_payload["accounts"][0]["accountId"] == "acct_1"
    assert top_payload["accounts"][0]["impressions"] == 2


@pytest.mark.integration
def test_extension_allowlist_filters_firehose_not_storage(extension_app) -> None:
    client = extension_app.test_client()
    scope = "ego=adityaarpitha&workspace_id=default"

    settings_resp = client.put(
        f"/api/extension/settings?{scope}",
        json={"allowlistEnabled": True, "allowlistAccounts": ["acct_allowed"]},
    )
    assert settings_resp.status_code == 200

    ingest_resp = client.post(
        f"/api/extension/feed_events?{scope}",
        json={
            "events": [
                {"accountId": "acct_allowed", "tweetId": "tweet_allow", "seenAt": "2026-02-10T00:00:00Z"},
                {"accountId": "acct_blocked", "tweetId": "tweet_block", "seenAt": "2026-02-10T00:01:00Z"},
            ]
        },
    )
    assert ingest_resp.status_code == 200
    payload = ingest_resp.get_json()
    assert payload["ingest"]["inserted"] == 2
    assert payload["firehose"]["written"] == 1
    assert payload["firehose"]["filteredOut"] == 1

    raw_resp = client.get(f"/api/extension/feed_events/raw?{scope}&limit=10")
    assert raw_resp.status_code == 200
    account_ids = {row["accountId"] for row in raw_resp.get_json()["events"]}
    assert {"acct_allowed", "acct_blocked"}.issubset(account_ids)


@pytest.mark.integration
def test_extension_purge_by_tag_scope(extension_app, tmp_path) -> None:
    client = extension_app.test_client()
    scope = "ego=adityaarpitha&workspace_id=default"
    snapshot_dir = tmp_path / "snapshot"
    tag_store = AccountTagStore(snapshot_dir / "account_tags.db")
    tag_store.upsert_tag(
        ego="adityaarpitha",
        account_id="acct_sensitive",
        tag="sensitive",
        polarity=1,
    )

    ingest_resp = client.post(
        f"/api/extension/feed_events?{scope}",
        json={
            "events": [
                {"accountId": "acct_sensitive", "tweetId": "tweet_1", "seenAt": "2026-02-10T00:00:00Z"},
                {"accountId": "acct_other", "tweetId": "tweet_2", "seenAt": "2026-02-10T00:01:00Z"},
            ]
        },
    )
    assert ingest_resp.status_code == 200

    dry_run = client.post(
        f"/api/extension/feed_events/purge_by_tag?{scope}",
        json={"tag": "sensitive", "dryRun": True},
    )
    assert dry_run.status_code == 200
    assert dry_run.get_json()["accountCount"] == 1

    purge = client.post(
        f"/api/extension/feed_events/purge_by_tag?{scope}",
        json={"tag": "sensitive"},
    )
    assert purge.status_code == 200
    purge_payload = purge.get_json()
    assert purge_payload["accountCount"] == 1
    assert purge_payload["deletedEvents"] >= 1

    top_resp = client.get(f"/api/extension/exposure/top?{scope}&days=365&limit=10")
    assert top_resp.status_code == 200
    accounts = {row["accountId"] for row in top_resp.get_json()["accounts"]}
    assert "acct_sensitive" not in accounts
    assert "acct_other" in accounts


@pytest.mark.integration
def test_guarded_mode_requires_token(extension_app, monkeypatch) -> None:
    client = extension_app.test_client()
    scope = "ego=adityaarpitha&workspace_id=default"

    set_guarded = client.put(
        f"/api/extension/settings?{scope}",
        json={"ingestionMode": "guarded"},
    )
    assert set_guarded.status_code == 200

    no_token_resp = client.post(f"/api/extension/feed_events?{scope}", json={"events": []})
    assert no_token_resp.status_code == 503  # guarded mode misconfigured until token is set

    monkeypatch.setenv("TPOT_EXTENSION_TOKEN", "local-secret")
    bad_token = client.post(
        f"/api/extension/feed_events?{scope}",
        json={"events": []},
        headers={"X-TPOT-Extension-Token": "wrong"},
    )
    assert bad_token.status_code == 401

    ok = client.post(
        f"/api/extension/feed_events?{scope}",
        json={"events": []},
        headers={"X-TPOT-Extension-Token": "local-secret"},
    )
    assert ok.status_code == 200
