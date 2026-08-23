"""Integrity checks and concrete metrics for the Slice 1 verifier."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.community_gold import CommunityGoldStore

if __package__:
    from scripts._personal_ontology_slice1_fixture import (
        frozen_frame,
        record_judgment,
        seed_database,
        terminal_receipt,
    )
    from scripts._personal_ontology_slice1_probes import (
        calibration_is_blocked,
        database_metrics,
        mismatched_repeat_is_blocked,
        sealed_write_is_blocked,
    )
else:  # Direct execution through the sibling verifier script.
    from _personal_ontology_slice1_fixture import (
        frozen_frame,
        record_judgment,
        seed_database,
        terminal_receipt,
    )
    from _personal_ontology_slice1_probes import (
        calibration_is_blocked,
        database_metrics,
        mismatched_repeat_is_blocked,
        sealed_write_is_blocked,
    )


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def run_verification(db_path: Path) -> tuple[list[Check], dict[str, Any]]:
    seed_database(db_path)
    store = CommunityGoldStore(db_path)
    store.upsert_label(
        account_id="legacy-account",
        community_id="verify-a",
        reviewer="legacy-reviewer",
        judgment="in",
    )
    store.register_ontology_version(
        user_id="verifier-user",
        ontology_id="verifier-ontology",
        ontology_version=1,
        definition={
            "groups": [
                {"communityId": "verify-a", "definition": "Boundary A"},
                {"communityId": "verify-b", "definition": "Boundary B"},
            ]
        },
    )
    store.register_ontology_task(
        user_id="verifier-user",
        ontology_id="verifier-ontology",
        ontology_version=1,
        task_id="affiliation",
        target_type="affiliation",
        definition={"question": "Does this account participate?"},
    )
    frame = frozen_frame()
    store.freeze_study(frame)
    development = next(
        row for row in frame["roleAssignments"]
        if row["assignedRole"] == "model_development"
    )
    terminal_assignments = [
        row for row in frame["roleAssignments"]
        if row["assignedRole"] == "terminal_test"
    ]
    record_judgment(
        store,
        frame,
        account_id=development["accountId"],
        judgment="in",
        context_digit="d",
    )
    for account_index, assignment in enumerate(terminal_assignments):
        for community_index, community_id in enumerate(
            ("verify-a", "verify-b")
        ):
            record_judgment(
                store,
                frame,
                account_id=assignment["accountId"],
                community_id=community_id,
                judgment=("in", "out", "abstain")[
                    (
                        account_index * 2 + community_index
                    ) % 3
                ],
                context_digit=(
                    "e" if community_id == "verify-a" else "f"
                ),
            )
    store.record_prediction(
        prediction_id="verifier-prediction",
        frame_id=frame["frameId"],
        account_id=development["accountId"],
        community_id="verify-a",
        model_run_id="verifier-local-run",
        score=0.72,
        score_semantics="affinity",
        evidence_snapshot_id=frame["evidence"]["snapshotId"],
        evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
        context_hash="d" * 64,
        observed_at="2026-07-25T00:00:00+00:00",
    )
    calibration_blocked = calibration_is_blocked(
        store,
        frame,
        development["accountId"],
    )
    training = store.list_study_judgments(
        frame_id=frame["frameId"],
        purpose="training",
    )
    terminal_release = store.release_terminal_test(
        frame_id=frame["frameId"],
        reviewer="verifier-human",
        accessed_by="verifier",
        access_receipt=terminal_receipt(),
    )
    terminal_rows = terminal_release["judgments"]
    replay = store.release_terminal_test(
        frame_id=frame["frameId"],
        reviewer="verifier-human",
        accessed_by="verifier",
        access_receipt=terminal_receipt(),
    )
    mismatch_blocked = mismatched_repeat_is_blocked(store, frame)
    sealed_write_blocked = sealed_write_is_blocked(
        store,
        frame,
        terminal_assignments[0]["accountId"],
    )
    legacy = store.list_labels(account_id="legacy-account")
    predictions = store.list_predictions(frame_id=frame["frameId"])
    study = store.get_study(frame["frameId"])
    stored_metrics = database_metrics(db_path)

    checks = [
        Check(
            "Legacy identity remains unbound",
            len(legacy) == 1
            and legacy[0]["identityStatus"] == "legacy_unbound"
            and legacy[0]["ontologyScope"] is None,
            f"legacy_rows={len(legacy)}",
        ),
        Check(
            "Migration version and global roles are complete",
            stored_metrics["schemaVersion"] == 3
            and stored_metrics["globalRoles"] == frame["counts"]["u0"]
            and frame["randomizationAudit"]["designInferenceEligible"]
            is False,
            "schema="
            f"{stored_metrics['schemaVersion']}, "
            f"global_roles={stored_metrics['globalRoles']}, "
            "design_inference_eligible="
            f"{frame['randomizationAudit']['designInferenceEligible']}",
        ),
        Check(
            "Training result excludes terminal labels",
            [row["accountId"] for row in training]
            == [development["accountId"]],
            f"training_accounts={[row['accountId'] for row in training]}",
        ),
        Check(
            "Predictions remain separate and semantically explicit",
            len(predictions) == 1
            and predictions[0]["scoreSemantics"] == "affinity"
            and stored_metrics["scopedHistory"]
            == 1 + len(terminal_rows),
            "predictions="
            f"{len(predictions)}, "
            f"scoped_history={stored_metrics['scopedHistory']}",
        ),
        Check(
            "Unregistered probability claims are blocked",
            calibration_blocked,
            f"blocked={calibration_blocked}",
        ),
        Check(
            "Terminal release is exact, replay-safe, and sealing",
            {row["accountId"] for row in terminal_rows}
            == {
                row["accountId"] for row in terminal_assignments
            }
            and terminal_release["replayed"] is False
            and replay["replayed"] is True
            and replay["judgments"] == terminal_rows
            and replay["terminalAccess"]
            == terminal_release["terminalAccess"]
            and mismatch_blocked
            and sealed_write_blocked
            and stored_metrics["terminalAccessRows"] == 1
            and study["terminalAccess"]["releasedLabelHeadCount"]
            == len(terminal_rows)
            and study["terminalAccess"]["coverage"]["complete"] is True,
            f"released={len(terminal_rows)}, replayed="
            f"{replay['replayed']}, mismatch_blocked={mismatch_blocked}, "
            f"access_rows={stored_metrics['terminalAccessRows']}, "
            f"writes_blocked={sealed_write_blocked}, "
            "coverage_complete="
            f"{study['terminalAccess']['coverage']['complete']}",
        ),
    ]
    metrics = {
        "frameDigest": frame["manifestDigest"],
        "roleDigest": frame["roleAssignmentsDigest"],
        "roleCounts": dict(
            sorted(
                Counter(
                    row["assignedRole"]
                    for row in frame["roleAssignments"]
                ).items()
            )
        ),
        "minimumNominalTerminalInclusionProbability": min(
            row["terminalTestProbability"]
            for row in frame["roleAssignments"]
        ),
        "releaseManifestHash": study["terminalAccess"][
            "releaseManifestHash"
        ],
    }
    return checks, metrics
