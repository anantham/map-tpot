"""Load and verify immutable evaluation-frame projections."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict

from src.artifacts.digests import json_sha256

from .evaluation_frame import validate_evaluation_frame


class CommunityGoldStudyProjectionMixin:
    def _load_study_frame_with_conn(
        self,
        conn: sqlite3.Connection,
        frame_id: str,
    ) -> Dict[str, Any]:
        row = conn.execute(
            """
            SELECT frame_id, user_id, ontology_id, ontology_version,
                   task_id, manifest_json, manifest_digest,
                   evidence_snapshot_id, evidence_snapshot_hash,
                   graph_manifest_hash, evidence_cutoff, role_registry_id
            FROM account_community_evaluation_frame
            WHERE frame_id = ?
            """,
            (frame_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"study frame '{frame_id}' does not exist")
        frame = json.loads(str(row["manifest_json"]))
        validate_evaluation_frame(frame)
        expected = {
            "frame_id": frame["frameId"],
            "user_id": frame["scope"]["userId"],
            "ontology_id": frame["scope"]["ontologyId"],
            "ontology_version": frame["scope"]["ontologyVersion"],
            "task_id": frame["scope"]["taskId"],
            "manifest_digest": frame["manifestDigest"],
            "evidence_snapshot_id": frame["evidence"]["snapshotId"],
            "evidence_snapshot_hash": frame["evidence"]["snapshotHash"],
            "graph_manifest_hash": frame["evidence"]["graphManifestHash"],
            "evidence_cutoff": frame["evidence"]["cutoff"],
            "role_registry_id": frame["roleRegistry"]["id"],
        }
        mismatches = {
            field: {"expected": value, "observed": row[field]}
            for field, value in expected.items()
            if row[field] != value
        }
        if mismatches:
            raise ValueError(
                "study frame denormalized identity mismatch: "
                f"{mismatches}"
            )
        return frame

    def _verify_role_projection(
        self,
        conn: sqlite3.Connection,
        frame: Dict[str, Any],
    ) -> None:
        rows = conn.execute(
            """
            SELECT account_id, stratum, assigned_role, assigned_probability,
                   terminal_test_probability, role_probabilities_json
            FROM account_community_evaluation_role
            WHERE frame_id = ?
            """,
            (frame["frameId"],),
        ).fetchall()
        if len(rows) != len(frame["roleAssignments"]):
            raise ValueError(
                "study role projection mismatch: "
                f"expected {len(frame['roleAssignments'])} rows, "
                f"observed {len(rows)}"
            )
        by_account = {str(row["account_id"]): row for row in rows}
        projected = []
        for expected in frame["roleAssignments"]:
            row = by_account.get(str(expected["accountId"]))
            if row is None:
                raise ValueError(
                    "study role projection mismatch: missing account "
                    f"{expected['accountId']}"
                )
            projected.append(
                {
                    "accountId": str(row["account_id"]),
                    "stratum": str(row["stratum"]),
                    "assignedRole": str(row["assigned_role"]),
                    "assignedProbability": float(
                        row["assigned_probability"]
                    ),
                    "terminalTestProbability": float(
                        row["terminal_test_probability"]
                    ),
                    "roleProbabilities": json.loads(
                        str(row["role_probabilities_json"])
                    ),
                    "roleRegistryId": frame["roleRegistry"]["id"],
                }
            )
        observed_digest = json_sha256(projected)
        if observed_digest != frame["roleAssignmentsDigest"]:
            raise ValueError(
                "study role projection digest mismatch: "
                f"expected={frame['roleAssignmentsDigest']}, "
                f"observed={observed_digest}"
            )
