"""Canonical payload and lineage hashes for scoped human judgments."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Any, Collection, Dict, Mapping, Sequence

from src.artifacts.digests import json_sha256

from .constants import JUDGMENT_NAMES
from .frame_validation import require_text, require_utc_aware
from .schema import validate_confidence
from .study_binding import validate_persisted_study_row

JudgmentKey = tuple[str, str, str]


def _positive_id(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _optional_evidence(value: Any) -> Any:
    if value is None:
        return None
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("stored judgment evidence JSON is invalid") from exc


def canonical_judgment_payload(
    row: sqlite3.Row,
    *,
    frame: Mapping[str, Any],
    ontology_community_ids: Collection[str],
) -> Dict[str, Any]:
    """Validate and normalize every scientific field on one stored judgment."""

    validate_persisted_study_row(
        row,
        frame=frame,
        ontology_community_ids=ontology_community_ids,
    )
    if str(row["identity_status"]) != "scoped":
        raise ValueError("terminal judgment provenance must be study-scoped")
    if (
        isinstance(row["is_active"], bool)
        or not isinstance(row["is_active"], int)
        or row["is_active"] != 1
    ):
        raise ValueError("scoped terminal judgment must remain active")
    judgment = require_text(row["judgment"], field="stored judgment")
    if judgment not in JUDGMENT_NAMES:
        raise ValueError(f"stored judgment is invalid: {judgment}")
    supersedes = row["supersedes_label_set_id"]
    if supersedes is not None:
        supersedes = _positive_id(
            supersedes,
            field="stored supersedes_label_set_id",
        )
    note = row["note"]
    if note is not None and not isinstance(note, str):
        raise ValueError("stored judgment note must be text or null")
    scope = frame["scope"]
    return {
        "schemaVersion": 1,
        "labelSetId": _positive_id(
            row["id"],
            field="stored label_set_id",
        ),
        "frameId": require_text(
            row["study_frame_id"],
            field="stored study_frame_id",
        ),
        "accountId": require_text(
            row["account_id"],
            field="stored account_id",
        ),
        "communityId": require_text(
            row["community_id"],
            field="stored community_id",
        ),
        "reviewer": require_text(
            row["reviewer"],
            field="stored reviewer",
        ),
        "judgment": judgment,
        "confidence": validate_confidence(row["confidence"]),
        "note": note,
        "evidence": _optional_evidence(row["evidence_json"]),
        "isActive": True,
        "identityStatus": "scoped",
        "ontologyScope": {
            "userId": scope["userId"],
            "ontologyId": scope["ontologyId"],
            "ontologyVersion": scope["ontologyVersion"],
            "taskId": scope["taskId"],
        },
        "evidenceSnapshotId": require_text(
            row["evidence_snapshot_id"],
            field="stored evidence_snapshot_id",
        ),
        "evidenceSnapshotHash": str(row["evidence_snapshot_hash"]),
        "contextHash": str(row["context_hash"]),
        "observedAt": str(row["observed_at"]),
        "createdAt": require_utc_aware(
            row["created_at"],
            field="stored created_at",
        ),
        "supersedesLabelSetId": supersedes,
    }


def release_provenance_by_head(
    conn: sqlite3.Connection,
    *,
    frame: Mapping[str, Any],
    expected_keys: set[JudgmentKey],
    current_rows: Sequence[Mapping[str, object]],
    ontology_community_ids: set[str],
) -> Dict[int, Dict[str, Any]]:
    """Hash complete current payloads and every row in their linear histories."""

    current_by_key = {
        (
            str(row["accountId"]),
            str(row["communityId"]),
            str(row["reviewer"]),
        ): int(row["labelSetId"])
        for row in current_rows
    }
    reviewers = sorted({key[2] for key in expected_keys})
    placeholders = ",".join("?" for _ in reviewers)
    stored = conn.execute(
        f"""
        SELECT *
        FROM account_community_gold_label_set
        WHERE identity_status = 'scoped'
          AND study_frame_id = ?
          AND reviewer IN ({placeholders})
        ORDER BY id
        """,
        (frame["frameId"], *reviewers),
    ).fetchall()
    histories: dict[JudgmentKey, list[sqlite3.Row]] = defaultdict(list)
    for row in stored:
        key = (
            str(row["account_id"]),
            str(row["community_id"]),
            str(row["reviewer"]),
        )
        if key in expected_keys:
            histories[key].append(row)

    output: Dict[int, Dict[str, Any]] = {}
    for key in sorted(expected_keys):
        payloads = [
            canonical_judgment_payload(
                row,
                frame=frame,
                ontology_community_ids=ontology_community_ids,
            )
            for row in histories[key]
        ]
        head_id = current_by_key[key]
        head_payload = next(
            (
                payload
                for payload in payloads
                if payload["labelSetId"] == head_id
            ),
            None,
        )
        if head_payload is None:
            raise ValueError(
                f"terminal judgment provenance is missing head: key={key}"
            )
        lineage = {
            "schemaVersion": 1,
            "frameId": frame["frameId"],
            "accountId": key[0],
            "communityId": key[1],
            "reviewer": key[2],
            "headLabelSetId": head_id,
            "judgments": payloads,
        }
        output[head_id] = {
            "judgmentPayloadHash": json_sha256(head_payload),
            "lineageHash": json_sha256(lineage),
            "lineageLength": len(payloads),
        }
    return output
