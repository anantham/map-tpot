from __future__ import annotations

import sqlite3

import pytest

from src.data.account_tags import AccountTagStore


@pytest.mark.integration
def test_account_tag_store_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "account_tags.db"
    store = AccountTagStore(db_path)

    saved = store.upsert_tag(
        ego="ego1",
        account_id="123",
        tag="AI alignment",
        polarity=1,
        confidence=0.9,
    )
    assert saved.tag == "AI alignment"
    assert saved.polarity == 1
    assert saved.confidence == 0.9

    tags = store.list_tags(ego="ego1", account_id="123")
    assert len(tags) == 1
    assert tags[0].tag == "AI alignment"
    assert tags[0].polarity == 1

    # Case-insensitive upsert should update the existing row (tag_key uses casefold)
    saved2 = store.upsert_tag(
        ego="ego1",
        account_id="123",
        tag="ai alignment",
        polarity=-1,
        confidence=None,
    )
    assert saved2.polarity == -1

    tags2 = store.list_tags(ego="ego1", account_id="123")
    assert len(tags2) == 1
    assert tags2[0].polarity == -1

    distinct = store.list_distinct_tags(ego="ego1")
    assert "ai alignment" in distinct

    store.upsert_tag(ego="ego1", account_id="abc", tag="trusted", polarity=1)
    store.upsert_tag(ego="ego1", account_id="xyz", tag="trusted", polarity=1)
    store.upsert_tag(ego="ego1", account_id="xyz", tag="noise", polarity=-1)
    store.upsert_tag(ego="ego1", account_id="neg_only", tag="blocked", polarity=-1)
    assert store.list_account_ids_for_tag(ego="ego1", tag="TRUSTED") == ["abc", "xyz"]
    assert store.list_account_ids_for_tags(ego="ego1", tags=["trusted", "missing"]) == [
        "abc",
        "xyz",
    ]
    assert sorted(store.list_anchor_polarities(ego="ego1")) == [
        ("123", -1),
        ("abc", 1),
        ("neg_only", -1),
    ]

    deleted = store.delete_tag(ego="ego1", account_id="123", tag="AI ALIGNMENT")
    assert deleted is True
    assert store.list_tags(ego="ego1", account_id="123") == []

    events = store.list_events(ego="ego1", account_id="123")
    assert [(event.action, event.polarity) for event in events] == [
        ("set", 1),
        ("set", -1),
        ("remove", None),
    ]
    assert [event.event_id for event in events] == sorted(
        event.event_id for event in events
    )


@pytest.mark.integration
def test_distinct_vocabulary_survives_retraction(tmp_path) -> None:
    store = AccountTagStore(tmp_path / "account_tags.db")
    store.upsert_tag(
        ego="ego",
        account_id="account",
        tag="Dharma",
        polarity=1,
    )
    store.delete_tag(ego="ego", account_id="account", tag="dharma")

    assert store.list_distinct_tags(ego="ego") == ["Dharma"]


@pytest.mark.integration
def test_account_tag_history_records_only_real_state_changes(tmp_path) -> None:
    store = AccountTagStore(tmp_path / "account_tags.db")

    assert store.delete_tag(ego="ego", account_id="missing", tag="Dharma") is False
    assert store.list_events(ego="ego", account_id="missing") == []

    store.upsert_tag(
        ego="ego",
        account_id="known",
        tag="Dharma",
        polarity=1,
        confidence=0.8,
    )
    store.upsert_tag(
        ego="other",
        account_id="known",
        tag="Dharma",
        polarity=-1,
    )
    assert store.delete_tag(ego="ego", account_id="known", tag="dharma") is True

    assert store.list_tags(ego="ego", account_id="known") == []
    events = store.list_events(ego="ego", account_id="known")
    assert [event.action for event in events] == ["set", "remove"]
    assert events[0].tag == "Dharma"
    assert events[0].confidence == 0.8
    assert events[0].source == "account_tag_store"
    assert events[0].evidence_binding_status == "unbound"
    assert events[1].tag == "Dharma"
    assert events[1].polarity is None
    other_events = store.list_events(ego="other", account_id="known")
    assert [event.polarity for event in other_events] == [-1]


@pytest.mark.integration
def test_account_tag_store_validates_inputs(tmp_path) -> None:
    store = AccountTagStore(tmp_path / "account_tags.db")
    with pytest.raises(ValueError, match="tag cannot be empty"):
        store.upsert_tag(ego="ego", account_id="1", tag="  ", polarity=1)
    with pytest.raises(ValueError, match="polarity must be 1"):
        store.upsert_tag(ego="ego", account_id="1", tag="x", polarity=0)
    with pytest.raises(ValueError, match="confidence must be in"):
        store.upsert_tag(ego="ego", account_id="1", tag="x", polarity=1, confidence=2.0)


@pytest.mark.integration
def test_account_tag_store_backfills_legacy_projection_once(tmp_path) -> None:
    db_path = tmp_path / "account_tags.db"
    store = AccountTagStore(db_path)
    store.upsert_tag(ego="ego", account_id="legacy", tag="Dharma", polarity=1)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM account_tag_events")

    AccountTagStore(db_path)
    events = store.list_events(ego="ego", account_id="legacy")
    assert len(events) == 1
    assert events[0].source == "legacy_projection_backfill"

    AccountTagStore(db_path)
    assert len(store.list_events(ego="ego", account_id="legacy")) == 1
