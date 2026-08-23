"""Append-only, study-scoped human judgments and gated reads."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional

from .frame_validation import json_value, require_text
from .global_roles import verify_global_role_registry
from .judgment_rows import (
    current_study_rows,
    readable_study_rows,
)
from .ontology_contract import verified_study_community_ids
from .schema import now_iso, validate_confidence, validate_judgment
from .study_access import (
    access_filter_for_purpose,
    accounts_for_purpose,
    assert_study_open,
)
from .study_binding import validate_study_binding


def _optional_text(value: Optional[str], *, field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text or null")
    return value


def _canonical_json(value: Any, *, field: str) -> Optional[str]:
    if value is None:
        return None
    normalized = json_value(value, field=field)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


class CommunityGoldJudgmentMixin:
    """Persist corrections as history while moving a separate current head."""

    def record_study_judgment(
        self,
        *,
        frame_id: str,
        account_id: str,
        community_id: str,
        reviewer: str,
        judgment: Any,
        evidence_snapshot_id: str,
        evidence_snapshot_hash: str,
        context_hash: str,
        observed_at: str,
        confidence: Any = None,
        note: Optional[str] = None,
        evidence: Optional[Any] = None,
    ) -> Dict[str, Any]:
        actor = require_text(reviewer, field="reviewer")
        parsed_judgment = validate_judgment(judgment)
        parsed_confidence = validate_confidence(confidence)
        parsed_note = _optional_text(note, field="note")
        evidence_json = _canonical_json(evidence, field="evidence")
        created_at = now_iso()

        with self._open() as conn:
            binding = validate_study_binding(
                self,
                conn,
                frame_id=frame_id,
                account_id=account_id,
                community_id=community_id,
                evidence_snapshot_id=evidence_snapshot_id,
                evidence_snapshot_hash=evidence_snapshot_hash,
                context_hash=context_hash,
                observed_at=observed_at,
            )
            scope = binding.scope
            conn.execute("BEGIN IMMEDIATE")
            try:
                assert_study_open(
                    conn,
                    frame_id=binding.frame_id,
                    operation="judgment writes",
                )
                prior = conn.execute(
                    """
                    SELECT label_set_id
                    FROM account_community_gold_head
                    WHERE frame_id = ? AND account_id = ?
                      AND community_id = ? AND reviewer = ?
                    """,
                    (
                        binding.frame_id,
                        binding.account_id,
                        binding.community_id,
                        actor,
                    ),
                ).fetchone()
                supersedes = (
                    int(prior["label_set_id"])
                    if prior is not None
                    else None
                )
                cursor = conn.execute(
                    """
                    INSERT INTO account_community_gold_label_set
                    (account_id, community_id, reviewer, judgment, confidence,
                     note, evidence_json, is_active, created_at,
                     supersedes_label_set_id, user_id, ontology_id,
                     ontology_version, task_id, study_frame_id,
                     evidence_snapshot_id, evidence_snapshot_hash,
                     context_hash, observed_at, identity_status)
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, 'scoped'
                    )
                    """,
                    (
                        binding.account_id,
                        binding.community_id,
                        actor,
                        parsed_judgment,
                        parsed_confidence,
                        parsed_note,
                        evidence_json,
                        created_at,
                        supersedes,
                        scope["userId"],
                        scope["ontologyId"],
                        scope["ontologyVersion"],
                        scope["taskId"],
                        binding.frame_id,
                        binding.evidence_snapshot_id,
                        binding.evidence_snapshot_hash,
                        binding.context_hash,
                        binding.observed_at,
                    ),
                )
                label_set_id = int(cursor.lastrowid)
                conn.execute(
                    """
                    INSERT INTO account_community_gold_head
                    (frame_id, account_id, community_id, reviewer,
                     label_set_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(frame_id, account_id, community_id, reviewer)
                    DO UPDATE SET
                        label_set_id = excluded.label_set_id,
                        updated_at = excluded.updated_at
                    """,
                    (
                        binding.frame_id,
                        binding.account_id,
                        binding.community_id,
                        actor,
                        label_set_id,
                        created_at,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "labelSetId": label_set_id,
            "frameId": binding.frame_id,
            "accountId": binding.account_id,
            "communityId": binding.community_id,
            "reviewer": actor,
            "judgment": parsed_judgment,
            "confidence": parsed_confidence,
            "role": binding.role,
            "ontologyScope": dict(scope),
            "createdAt": created_at,
            "supersedesLabelSetId": supersedes,
        }

    def list_study_judgments(
        self,
        *,
        frame_id: str,
        purpose: str,
        reviewer: Optional[str] = None,
        accessed_by: Optional[str] = None,
        access_receipt: Optional[Mapping[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        parsed_frame = require_text(frame_id, field="frame_id")
        parsed_reviewer = (
            require_text(reviewer, field="reviewer")
            if reviewer is not None
            else None
        )
        is_terminal = purpose == "terminal_evaluation"
        if is_terminal and parsed_reviewer is None:
            raise ValueError(
                "reviewer is required for terminal release coverage"
            )
        if is_terminal:
            release = self.release_terminal_test(
                frame_id=parsed_frame,
                reviewer=parsed_reviewer,
                accessed_by=accessed_by,
                access_receipt=access_receipt,
            )
            return release["judgments"]
        with self._open() as conn:
            frame = self._load_study_frame_with_conn(
                conn,
                parsed_frame,
            )
            verify_global_role_registry(conn, frame=frame)
            self._verify_role_projection(conn, frame)
            ontology_communities = verified_study_community_ids(
                conn,
                scope=frame["scope"],
            )
            allowed = accounts_for_purpose(frame, purpose)
            allowed_roles, fixed_accounts = access_filter_for_purpose(
                frame,
                purpose,
            )
            rows = current_study_rows(
                conn,
                frame_id=parsed_frame,
                reviewer=parsed_reviewer,
                allowed_roles=allowed_roles,
                fixed_accounts=fixed_accounts,
            )
            output = readable_study_rows(
                rows,
                frame=frame,
                allowed_accounts=allowed,
                ontology_community_ids=ontology_communities,
            )
        return output
