from __future__ import annotations

import pytest

from src.data.feed_scope_policy import FeedScopePolicyStore


@pytest.mark.integration
def test_feed_scope_policy_defaults_and_updates(tmp_path) -> None:
    store = FeedScopePolicyStore(tmp_path / "feed_signals.db")

    default_policy = store.get_policy(workspace_id="default", ego="adityaarpitha")
    assert default_policy.ingestion_mode == "open"
    assert default_policy.retention_mode == "infinite"
    assert default_policy.processing_mode == "continuous"
    assert default_policy.allowlist_enabled is False
    assert default_policy.firehose_enabled is True

    updated = store.upsert_policy(
        workspace_id="default",
        ego="adityaarpitha",
        ingestion_mode="guarded",
        allowlist_enabled=True,
        allowlist_accounts=["acct_1", "acct_1", "acct_2"],
        allowlist_tags=["trusted", " trusted "],
        firehose_path="~/tmp/indra.ndjson",
    )
    assert updated.ingestion_mode == "guarded"
    assert updated.allowlist_enabled is True
    assert updated.allowlist_accounts == ["acct_1", "acct_2"]
    assert updated.allowlist_tags == ["trusted"]
    assert updated.firehose_path

    loaded = store.get_policy(workspace_id="default", ego="adityaarpitha")
    assert loaded.ingestion_mode == "guarded"
    assert loaded.allowlist_accounts == ["acct_1", "acct_2"]


@pytest.mark.unit
def test_feed_scope_policy_validates_modes_and_types(tmp_path) -> None:
    store = FeedScopePolicyStore(tmp_path / "feed_signals.db")

    with pytest.raises(ValueError, match="ingestionMode must be one of"):
        store.upsert_policy(workspace_id="default", ego="adityaarpitha", ingestion_mode="invalid")
    with pytest.raises(ValueError, match="allowlistEnabled must be boolean"):
        store.upsert_policy(workspace_id="default", ego="adityaarpitha", allowlist_enabled="true")
    with pytest.raises(ValueError, match="allowlistAccounts must be an array"):
        store.upsert_policy(workspace_id="default", ego="adityaarpitha", allowlist_accounts="acct_1")
