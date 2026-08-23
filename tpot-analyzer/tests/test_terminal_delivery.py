"""Behavioral contract for recoverable terminal-test delivery."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import sqlite3
from typing import Any

import pytest

import src.data.community_gold.terminal_delivery as terminal_delivery
from src.data.community_gold.evaluation_frame import freeze_evaluation_frame
from tests.personal_ontology_fixtures import (
    frame_kwargs,
    record_complete_terminal_judgments,
    registered_study_store,
    terminal_access_receipt,
)


pytestmark = pytest.mark.integration


def _prepared_release(tmp_path):
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)
    return db_path, store, frame


def _release(
    store: Any,
    frame: dict[str, Any],
    *,
    actor: str = "terminal-verifier",
    reviewer: str = "human",
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return store.release_terminal_test(
        frame_id=frame["frameId"],
        reviewer=reviewer,
        accessed_by=actor,
        access_receipt=(
            terminal_access_receipt()
            if receipt is None
            else receipt
        ),
    )


def _access_count(db_path) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) "
                "FROM account_community_terminal_test_access"
            ).fetchone()[0]
        )


def test_lost_first_response_is_recoverable_with_identical_receipt(
    tmp_path,
) -> None:
    db_path, store, frame = _prepared_release(tmp_path)

    discarded_response = _release(store, frame)
    replay = _release(store, frame)

    assert discarded_response["replayed"] is False
    assert replay["replayed"] is True
    assert replay["judgments"] == discarded_response["judgments"]
    assert replay["terminalAccess"] == discarded_response["terminalAccess"]
    assert replay["terminalAccess"]["accessedAt"] == (
        discarded_response["terminalAccess"]["accessedAt"]
    )
    assert _access_count(db_path) == 1


@pytest.mark.parametrize(
    ("actor", "reviewer", "receipt"),
    [
        (
            "different-actor",
            "human",
            terminal_access_receipt(),
        ),
        (
            "terminal-verifier",
            "different-reviewer",
            terminal_access_receipt(),
        ),
        (
            "terminal-verifier",
            "human",
            {
                **terminal_access_receipt(),
                "runManifestHash": "6" * 64,
            },
        ),
        (
            "terminal-verifier",
            "human",
            {"repeat": True},
        ),
    ],
)
def test_consumed_generation_rejects_any_request_mismatch(
    tmp_path,
    actor: str,
    reviewer: str,
    receipt: dict[str, Any],
) -> None:
    db_path, store, frame = _prepared_release(tmp_path)
    _release(store, frame)

    with pytest.raises(ValueError) as raised:
        _release(
            store,
            frame,
            actor=actor,
            reviewer=reviewer,
            receipt=receipt,
        )

    assert type(raised.value).__name__ == "TerminalReleaseConflict"
    assert "already consumed" in str(raised.value)
    assert _access_count(db_path) == 1


def test_sibling_frame_cannot_replay_generation_release(tmp_path) -> None:
    db_path, store, frame = _prepared_release(tmp_path)
    store.register_ontology_task(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        task_id="competence",
        target_type="competence",
        definition={"question": "Competence?"},
    )
    sibling_kwargs = deepcopy(frame_kwargs())
    sibling_kwargs["frame_id"] = "synthetic-frame-competence-delivery"
    sibling_kwargs["scope"]["taskId"] = "competence"
    sibling = freeze_evaluation_frame(**sibling_kwargs)
    store.freeze_study(sibling)
    _release(store, frame)

    with pytest.raises(ValueError) as raised:
        _release(store, sibling)

    assert type(raised.value).__name__ == "TerminalReleaseConflict"
    assert "already consumed" in str(raised.value)
    assert _access_count(db_path) == 1


def test_corrupt_stored_release_blocks_identical_replay(tmp_path) -> None:
    db_path, store, frame = _prepared_release(tmp_path)
    _release(store, frame)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TRIGGER prevent_immutable_terminal_access_update")
        conn.execute(
            """
            UPDATE account_community_terminal_test_access
            SET release_manifest_json = '{}'
            WHERE frame_id = ?
            """,
            (frame["frameId"],),
        )
        conn.commit()

    with pytest.raises(ValueError, match="release|manifest"):
        _release(store, frame)
    assert _access_count(db_path) == 1


def test_first_release_verification_failure_rolls_back_consumption(
    tmp_path,
    monkeypatch,
) -> None:
    db_path, store, frame = _prepared_release(tmp_path)

    def reject_before_commit(*_args, **_kwargs):
        raise ValueError("synthetic pre-commit verification failure")

    monkeypatch.setattr(
        terminal_delivery,
        "verify_terminal_access_row",
        reject_before_commit,
    )

    with pytest.raises(ValueError, match="pre-commit verification"):
        _release(store, frame)
    assert _access_count(db_path) == 0


def test_replay_preserves_generation_seal(tmp_path) -> None:
    _db_path, store, frame = _prepared_release(tmp_path)
    _release(store, frame)
    _release(store, frame)
    terminal = next(
        assignment
        for assignment in frame["roleAssignments"]
        if assignment["assignedRole"] == "terminal_test"
    )

    with pytest.raises(ValueError, match="sealed"):
        store.record_study_judgment(
            frame_id=frame["frameId"],
            account_id=terminal["accountId"],
            community_id="comm-a",
            reviewer="human",
            judgment="out",
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash="f" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )


def test_concurrent_identical_requests_share_one_release(tmp_path) -> None:
    db_path, store, frame = _prepared_release(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_release, store, frame)
            for _ in range(2)
        ]
        results = [future.result(timeout=20) for future in futures]

    assert sorted(result["replayed"] for result in results) == [False, True]
    assert results[0]["judgments"] == results[1]["judgments"]
    assert results[0]["terminalAccess"] == results[1]["terminalAccess"]
    assert _access_count(db_path) == 1
