"""Complete terminal coverage manifests and tamper-checked release reads."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from typing import Any, Dict, Mapping, Sequence, Set

from src.artifacts.digests import json_sha256

from .judgment_lineage import assert_complete_linear_histories
from .judgment_provenance import release_provenance_by_head
from .ontology_contract import verified_study_community_ids
from .study_access import accounts_for_purpose
from .terminal_access_envelope import verify_access_envelope
from .terminal_contract import (
    canonical_json,
    checked_payload,
    normalize_release_manifest,
    normalize_terminal_receipt,
)


def _ontology_community_ids(
    conn: sqlite3.Connection,
    frame: Mapping[str, Any],
) -> list[str]:
    community_ids = sorted(
        verified_study_community_ids(conn, scope=frame["scope"])
    )
    if not community_ids:
        raise ValueError(
            "terminal release cannot proceed without ontology groups"
        )
    return community_ids


def _head_payload(
    row: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "labelSetId": int(row["labelSetId"]),
        "accountId": str(row["accountId"]),
        "communityId": str(row["communityId"]),
        "reviewer": str(row["reviewer"]),
        "judgment": str(row["judgment"]),
        "evidenceSnapshotHash": str(row["evidenceSnapshotHash"]),
        "contextHash": str(row["contextHash"]),
        "observedAt": str(row["observedAt"]),
        "createdAt": str(row["createdAt"]),
        "judgmentPayloadHash": provenance["judgmentPayloadHash"],
        "lineageHash": provenance["lineageHash"],
        "lineageLength": provenance["lineageLength"],
    }


def build_terminal_release_manifest(
    conn: sqlite3.Connection,
    *,
    frame: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    reviewer: str,
    terminal_account_ids: Set[str],
) -> Dict[str, Any]:
    """Require one current judgment for every account/group pair."""

    communities = _ontology_community_ids(conn, frame)
    expected = {
        (account_id, community_id, reviewer)
        for account_id in terminal_account_ids
        for community_id in communities
    }
    observed = {
        (
            str(row["accountId"]),
            str(row["communityId"]),
            str(row["reviewer"]),
        )
        for row in rows
    }
    missing = sorted(expected - observed)
    extra = sorted(observed - expected)
    if missing or extra or len(rows) != len(observed):
        raise ValueError(
            "terminal release coverage is incomplete or inconsistent: "
            f"expected={len(expected)}, reviewed={len(observed)}, "
            f"missing_sample={missing[:5]}, extra_sample={extra[:5]}"
        )
    if not expected:
        raise ValueError(
            "terminal release coverage has no expected account/group pairs"
        )
    assert_complete_linear_histories(
        conn,
        frame_id=str(frame["frameId"]),
        reviewer=reviewer,
        expected_keys=expected,
        current_rows=rows,
    )
    provenance = release_provenance_by_head(
        conn,
        frame=frame,
        expected_keys=expected,
        current_rows=rows,
        ontology_community_ids=set(communities),
    )
    heads = sorted(
        [
            _head_payload(
                row,
                provenance=provenance[int(row["labelSetId"])],
            )
            for row in rows
        ],
        key=lambda row: (
            row["accountId"],
            row["communityId"],
            row["reviewer"],
            row["labelSetId"],
        ),
    )
    counts = Counter(row["judgment"] for row in heads)
    labelable = counts["in"] + counts["out"]
    return {
        "schemaVersion": 1,
        "frameId": frame["frameId"],
        "frameManifestDigest": frame["manifestDigest"],
        "purpose": "terminal_evaluation",
        "reviewer": reviewer,
        "coverage": {
            "terminalAccountCount": len(terminal_account_ids),
            "ontologyGroupCount": len(communities),
            "expectedLabelHeadCount": len(expected),
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


def _stored_heads(
    conn: sqlite3.Connection,
    *,
    frame_id: str,
    label_set_ids: list[int],
) -> list[Dict[str, Any]]:
    placeholders = ",".join("?" for _ in label_set_ids)
    rows = conn.execute(
        f"""
        SELECT ls.id, ls.account_id, ls.community_id, ls.reviewer,
               ls.judgment, ls.evidence_snapshot_hash, ls.context_hash,
               ls.observed_at, ls.created_at
        FROM account_community_gold_head head
        JOIN account_community_gold_label_set ls
          ON ls.id = head.label_set_id
        WHERE head.frame_id = ?
          AND ls.study_frame_id = ?
          AND ls.identity_status = 'scoped'
          AND ls.id IN ({placeholders})
        """,
        (frame_id, frame_id, *label_set_ids),
    ).fetchall()
    return [
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
    ]


def verify_terminal_access_row(
    conn: sqlite3.Connection,
    *,
    row: sqlite3.Row,
    released_frame: Mapping[str, Any],
) -> Dict[str, Any]:
    """Recompute stored hashes, coverage, head tuples, and generation identity."""

    if (
        str(row["frame_id"]) != released_frame["frameId"]
        or str(row["role_registry_id"])
        != released_frame["roleRegistry"]["id"]
    ):
        raise ValueError(
            "terminal access generation identity differs from released frame"
        )
    envelope = verify_access_envelope(row)
    try:
        receipt_raw = json.loads(str(row["access_receipt_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("terminal access receipt JSON is invalid") from exc
    receipt = normalize_terminal_receipt(receipt_raw)
    checked_payload(
        stored_json=row["access_receipt_json"],
        stored_hash=row["access_receipt_hash"],
        normalized=receipt,
        record_name="access receipt",
    )
    try:
        release_raw = json.loads(str(row["release_manifest_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("terminal release manifest JSON is invalid") from exc
    release = normalize_release_manifest(
        release_raw,
        frame=released_frame,
    )
    checked_payload(
        stored_json=row["release_manifest_json"],
        stored_hash=row["release_manifest_hash"],
        normalized=release,
        record_name="release manifest",
    )
    if row["released_label_head_count"] != len(release["labelHeads"]):
        raise ValueError(
            "terminal release head count differs from its manifest"
        )
    label_ids = [item["labelSetId"] for item in release["labelHeads"]]
    stored_heads = _stored_heads(
        conn,
        frame_id=str(released_frame["frameId"]),
        label_set_ids=label_ids,
    )
    rebuilt = build_terminal_release_manifest(
        conn,
        frame=released_frame,
        rows=stored_heads,
        reviewer=release["reviewer"],
        terminal_account_ids=accounts_for_purpose(
            released_frame,
            "terminal_evaluation",
        ),
    )
    if canonical_json(rebuilt) != canonical_json(release):
        raise ValueError(
            "terminal release manifest coverage cannot be reproduced"
        )
    return {
        "releasedFrameId": envelope["frameId"],
        "roleRegistryId": envelope["roleRegistryId"],
        "accessedBy": envelope["accessedBy"],
        "accessedAt": envelope["accessedAt"],
        "accessReceiptHash": json_sha256(receipt),
        "releaseManifestHash": json_sha256(release),
        "accessEnvelopeHash": str(row["access_envelope_hash"]),
        "releasedLabelHeadCount": len(release["labelHeads"]),
        "coverage": dict(release["coverage"]),
        "reviewer": release["reviewer"],
    }
