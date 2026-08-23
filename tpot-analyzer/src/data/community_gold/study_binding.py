"""Shared validation for records bound to a frozen evaluation frame."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Collection, Mapping

from .frame_validation import (
    require_sha256,
    require_text,
    require_utc_aware,
)
from .global_roles import verify_global_role_registry
from .ontology_contract import verified_study_community_ids
from .study_access import role_for_account


def _timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


@dataclass(frozen=True)
class StudyBinding:
    frame: Mapping[str, Any]
    frame_id: str
    account_id: str
    community_id: str
    role: str
    evidence_snapshot_id: str
    evidence_snapshot_hash: str
    context_hash: str
    observed_at: str

    @property
    def scope(self) -> Mapping[str, Any]:
        return self.frame["scope"]


def validate_study_binding(
    store: Any,
    conn: sqlite3.Connection,
    *,
    frame_id: Any,
    account_id: Any,
    community_id: Any,
    evidence_snapshot_id: Any,
    evidence_snapshot_hash: Any,
    context_hash: Any,
    observed_at: Any,
) -> StudyBinding:
    """Validate account, ontology, evidence generation, and observation time."""

    parsed_frame = require_text(frame_id, field="frame_id")
    account = require_text(account_id, field="account_id")
    community = require_text(community_id, field="community_id")
    frame = store._load_study_frame_with_conn(conn, parsed_frame)
    verify_global_role_registry(conn, frame=frame)
    store._verify_role_projection(conn, frame)

    role = role_for_account(frame, account)
    if role is None:
        raise ValueError(
            f"account '{account}' is outside study frame '{parsed_frame}' U0"
        )
    store._assert_community_exists(conn, community)
    scope = frame["scope"]
    ontology_communities = verified_study_community_ids(
        conn,
        scope=scope,
    )
    if community not in ontology_communities:
        raise ValueError(
            f"community '{community}' is outside the study ontology version"
        )

    snapshot_id = require_text(
        evidence_snapshot_id,
        field="evidence_snapshot_id",
    )
    expected_id = str(frame["evidence"]["snapshotId"])
    if snapshot_id != expected_id:
        raise ValueError(
            "evidence_snapshot_id mismatch: "
            f"expected={expected_id}, observed={snapshot_id}"
        )
    snapshot_hash = require_sha256(
        evidence_snapshot_hash,
        field="evidence_snapshot_hash",
    )
    expected_hash = str(frame["evidence"]["snapshotHash"])
    if snapshot_hash != expected_hash:
        raise ValueError(
            "evidence_snapshot_hash mismatch: "
            f"expected={expected_hash}, observed={snapshot_hash}"
        )
    parsed_context = require_sha256(context_hash, field="context_hash")
    parsed_observed = require_utc_aware(observed_at, field="observed_at")
    cutoff = require_utc_aware(
        frame["evidence"]["cutoff"],
        field="frame.evidence.cutoff",
    )
    if _timestamp(parsed_observed) > _timestamp(cutoff):
        raise ValueError(
            "observed_at must not be later than the frozen evidence cutoff"
        )

    return StudyBinding(
        frame=frame,
        frame_id=parsed_frame,
        account_id=account,
        community_id=community,
        role=role,
        evidence_snapshot_id=snapshot_id,
        evidence_snapshot_hash=snapshot_hash,
        context_hash=parsed_context,
        observed_at=parsed_observed,
    )


def assert_row_matches_frame(
    row: sqlite3.Row,
    frame: Mapping[str, Any],
) -> None:
    """Fail closed if persisted scoped identity drifts from its frame."""

    scope = frame["scope"]
    expected = {
        "evidence_snapshot_id": frame["evidence"]["snapshotId"],
        "evidence_snapshot_hash": frame["evidence"]["snapshotHash"],
    }
    row_fields = set(row.keys())
    if "frame_id" in row_fields:
        expected["frame_id"] = frame["frameId"]
    else:
        expected.update(
            {
                "user_id": scope["userId"],
                "ontology_id": scope["ontologyId"],
                "ontology_version": scope["ontologyVersion"],
                "task_id": scope["taskId"],
                "study_frame_id": frame["frameId"],
            }
        )
    mismatches = {
        field: {"expected": value, "observed": row[field]}
        for field, value in expected.items()
        if row[field] != value
    }
    if mismatches:
        raise ValueError(
            "scoped record identity mismatch with frozen study frame: "
            f"{mismatches}"
        )
    require_sha256(row["context_hash"], field="stored context_hash")
    require_utc_aware(row["observed_at"], field="stored observed_at")


def validate_persisted_study_row(
    row: sqlite3.Row,
    *,
    frame: Mapping[str, Any],
    ontology_community_ids: Collection[str],
) -> str:
    """Revalidate a direct-written scoped row against its frozen frame."""

    assert_row_matches_frame(row, frame)
    account_id = require_text(
        row["account_id"],
        field="stored account_id",
    )
    role = role_for_account(frame, account_id)
    if role is None:
        raise ValueError(
            f"stored account '{account_id}' is outside frame U0"
        )
    community_id = require_text(
        row["community_id"],
        field="stored community_id",
    )
    if community_id not in ontology_community_ids:
        raise ValueError(
            f"stored community '{community_id}' is outside frame ontology"
        )
    observed = require_utc_aware(
        row["observed_at"],
        field="stored observed_at",
    )
    cutoff = require_utc_aware(
        frame["evidence"]["cutoff"],
        field="frame.evidence.cutoff",
    )
    if _timestamp(observed) > _timestamp(cutoff):
        raise ValueError(
            "stored observed_at is later than the frozen evidence cutoff"
        )
    return role
