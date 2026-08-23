"""Read and format current scoped judgment heads."""
from __future__ import annotations

import json
from typing import Any, Collection, Dict, Mapping, Optional, Set

from .study_binding import validate_persisted_study_row


def current_study_rows(
    conn: Any,
    *,
    frame_id: str,
    reviewer: Optional[str],
    allowed_roles: Set[str],
    fixed_accounts: Set[str],
) -> list[Any]:
    access_conditions = []
    access_params: list[Any] = []
    if allowed_roles:
        placeholders = ",".join("?" for _ in allowed_roles)
        access_conditions.append(
            f"role.assigned_role IN ({placeholders})"
        )
        access_params.extend(sorted(allowed_roles))
    if fixed_accounts:
        placeholders = ",".join("?" for _ in fixed_accounts)
        access_conditions.append(
            f"ls.account_id IN ({placeholders})"
        )
        access_params.extend(sorted(fixed_accounts))
    if not access_conditions:
        return []
    reviewer_clause = "AND ls.reviewer = ?" if reviewer is not None else ""
    params: list[Any] = [frame_id]
    if reviewer is not None:
        params.append(reviewer)
    params.extend(access_params)
    access_clause = " OR ".join(access_conditions)
    return conn.execute(
        f"""
        SELECT ls.*
        FROM account_community_gold_head head
        JOIN account_community_gold_label_set ls
          ON ls.id = head.label_set_id
        LEFT JOIN account_community_evaluation_role role
          ON role.frame_id = head.frame_id
         AND role.account_id = ls.account_id
        WHERE head.frame_id = ?
          AND ls.identity_status = 'scoped'
          {reviewer_clause}
          AND ({access_clause})
        ORDER BY ls.created_at ASC, ls.id ASC
        """,
        params,
    ).fetchall()


def readable_study_rows(
    rows: list[Any],
    *,
    frame: Mapping[str, Any],
    allowed_accounts: Set[str],
    ontology_community_ids: Collection[str],
) -> list[Dict[str, Any]]:
    output = []
    for row in rows:
        account_id = str(row["account_id"])
        if account_id not in allowed_accounts:
            continue
        role = validate_persisted_study_row(
            row,
            frame=frame,
            ontology_community_ids=ontology_community_ids,
        )
        output.append(
            {
                "labelSetId": int(row["id"]),
                "frameId": str(row["study_frame_id"]),
                "accountId": account_id,
                "communityId": str(row["community_id"]),
                "reviewer": str(row["reviewer"]),
                "judgment": str(row["judgment"]),
                "confidence": (
                    float(row["confidence"])
                    if row["confidence"] is not None
                    else None
                ),
                "note": row["note"],
                "evidence": (
                    json.loads(str(row["evidence_json"]))
                    if row["evidence_json"] is not None
                    else None
                ),
                "role": role,
                "ontologyScope": dict(frame["scope"]),
                "evidenceSnapshotId": str(
                    row["evidence_snapshot_id"]
                ),
                "evidenceSnapshotHash": str(
                    row["evidence_snapshot_hash"]
                ),
                "contextHash": str(row["context_hash"]),
                "observedAt": str(row["observed_at"]),
                "createdAt": str(row["created_at"]),
                "supersedesLabelSetId": (
                    int(row["supersedes_label_set_id"])
                    if row["supersedes_label_set_id"] is not None
                    else None
                ),
            }
        )
    return output
