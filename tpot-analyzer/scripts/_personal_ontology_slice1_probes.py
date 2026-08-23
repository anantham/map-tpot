"""Adversarial probes used by the human-facing Slice 1 verifier."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.data.community_gold import CommunityGoldStore

if __package__:
    from scripts._personal_ontology_slice1_fixture import (
        record_judgment,
        terminal_receipt,
    )
else:
    from _personal_ontology_slice1_fixture import (
        record_judgment,
        terminal_receipt,
    )


def calibration_is_blocked(
    store: CommunityGoldStore,
    frame: dict[str, Any],
    account_id: str,
) -> bool:
    try:
        store.record_prediction(
            prediction_id="forged-probability",
            frame_id=frame["frameId"],
            account_id=account_id,
            community_id="verify-a",
            model_run_id="verifier-local-run",
            score=0.72,
            score_semantics="calibrated_probability",
            calibration_record_hash="9" * 64,
            evidence_snapshot_id=frame["evidence"]["snapshotId"],
            evidence_snapshot_hash=frame["evidence"]["snapshotHash"],
            context_hash="d" * 64,
            observed_at="2026-07-25T00:00:00+00:00",
        )
    except ValueError as exc:
        return "not available" in str(exc)
    return False


def mismatched_repeat_is_blocked(
    store: CommunityGoldStore,
    frame: dict[str, Any],
) -> bool:
    changed_receipt = {
        **terminal_receipt(),
        "runManifestHash": "6" * 64,
    }
    try:
        store.release_terminal_test(
            frame_id=frame["frameId"],
            reviewer="verifier-human",
            accessed_by="verifier",
            access_receipt=changed_receipt,
        )
    except ValueError as exc:
        return (
            type(exc).__name__ == "TerminalReleaseConflict"
            and "already consumed" in str(exc)
        )
    return False


def sealed_write_is_blocked(
    store: CommunityGoldStore,
    frame: dict[str, Any],
    terminal_account_id: str,
) -> bool:
    try:
        record_judgment(
            store,
            frame,
            account_id=terminal_account_id,
            judgment="in",
            context_digit="f",
        )
    except ValueError as exc:
        return "sealed" in str(exc)
    return False


def database_metrics(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            "schemaVersion": int(
                conn.execute(
                    """
                    SELECT MAX(version)
                    FROM account_community_gold_schema_version
                    """
                ).fetchone()[0]
            ),
            "globalRoles": int(
                conn.execute(
                    "SELECT COUNT(*) FROM account_community_global_role"
                ).fetchone()[0]
            ),
            "scopedHistory": int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM account_community_gold_label_set
                    WHERE identity_status = 'scoped'
                    """
                ).fetchone()[0]
            ),
            "terminalAccessRows": int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM account_community_terminal_test_access
                    """
                ).fetchone()[0]
            ),
        }
