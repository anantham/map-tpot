from __future__ import annotations

from copy import deepcopy
import sqlite3

import pytest

from src.data.community_gold.evaluation_frame import freeze_evaluation_frame
from tests.personal_ontology_fixtures import (
    frame_kwargs,
    record_complete_terminal_judgments,
    registered_study_store,
    seed_community_db,
    terminal_access_receipt,
)
from src.data.community_gold import CommunityGoldStore


@pytest.mark.integration
def test_frozen_study_is_immutable_and_roles_are_queryable(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    seed_community_db(db_path)
    store = CommunityGoldStore(db_path)
    store.register_ontology_version(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        definition={
            "groups": [
                {"communityId": "comm-a", "definition": "A"},
                {"communityId": "comm-b", "definition": "B"},
            ]
        },
    )
    store.register_ontology_task(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        task_id="affiliation",
        target_type="affiliation",
        definition={"question": "Affiliation?"},
    )
    frame = freeze_evaluation_frame(**frame_kwargs())

    first = store.freeze_study(frame)
    second = store.freeze_study(frame)

    assert first["created"] is True
    assert second["created"] is False
    stored = store.get_study(frame["frameId"])
    assert stored["manifestDigest"] == frame["manifestDigest"]
    assert stored["roleCount"] == frame["counts"]["uEval"]
    assert stored["terminalAccessConsumed"] is False

    changed_kwargs = frame_kwargs()
    changed_kwargs["candidate_rules"] = {"source": "changed"}
    changed = freeze_evaluation_frame(**changed_kwargs)
    with pytest.raises(ValueError, match="immutable study frame"):
        store.freeze_study(changed)


@pytest.mark.integration
def test_training_cannot_read_terminal_labels_and_terminal_access_is_one_use(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    development = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "model_development"
    )
    terminal = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    )
    for assignment, judgment in ((development, "in"), (terminal, "out")):
        store.record_study_judgment(
            frame_id=frame["frameId"],
            account_id=assignment["accountId"],
            community_id="comm-a",
            reviewer="human",
            judgment=judgment,
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash=("d" if judgment == "in" else "e") * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )

    training = store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="training",
        reviewer="human",
    )
    assert [row["accountId"] for row in training] == [development["accountId"]]
    assert terminal["accountId"] not in {row["accountId"] for row in training}

    complete_terminal = record_complete_terminal_judgments(store, frame)
    with pytest.raises(ValueError, match="access_receipt"):
        store.list_study_judgments(
            frame_id=frame["frameId"],
            purpose="terminal_evaluation",
            reviewer="human",
        )

    terminal_rows = store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="terminal_evaluation",
        reviewer="human",
        accessed_by="terminal-verifier",
        access_receipt=terminal_access_receipt(),
    )
    assert len(terminal_rows) == len(complete_terminal)
    assert {row["accountId"] for row in terminal_rows} == {
        row["accountId"]
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    }

    with pytest.raises(ValueError, match="already consumed"):
        store.list_study_judgments(
            frame_id=frame["frameId"],
            purpose="terminal_evaluation",
            reviewer="human",
            accessed_by="terminal-verifier",
            access_receipt={"repeat": True},
        )


@pytest.mark.integration
def test_frame_manifest_tampering_is_rejected_before_persistence(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    tampered = deepcopy(frame)
    tampered["counts"]["uEval"] += 1

    with pytest.raises(ValueError, match="manifestDigest"):
        store.freeze_study(tampered)


@pytest.mark.integration
def test_role_projection_rejects_extra_persisted_accounts(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    template = frame["roleAssignments"][0]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO account_community_evaluation_role
            (frame_id, account_id, stratum, assigned_role,
             assigned_probability, terminal_test_probability,
             role_probabilities_json)
            VALUES (?, 'tampered-extra-account', ?, ?, ?, ?, ?)
            """,
            (
                frame["frameId"],
                template["stratum"],
                template["assignedRole"],
                template["assignedProbability"],
                template["terminalTestProbability"],
                "{}",
            ),
        )
        conn.commit()

    with pytest.raises(ValueError, match="role projection mismatch"):
        store.get_study(frame["frameId"])


@pytest.mark.integration
def test_corrupt_terminal_row_does_not_consume_one_use_access(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    terminal = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    )
    stored = store.record_study_judgment(
        frame_id=frame["frameId"],
        account_id=terminal["accountId"],
        community_id="comm-a",
        reviewer="human",
        judgment="in",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TRIGGER prevent_scoped_gold_update")
        conn.execute(
            """
            UPDATE account_community_gold_label_set
            SET context_hash = 'corrupt'
            WHERE id = ?
            """,
            (stored["labelSetId"],),
        )
        conn.commit()

    with pytest.raises(ValueError, match="stored context_hash"):
        store.list_study_judgments(
            frame_id=frame["frameId"],
            purpose="terminal_evaluation",
            reviewer="human",
            accessed_by="terminal-verifier",
            access_receipt=terminal_access_receipt(),
        )
    assert store.get_study(frame["frameId"])[
        "terminalAccessConsumed"
    ] is False


@pytest.mark.integration
def test_role_registry_id_cannot_be_reused_for_a_new_allocation(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, _frame = registered_study_store(db_path)
    changed_kwargs = frame_kwargs()
    changed_kwargs["frame_id"] = "synthetic-frame-new-allocation"
    changed_kwargs["seed"] = "different-seed"
    changed = freeze_evaluation_frame(**changed_kwargs)

    with pytest.raises(ValueError, match="immutable role registry"):
        store.freeze_study(changed)


@pytest.mark.integration
def test_terminal_release_seals_judgments_and_records_exact_heads(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    terminal = next(
        row
        for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    )
    terminal_heads = record_complete_terminal_judgments(store, frame)
    first = terminal_heads[0]
    store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="terminal_evaluation",
        reviewer="human",
        accessed_by="terminal-verifier",
        access_receipt=terminal_access_receipt(),
    )

    study = store.get_study(frame["frameId"])
    assert len(study["terminalAccess"]["releaseManifestHash"]) == 64
    assert study["terminalAccess"]["releasedLabelHeadCount"] == 6
    assert study["terminalAccess"]["coverage"]["complete"] is True
    with sqlite3.connect(db_path) as conn:
        release = conn.execute(
            """
            SELECT release_manifest_json
            FROM account_community_terminal_test_access
            WHERE frame_id = ?
            """,
            (frame["frameId"],),
        ).fetchone()
        with pytest.raises(sqlite3.IntegrityError, match="immutable terminal"):
            conn.execute(
                """
                DELETE FROM account_community_terminal_test_access
                WHERE frame_id = ?
                """,
                (frame["frameId"],),
            )
    assert str(first["labelSetId"]) in release[0]

    with pytest.raises(ValueError, match="sealed"):
        store.record_study_judgment(
            frame_id=frame["frameId"],
            account_id=terminal["accountId"],
            community_id="comm-a",
            reviewer="human",
            judgment="out",
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash="e" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )
