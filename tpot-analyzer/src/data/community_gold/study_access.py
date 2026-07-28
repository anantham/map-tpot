"""Purpose-gated account roles and one-use terminal-test access."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Mapping, Optional, Set

from src.artifacts.digests import json_sha256

from .frame_validation import require_text
from .role_allocation import READ_PURPOSES
from .schema import now_iso
from .terminal_access_envelope import access_envelope_hash
from .terminal_contract import (
    canonical_json,
    normalize_release_manifest,
    normalize_terminal_receipt,
)


def role_for_account(
    frame: Mapping[str, Any],
    account_id: str,
) -> Optional[str]:
    """Return the one frozen role, including explicit purposive roles."""

    if account_id in frame["fixedTrainingIds"]:
        return "fixed_training"
    if account_id in frame["fixedChallengeIds"]:
        return "fixed_challenge"
    for assignment in frame["roleAssignments"]:
        if assignment["accountId"] == account_id:
            return str(assignment["assignedRole"])
    return None


def accounts_for_purpose(
    frame: Mapping[str, Any],
    purpose: str,
) -> Set[str]:
    """Resolve readable account IDs without consulting mutable labels."""

    parsed_purpose = require_text(purpose, field="purpose")
    if parsed_purpose not in READ_PURPOSES:
        raise ValueError(
            "purpose must be one of: "
            f"{', '.join(sorted(READ_PURPOSES))}"
        )

    roles, fixed_accounts = access_filter_for_purpose(
        frame,
        parsed_purpose,
    )
    allowed: Set[str] = set(fixed_accounts)
    for assignment in frame["roleAssignments"]:
        if str(assignment["assignedRole"]) in roles:
            allowed.add(str(assignment["accountId"]))
    return allowed


def access_filter_for_purpose(
    frame: Mapping[str, Any],
    purpose: str,
) -> tuple[Set[str], Set[str]]:
    parsed_purpose = require_text(purpose, field="purpose")
    if parsed_purpose not in READ_PURPOSES:
        raise ValueError(
            "purpose must be one of: "
            f"{', '.join(sorted(READ_PURPOSES))}"
        )
    fixed_accounts: Set[str] = set()
    if parsed_purpose in {"training", "selection"}:
        fixed_accounts.update(
            str(value) for value in frame["fixedTrainingIds"]
        )
    if parsed_purpose == "selection":
        fixed_accounts.update(
            str(value) for value in frame["fixedChallengeIds"]
        )
    roles = {
        str(role)
        for role, contract in frame["roleRegistry"]["catalog"].items()
        if parsed_purpose in contract["readPurposes"]
    }
    return roles, fixed_accounts


def consume_terminal_access(
    conn: sqlite3.Connection,
    *,
    frame: Mapping[str, Any],
    accessed_by: Optional[str],
    access_receipt: Optional[Mapping[str, Any]],
    release_manifest: Mapping[str, Any],
) -> Dict[str, Any]:
    """Atomically consume a terminal label generation once."""

    frame_id = str(frame["frameId"])
    role_registry_id = str(frame["roleRegistry"]["id"])
    existing = conn.execute(
        """
        SELECT frame_id, accessed_by, accessed_at, access_receipt_hash
        FROM account_community_terminal_test_access
        WHERE role_registry_id = ?
        """,
        (role_registry_id,),
    ).fetchone()
    if existing is not None:
        raise ValueError(
            "terminal access for evaluation generation "
            f"'{role_registry_id}' is already consumed by frame "
            f"'{existing['frame_id']}'"
        )

    if access_receipt is None:
        raise ValueError(
            "access_receipt is required for terminal_evaluation"
        )
    actor = require_text(accessed_by, field="accessed_by")
    normalized = normalize_terminal_receipt(access_receipt)
    receipt_hash = json_sha256(normalized)
    normalized_release = normalize_release_manifest(
        release_manifest,
        frame=frame,
    )
    release_hash = json_sha256(normalized_release)
    label_heads = normalized_release.get("labelHeads")
    released_count = len(label_heads)
    accessed_at = now_iso()
    envelope_hash = access_envelope_hash(
        frame_id=frame_id,
        role_registry_id=role_registry_id,
        accessed_by=actor,
        accessed_at=accessed_at,
        access_receipt_hash=receipt_hash,
        release_manifest_hash=release_hash,
        released_label_head_count=released_count,
    )
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
            frame_id,
            role_registry_id,
            actor,
            canonical_json(normalized),
            receipt_hash,
            canonical_json(normalized_release),
            release_hash,
            envelope_hash,
            released_count,
            accessed_at,
        ),
    )
    return {
        "accessedBy": actor,
        "accessedAt": accessed_at,
        "roleRegistryId": role_registry_id,
        "accessReceiptHash": receipt_hash,
        "releaseManifestHash": release_hash,
        "accessEnvelopeHash": envelope_hash,
        "releasedLabelHeadCount": released_count,
    }


def assert_study_open(
    conn: sqlite3.Connection,
    *,
    frame_id: str,
    operation: str,
) -> None:
    sealed = conn.execute(
        """
        SELECT access.frame_id, access.accessed_at
        FROM account_community_evaluation_frame frame
        JOIN account_community_terminal_test_access access
          ON access.role_registry_id = frame.role_registry_id
        WHERE frame.frame_id = ?
        """,
        (frame_id,),
    ).fetchone()
    if sealed is not None:
        raise ValueError(
            f"study frame '{frame_id}' is sealed after terminal release "
            f"by frame '{sealed['frame_id']}'; "
            f"{operation} is not permitted"
        )
