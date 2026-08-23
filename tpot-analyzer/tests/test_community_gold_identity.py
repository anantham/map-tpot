from __future__ import annotations

import sqlite3

import pytest

from src.data.community_gold import CommunityGoldStore
from tests.personal_ontology_fixtures import (
    registered_study_store,
    seed_legacy_gold_db,
)


@pytest.mark.integration
def test_legacy_migration_is_idempotent_and_does_not_invent_identity(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_legacy_gold_db(db_path)

    first_store = CommunityGoldStore(db_path)
    first = first_store.list_labels(account_id="legacy-account")
    second_store = CommunityGoldStore(db_path)
    second = second_store.list_labels(account_id="legacy-account")

    assert first == second
    assert len(first) == 1
    assert first[0].get("identityStatus") == "legacy_unbound"
    assert first[0].get("ontologyScope") is None
    assert first[0].get("evidenceSnapshotId") is None
    assert first[0].get("contextHash") is None

    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(account_community_gold_label_set)"
            )
        }
        version = conn.execute(
            "SELECT MAX(version) FROM account_community_gold_schema_version"
        ).fetchone()[0]
        count = conn.execute(
            "SELECT COUNT(*) FROM account_community_gold_label_set"
        ).fetchone()[0]
        identity = conn.execute(
            """
            SELECT user_id, ontology_id, ontology_version, task_id,
                   evidence_snapshot_id, context_hash
            FROM account_community_gold_label_set
            WHERE account_id = 'legacy-account'
            """
        ).fetchone()
    assert {
        "user_id",
        "ontology_id",
        "ontology_version",
        "task_id",
        "study_frame_id",
        "evidence_snapshot_id",
        "evidence_snapshot_hash",
        "context_hash",
        "observed_at",
        "identity_status",
    } <= columns
    assert version == 3
    assert count == 1
    assert identity == (None, None, None, None, None, None)


@pytest.mark.integration
def test_ontology_versions_and_tasks_are_immutable(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, _frame = registered_study_store(db_path)

    exact = store.register_ontology_version(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        definition={
            "name": "Personal subcultures",
            "groups": [
                {"communityId": "comm-a", "definition": "Group A boundary"},
                {"communityId": "comm-b", "definition": "Group B boundary"},
            ],
        },
    )
    assert exact["created"] is False
    assert len(exact["definitionHash"]) == 64

    with pytest.raises(ValueError, match="immutable ontology version"):
        store.register_ontology_version(
            user_id="user-aditya",
            ontology_id="personal-subcultures",
            ontology_version=1,
            definition={
                "name": "Changed after freeze",
                "groups": [
                    {"communityId": "comm-a", "definition": "Changed boundary"}
                ],
            },
        )

    version_two = store.register_ontology_version(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=2,
        supersedes_version=1,
        definition={
            "name": "Personal subcultures v2",
            "groups": [
                {"communityId": "comm-a", "definition": "Narrower A boundary"}
            ],
        },
    )
    assert version_two["created"] is True
    assert version_two["supersedesVersion"] == 1


@pytest.mark.integration
def test_scoped_judgment_corrections_append_without_mutating_predecessor(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    development = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "model_development"
    )
    account_id = development["accountId"]

    first = store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=account_id,
        community_id="comm-a",
        reviewer="human",
        judgment="in",
        confidence=0.8,
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
        note="initial boundary call",
    )
    second = store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=account_id,
        community_id="comm-a",
        reviewer="human",
        judgment="out",
        confidence=0.7,
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="e" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
        note="corrected after context review",
    )

    assert second["supersedesLabelSetId"] == first["labelSetId"]
    current = store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="training",
        reviewer="human",
    )
    assert len(current) == 1
    assert current[0]["judgment"] == "out"
    assert current[0]["ontologyScope"]["taskId"] == "affiliation"

    with sqlite3.connect(db_path) as conn:
        predecessor = conn.execute(
            """
            SELECT judgment, note, is_active
            FROM account_community_gold_label_set
            WHERE id = ?
            """,
            (first["labelSetId"],),
        ).fetchone()
        total = conn.execute(
            """
            SELECT COUNT(*)
            FROM account_community_gold_label_set
            WHERE study_frame_id = ?
            """,
            (frame["frameId"],),
        ).fetchone()[0]
    assert predecessor == ("in", "initial boundary call", 1)
    assert total == 2

    reopened = CommunityGoldStore(db_path)
    reopened_current = reopened.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="training",
        reviewer="human",
    )
    assert [row["labelSetId"] for row in reopened_current] == [
        second["labelSetId"]
    ]


@pytest.mark.integration
def test_scoped_judgment_requires_matching_evidence_identity(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    account_id = frame["roleAssignments"][0]["accountId"]

    with pytest.raises(ValueError, match="evidence_snapshot_hash mismatch"):
        store.record_study_judgment(
            frame_id=frame["frameId"],
            account_id=account_id,
            community_id="comm-a",
            reviewer="human",
            judgment="in",
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash="f" * 64,
            context_hash="d" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )


@pytest.mark.integration
def test_scoped_head_must_match_full_label_identity(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    account_id = frame["roleAssignments"][0]["accountId"]
    stored = store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=account_id,
        community_id="comm-a",
        reviewer="human",
        judgment="in",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="does not match"):
            conn.execute(
                """
                INSERT INTO account_community_gold_head
                (frame_id, account_id, community_id, reviewer,
                 label_set_id, updated_at)
                VALUES (?, 'wrong-account', 'comm-b', 'other', ?, ?)
                """,
                (
                    frame["frameId"],
                    stored["labelSetId"],
                    "2026-07-26T00:00:00+00:00",
                ),
            )


@pytest.mark.integration
def test_ontology_requires_boundaries_and_protects_registered_groups(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, _frame = registered_study_store(db_path)

    with pytest.raises(ValueError, match="definition"):
        store.register_ontology_version(
            user_id="user-aditya",
            ontology_id="missing-boundary",
            ontology_version=1,
            definition={"groups": [{"communityId": "comm-a"}]},
        )
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(
            sqlite3.IntegrityError,
            match="FOREIGN KEY constraint failed",
        ):
            conn.execute("DELETE FROM community WHERE id = 'comm-a'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable ontology"):
            conn.execute(
                """
                UPDATE personal_ontology_version
                SET definition_hash = ?
                WHERE user_id = 'user-aditya'
                  AND ontology_id = 'personal-subcultures'
                  AND ontology_version = 1
                """,
                ("0" * 64,),
            )
