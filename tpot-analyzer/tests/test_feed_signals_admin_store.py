from __future__ import annotations

import pytest

from src.data.feed_signals import FeedSignalsStore
from src.data.feed_signals_admin import FeedSignalsAdminStore


@pytest.mark.integration
def test_feed_signals_admin_raw_fetch_and_purge(tmp_path) -> None:
    db_path = tmp_path / "feed_signals.db"
    feed_store = FeedSignalsStore(db_path)
    admin_store = FeedSignalsAdminStore(db_path)

    ingest = feed_store.ingest_events(
        workspace_id="default",
        ego="adityaarpitha",
        events=[
            {
                "accountId": "acct_1",
                "tweetId": "tweet_1",
                "tweetText": "one",
                "seenAt": "2026-02-10T00:00:00Z",
            },
            {
                "accountId": "acct_2",
                "tweetId": "tweet_2",
                "tweetText": "two",
                "seenAt": "2026-02-10T00:01:00Z",
            },
        ],
        collect_inserted_keys=True,
    )
    keys = ingest["insertedEventKeys"]
    assert len(keys) == 2

    fetched = admin_store.fetch_events_by_keys(
        workspace_id="default",
        ego="adityaarpitha",
        event_keys=keys,
    )
    assert len(fetched) == 2
    assert {event["accountId"] for event in fetched} == {"acct_1", "acct_2"}

    raw_page = admin_store.list_raw_events(
        workspace_id="default",
        ego="adityaarpitha",
        limit=1,
    )
    assert len(raw_page["events"]) == 1
    assert raw_page["nextCursor"] is not None

    purged = admin_store.purge_events_for_accounts(
        workspace_id="default",
        ego="adityaarpitha",
        account_ids=["acct_1"],
    )
    assert purged["accountCount"] == 1
    assert purged["deletedEvents"] >= 1

    top_after = feed_store.top_exposed_accounts(
        workspace_id="default",
        ego="adityaarpitha",
        days=365,
        limit=10,
    )
    assert {row["accountId"] for row in top_after} == {"acct_2"}


@pytest.mark.unit
def test_feed_signals_admin_validates_cursor(tmp_path) -> None:
    admin_store = FeedSignalsAdminStore(tmp_path / "feed_signals.db")
    with pytest.raises(ValueError, match="before_seen_at must be ISO-8601"):
        admin_store.list_raw_events(
            workspace_id="default",
            ego="adityaarpitha",
            before_seen_at="not-a-timestamp",
        )
