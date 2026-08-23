"""Behavioral contract for immutable formative Research Notes dossiers."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from src.data.research_notes_snapshot import (
    ResearchNotesSnapshotError,
    build_research_notes_snapshot,
    canonical_snapshot_bytes,
    verify_research_notes_snapshot,
)


def _account(
    account_id: str = "acct-1",
    username: str = "DharmaExample",
) -> dict:
    return {
        "account": {
            "accountId": account_id,
            "username": username,
            "displayName": "Dharma Example",
            "bio": "Meditation notes",
            "location": None,
            "website": "https://example.test",
            "fetchedAt": "2026-07-31T10:00:00Z",
        },
        "tweets": [
            {
                "tweetId": f"{account_id}-new",
                "text": "First displayed tweet",
                "createdAt": "2026-07-30T10:00:00Z",
                "favoriteCount": 3,
                "retweetCount": 1,
                "fetchedAt": "2026-07-31T10:00:00Z",
            },
            {
                "tweetId": f"{account_id}-old",
                "text": "Second displayed tweet",
                "createdAt": "2026-07-29T10:00:00Z",
                "favoriteCount": 1,
                "retweetCount": 0,
                "fetchedAt": "2026-07-31T10:00:00Z",
            },
        ],
    }


def _provenance() -> dict:
    return {
        "source": "bounded_private_acquisition",
        "acquisitionPlanSha256": "a" * 64,
        "acquisitionReceiptSha256": "b" * 64,
    }


def _build(dossiers: list[dict] | None = None) -> dict:
    return build_research_notes_snapshot(
        snapshot_id="dharma-boundary-pretrial-v1",
        created_at="2026-07-31T11:00:00+00:00",
        provenance=_provenance(),
        dossiers=dossiers or [_account()],
    )


def test_build_is_canonical_and_verifiable() -> None:
    second = _account("acct-2", "AnotherDharma")
    artifact = _build([_account(), second])
    reordered_inputs = [
        {"tweets": deepcopy(second["tweets"]), "account": deepcopy(second["account"])},
        {"tweets": deepcopy(_account()["tweets"]), "account": deepcopy(_account()["account"])},
    ]
    rebuilt = _build(reordered_inputs)

    assert [row["account"]["accountId"] for row in artifact["dossiers"]] == [
        "acct-2",
        "acct-1",
    ]
    assert artifact == rebuilt
    assert verify_research_notes_snapshot(artifact) == artifact
    assert canonical_snapshot_bytes(artifact) == canonical_snapshot_bytes(rebuilt)
    assert all(len(row["accountHash"]) == 64 for row in artifact["dossiers"])
    assert len(artifact["snapshotHash"]) == 64


def test_json_key_order_and_whitespace_do_not_change_canonical_artifact() -> None:
    artifact = _build()
    pretty_reordered = json.dumps(
        {key: artifact[key] for key in reversed(artifact)},
        indent=4,
        ensure_ascii=False,
    )
    reparsed = json.loads(pretty_reordered)

    assert verify_research_notes_snapshot(reparsed) == artifact
    assert canonical_snapshot_bytes(reparsed) == canonical_snapshot_bytes(artifact)


def test_exact_displayed_tweet_order_changes_hashes() -> None:
    original = _build()
    reversed_tweets = _account()
    reversed_tweets["tweets"].reverse()
    reordered = _build([reversed_tweets])

    assert reordered["dossiers"][0]["accountHash"] != original["dossiers"][0]["accountHash"]
    assert reordered["snapshotHash"] != original["snapshotHash"]


def test_mutation_is_rejected_and_builder_does_not_alias_inputs() -> None:
    input_dossier = _account()
    artifact = _build([input_dossier])
    input_dossier["tweets"][0]["text"] = "mutated after build"
    assert artifact["dossiers"][0]["tweets"][0]["text"] == "First displayed tweet"

    tampered = deepcopy(artifact)
    tampered["dossiers"][0]["tweets"][0]["text"] = "forged"
    with pytest.raises(ResearchNotesSnapshotError, match="accountHash mismatch"):
        verify_research_notes_snapshot(tampered)


def test_declared_snapshot_hash_is_verified() -> None:
    artifact = _build()
    artifact["snapshotHash"] = "f" * 64
    with pytest.raises(ResearchNotesSnapshotError, match="snapshotHash mismatch"):
        verify_research_notes_snapshot(artifact)


def test_semantically_equal_but_noncanonical_timestamp_mutation_is_rejected() -> None:
    artifact = _build()
    artifact["createdAt"] = "2026-07-31T11:00:00+00:00"

    with pytest.raises(ResearchNotesSnapshotError, match="not canonical"):
        verify_research_notes_snapshot(artifact)


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ((), "sourceText"),
        (("provenance",), "sourceNotes"),
        (("dossiers", 0), "strata"),
        (("dossiers", 0, "account"), "roles"),
        (("dossiers", 0, "tweets", 0), "model"),
    ],
)
def test_leaked_or_unallowlisted_fields_are_rejected(path: tuple, field: str) -> None:
    artifact = _build()
    target = artifact
    for segment in path:
        target = target[segment]
    target[field] = "must not enter a blind dossier"

    with pytest.raises(ResearchNotesSnapshotError, match="unexpected field"):
        verify_research_notes_snapshot(artifact)


@pytest.mark.parametrize(
    "dossiers, message",
    [
        ([_account(), _account("acct-1", "OtherHandle")], "duplicate accountId"),
        ([_account(), _account("acct-2", "dHaRmAeXaMpLe")], "duplicate username"),
    ],
)
def test_account_ids_and_handles_must_be_unique(dossiers: list[dict], message: str) -> None:
    with pytest.raises(ResearchNotesSnapshotError, match=message):
        _build(dossiers)


def test_tweet_ids_must_be_unique_across_account_dossiers() -> None:
    first = _account()
    second = _account("acct-2", "AnotherDharma")
    second["tweets"][0]["tweetId"] = first["tweets"][0]["tweetId"]

    with pytest.raises(ResearchNotesSnapshotError, match="duplicate tweetId across"):
        _build([first, second])


def test_build_rejects_model_fields_before_hashing() -> None:
    dossier = _account()
    dossier["account"]["community"] = "dharma"
    with pytest.raises(ResearchNotesSnapshotError, match="unexpected field"):
        _build([dossier])
