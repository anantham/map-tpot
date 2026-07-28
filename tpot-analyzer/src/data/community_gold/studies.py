"""Persistence and compatibility checks for frozen evaluation frames."""
from __future__ import annotations

import json
from typing import Any, Dict

from .evaluation_frame import validate_evaluation_frame
from .frame_validation import require_text
from .global_roles import (
    persist_global_role_registry,
    verify_global_role_registry,
)
from .ontology_contract import verified_study_community_ids
from .schema import now_iso
from .study_projection import CommunityGoldStudyProjectionMixin
from .terminal_release import verify_terminal_access_row


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class CommunityGoldStudyMixin(CommunityGoldStudyProjectionMixin):
    """Store each evaluation frame once and verify its role projection."""

    def freeze_study(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        validate_evaluation_frame(frame)
        frame_id = require_text(frame["frameId"], field="frame.frameId")
        scope = frame["scope"]
        manifest_digest = str(frame["manifestDigest"])
        manifest_json = _canonical_json(frame)

        with self._open() as conn:
            verified_study_community_ids(conn, scope=scope)
            existing = conn.execute(
                """
                SELECT manifest_digest, created_at
                FROM account_community_evaluation_frame
                WHERE frame_id = ?
                """,
                (frame_id,),
            ).fetchone()
            if existing is not None:
                stored_frame = self._load_study_frame_with_conn(
                    conn,
                    frame_id,
                )
                if (
                    str(existing["manifest_digest"]) != manifest_digest
                    or stored_frame != frame
                ):
                    raise ValueError(
                        f"immutable study frame '{frame_id}' already exists "
                        "with different content"
                    )
                verify_global_role_registry(conn, frame=frame)
                self._verify_role_projection(conn, frame)
                return {
                    "created": False,
                    "frameId": frame_id,
                    "manifestDigest": manifest_digest,
                    "roleCount": len(frame["roleAssignments"]),
                    "createdAt": existing["created_at"],
                }

            created_at = now_iso()
            conn.execute("BEGIN IMMEDIATE")
            try:
                persist_global_role_registry(
                    conn,
                    frame=frame,
                    created_at=created_at,
                )
                conn.execute(
                    """
                    INSERT INTO account_community_evaluation_frame
                    (frame_id, user_id, ontology_id, ontology_version, task_id,
                     manifest_json, manifest_digest, evidence_snapshot_id,
                     evidence_snapshot_hash, graph_manifest_hash,
                     evidence_cutoff, role_registry_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        frame_id,
                        scope["userId"],
                        scope["ontologyId"],
                        scope["ontologyVersion"],
                        scope["taskId"],
                        manifest_json,
                        manifest_digest,
                        frame["evidence"]["snapshotId"],
                        frame["evidence"]["snapshotHash"],
                        frame["evidence"]["graphManifestHash"],
                        frame["evidence"]["cutoff"],
                        frame["roleRegistry"]["id"],
                        created_at,
                    ),
                )
                conn.executemany(
                    """
                    INSERT INTO account_community_evaluation_role
                    (frame_id, account_id, stratum, assigned_role,
                     assigned_probability, terminal_test_probability,
                     role_probabilities_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            frame_id,
                            row["accountId"],
                            row["stratum"],
                            row["assignedRole"],
                            row["assignedProbability"],
                            row["terminalTestProbability"],
                            _canonical_json(row["roleProbabilities"]),
                        )
                        for row in frame["roleAssignments"]
                    ],
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "created": True,
            "frameId": frame_id,
            "manifestDigest": manifest_digest,
            "roleCount": len(frame["roleAssignments"]),
            "createdAt": created_at,
        }

    def get_study(self, frame_id: str) -> Dict[str, Any]:
        parsed_id = require_text(frame_id, field="frame_id")
        with self._open() as conn:
            frame = self._load_study_frame_with_conn(conn, parsed_id)
            verified_study_community_ids(
                conn,
                scope=frame["scope"],
            )
            verify_global_role_registry(conn, frame=frame)
            self._verify_role_projection(conn, frame)
            access = conn.execute(
                """
                SELECT access.*
                FROM account_community_terminal_test_access access
                WHERE access.role_registry_id = ?
                """,
                (frame["roleRegistry"]["id"],),
            ).fetchone()
            verified_access = None
            if access is not None:
                released_frame = self._load_study_frame_with_conn(
                    conn,
                    str(access["frame_id"]),
                )
                verify_global_role_registry(conn, frame=released_frame)
                self._verify_role_projection(conn, released_frame)
                verified_access = verify_terminal_access_row(
                    conn,
                    row=access,
                    released_frame=released_frame,
                )
        return {
            **frame,
            "roleCount": len(frame["roleAssignments"]),
            "terminalAccessConsumed": access is not None,
            "terminalAccess": verified_access,
        }
