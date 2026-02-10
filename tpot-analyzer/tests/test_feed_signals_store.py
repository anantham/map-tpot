from __future__ import annotations

import pytest

from src.data.feed_signals import FeedSignalsStore


@pytest.mark.integration
def test_feed_signals_ingest_dedup_and_summary(tmp_path) -> None:
    store = FeedSignalsStore(tmp_path / "feed_signals.db")

    events = [
        {
            "accountId": "acct_1",
            "username": "alice",
            "tweetId": "tweet_1",
            "tweetText": "Meditation and meaning are central themes",
            "surface": "home",
            "position": 1,
            "seenAt": "2026-02-10T01:00:00Z",
        },
        {
            "accountId": "acct_1",
            "username": "alice",
            "tweetId": "tweet_1",
            "tweetText": "Meditation and meaning are central themes",
            "surface": "home",
            "position": 1,
            "seenAt": "2026-02-10T01:00:00Z",
        },  # exact duplicate
        {
            "accountId": "acct_1",
            "username": "alice",
            "tweetId": "tweet_1",
            "tweetText": "Meditation and meaning are central themes",
            "surface": "home",
            "position": 3,
            "seenAt": "2026-02-10T02:00:00Z",
        },
        {
            "accountId": "acct_2",
            "username": "bob",
            "tweetText": "No tweet id but still an impression",
            "surface": "following",
            "position": 2,
            "seenAt": "2026-02-10T03:00:00Z",
        },
        {
            "username": "invalid_missing_account_id",
            "tweetText": "This should fail validation",
            "seenAt": "2026-02-10T03:00:00Z",
        },
    ]

    ingest = store.ingest_events(
        workspace_id="default",
        ego="adityaarpitha",
        events=events,
        collect_inserted_keys=True,
    )
    assert ingest["total"] == 5
    assert ingest["inserted"] == 3
    assert ingest["duplicates"] == 1
    assert ingest["failed"] == 1
    assert len(ingest["errors"]) == 1
    assert len(ingest["insertedEventKeys"]) == 3

    summary = store.account_summary(
        workspace_id="default",
        ego="adityaarpitha",
        account_id="acct_1",
        days=365,
        keyword_limit=10,
        sample_limit=5,
    )
    assert summary["impressions"] == 2
    assert summary["uniqueTweetsSeen"] == 1
    assert summary["tweetSamples"][0]["tweetId"] == "tweet_1"
    assert summary["tweetSamples"][0]["seenCount"] == 2
    assert any(item["surface"] == "home" and item["count"] == 2 for item in summary["surfaceCounts"])
    terms = {item["term"] for item in summary["topKeywords"]}
    assert "meditation" in terms
    assert "meaning" in terms

    top_accounts = store.top_exposed_accounts(
        workspace_id="default",
        ego="adityaarpitha",
        days=365,
        limit=10,
    )
    assert top_accounts[0]["accountId"] == "acct_1"
    assert top_accounts[0]["impressions"] == 2
    assert any(row["accountId"] == "acct_2" and row["impressions"] == 1 for row in top_accounts)


@pytest.mark.unit
def test_feed_signals_reject_non_positive_day_window(tmp_path) -> None:
    store = FeedSignalsStore(tmp_path / "feed_signals.db")
    with pytest.raises(ValueError, match="days must be > 0"):
        store.top_exposed_accounts(workspace_id="default", ego="adityaarpitha", days=0, limit=10)
