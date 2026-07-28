"""Behavioral regressions for terminal release and provenance integrity."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
import sqlite3
from typing import Any

import pytest

from src.artifacts.digests import json_sha256
from src.data.community_gold.evaluation_frame import freeze_evaluation_frame
from src.data.community_gold.study_access import accounts_for_purpose
from src.data.community_gold.terminal_access_envelope import (
    access_envelope_hash,
)
from src.data.community_gold.terminal_contract import (
    canonical_json,
    normalize_terminal_receipt,
)
from tests.personal_ontology_fixtures import (
    frame_kwargs,
    record_complete_terminal_judgments,
    registered_study_store,
    terminal_access_receipt,
)


pytestmark = pytest.mark.integration


def _access_count(db_path: Any) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM account_community_terminal_test_access"
            ).fetchone()[0]
        )


def _release(store: Any, frame: dict[str, Any]) -> None:
    store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="terminal_evaluation",
        reviewer="human",
        accessed_by="terminal-verifier",
        access_receipt=terminal_access_receipt(),
    )


def _sibling_frame(store: Any) -> dict[str, Any]:
    store.register_ontology_task(
        user_id="user-aditya",
        ontology_id="personal-subcultures",
        ontology_version=1,
        task_id="competence",
        target_type="competence",
        definition={"question": "Does this account demonstrate competence?"},
    )
    kwargs = deepcopy(frame_kwargs())
    kwargs["frame_id"] = "synthetic-frame-competence-v1"
    kwargs["scope"]["taskId"] = "competence"
    frame = freeze_evaluation_frame(**kwargs)
    store.freeze_study(frame)
    return frame


def _stored_head_payloads(db_path: Any, frame_id: str) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ls.id, ls.account_id, ls.community_id, ls.reviewer,
                   ls.judgment, ls.evidence_snapshot_hash, ls.context_hash,
                   ls.observed_at, ls.created_at
            FROM account_community_gold_head head
            JOIN account_community_gold_label_set ls
              ON ls.id = head.label_set_id
            WHERE head.frame_id = ?
            """,
            (frame_id,),
        ).fetchall()
    return sorted(
        [
            {
                "labelSetId": int(row["id"]),
                "accountId": str(row["account_id"]),
                "communityId": str(row["community_id"]),
                "reviewer": str(row["reviewer"]),
                "judgment": str(row["judgment"]),
                "evidenceSnapshotHash": str(row["evidence_snapshot_hash"]),
                "contextHash": str(row["context_hash"]),
                "observedAt": str(row["observed_at"]),
                "createdAt": str(row["created_at"]),
            }
            for row in rows
        ],
        key=lambda row: (
            row["accountId"],
            row["communityId"],
            row["reviewer"],
            row["labelSetId"],
        ),
    )


def _forged_release(
    frame: dict[str, Any],
    heads: list[dict[str, Any]],
) -> dict[str, Any]:
    counts = Counter(row["judgment"] for row in heads)
    labelable = counts["in"] + counts["out"]
    terminal_accounts = accounts_for_purpose(
        frame,
        "terminal_evaluation",
    )
    return {
        "schemaVersion": 1,
        "frameId": frame["frameId"],
        "frameManifestDigest": frame["manifestDigest"],
        "purpose": "terminal_evaluation",
        "reviewer": "human",
        "coverage": {
            "terminalAccountCount": len(terminal_accounts),
            "ontologyGroupCount": 2,
            "expectedLabelHeadCount": len(heads),
            "reviewedLabelHeadCount": len(heads),
            "missingLabelHeadCount": 0,
            "judgmentCounts": {
                judgment: counts[judgment]
                for judgment in ("in", "out", "abstain")
            },
            "labelabilityRate": labelable / len(heads),
            "complete": True,
        },
        "labelHeads": heads,
    }


def _insert_terminal_access(
    db_path: Any,
    *,
    frame: dict[str, Any],
    release: dict[str, Any],
) -> None:
    receipt = normalize_terminal_receipt(terminal_access_receipt())
    receipt_hash = json_sha256(receipt)
    release_hash = json_sha256(release)
    accessed_at = "2026-07-26T00:00:00+00:00"
    envelope_hash = access_envelope_hash(
        frame_id=frame["frameId"],
        role_registry_id=frame["roleRegistry"]["id"],
        accessed_by="forged-replay",
        accessed_at=accessed_at,
        access_receipt_hash=receipt_hash,
        release_manifest_hash=release_hash,
        released_label_head_count=len(release["labelHeads"]),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO account_community_terminal_test_access
            (frame_id, role_registry_id, accessed_by, access_receipt_json,
             access_receipt_hash, release_manifest_json,
             release_manifest_hash, access_envelope_hash,
             released_label_head_count, accessed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                frame["frameId"],
                frame["roleRegistry"]["id"],
                "forged-replay",
                canonical_json(receipt),
                receipt_hash,
                canonical_json(release),
                release_hash,
                envelope_hash,
                len(release["labelHeads"]),
                accessed_at,
            ),
        )
        conn.commit()


def test_sibling_frame_head_replay_is_rejected(tmp_path) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, target = registered_study_store(db_path)
    sibling = _sibling_frame(store)
    record_complete_terminal_judgments(store, sibling)
    forged = _forged_release(
        target,
        _stored_head_payloads(db_path, sibling["frameId"]),
    )

    with pytest.raises(
        (ValueError, RuntimeError, sqlite3.IntegrityError),
        match="frame|identity|terminal|head|manifest",
    ):
        _insert_terminal_access(db_path, frame=target, release=forged)
        store.get_study(target["frameId"])


@pytest.mark.parametrize("tamper", ["append", "corrupt"])
def test_global_role_tamper_blocks_release_without_consuming(
    tmp_path,
    tamper: str,
) -> None:
    db_path = tmp_path / "archive_tweets.db"
    store, frame = registered_study_store(db_path)
    record_complete_terminal_judgments(store, frame)

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if tamper == "append":
                payload = {
                    "accountId": "injected-global-account",
                    "assignedRole": "model_development",
                    "roleRegistryId": frame["roleRegistry"]["id"],
                }
                conn.execute(
                    """
                    INSERT INTO account_community_global_role
                    (role_registry_id, account_id, assigned_role,
                     role_json, role_hash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        frame["roleRegistry"]["id"],
                        payload["accountId"],
                        payload["assignedRole"],
                        canonical_json(payload),
                        json_sha256(payload),
                    ),
                )
            else:
                conn.execute(
                    "DROP TRIGGER prevent_immutable_global_role_update"
                )
                row = conn.execute(
                    """
                    SELECT account_id, role_json
                    FROM account_community_global_role
                    ORDER BY account_id LIMIT 1
                    """
                ).fetchone()
                payload = json.loads(str(row["role_json"]))
                payload["assignedRole"] = "terminal_test"
                conn.execute(
                    """
                    UPDATE account_community_global_role
                    SET assigned_role = ?, role_json = ?, role_hash = ?
                    WHERE account_id = ?
                    """,
                    (
                        payload["assignedRole"],
                        canonical_json(payload),
                        json_sha256(payload),
                        row["account_id"],
                    ),
                )
            conn.commit()
    except sqlite3.IntegrityError:
        assert _access_count(db_path) == 0
        return

    with pytest.raises(
        (ValueError, RuntimeError, sqlite3.IntegrityError),
        match="global role|role projection|registry|terminal",
    ):
        _release(store, frame)
    assert _access_count(db_path) == 0
