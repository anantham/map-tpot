"""Immutable personal-ontology and task registration."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .frame_validation import require_text
from .ontology_contract import (
    canonical_json_hash,
    normalize_ontology_definition,
    normalize_task_definition,
    positive_version,
    verify_group_projection,
    verify_stored_definition,
)
from .schema import now_iso

TARGET_TYPES = frozenset(
    {"affiliation", "competence", "participation_interest"}
)


class CommunityGoldOntologyMixin:
    """Register ontology versions and task definitions without overwrite."""

    def register_ontology_version(
        self,
        *,
        user_id: str,
        ontology_id: str,
        ontology_version: int,
        definition: Mapping[str, Any],
        supersedes_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        user = require_text(user_id, field="user_id")
        ontology = require_text(ontology_id, field="ontology_id")
        version = positive_version(
            ontology_version,
            field="ontology_version",
        )
        prior_version = (
            positive_version(
                supersedes_version,
                field="supersedes_version",
            )
            if supersedes_version is not None
            else None
        )
        if prior_version == version:
            raise ValueError("supersedes_version must differ from ontology_version")
        normalized, groups = normalize_ontology_definition(definition)
        community_ids = [row["communityId"] for row in groups]
        definition_json, definition_hash = canonical_json_hash(
            normalized
        )
        with self._open() as conn:
            self._assert_community_table(conn)
            missing = [
                community_id
                for community_id in community_ids
                if conn.execute(
                    "SELECT 1 FROM community WHERE id = ?",
                    (community_id,),
                ).fetchone()
                is None
            ]
            if missing:
                raise ValueError(
                    f"ontology definition references missing communities: {missing}"
                )
            if prior_version is not None:
                prior = conn.execute(
                    """
                    SELECT 1
                    FROM personal_ontology_version
                    WHERE user_id = ? AND ontology_id = ?
                      AND ontology_version = ?
                    """,
                    (user, ontology, prior_version),
                ).fetchone()
                if prior is None:
                    raise ValueError(
                        f"supersedes_version {prior_version} does not exist"
                    )
            existing = conn.execute(
                """
                SELECT definition_json, definition_hash,
                       supersedes_version, created_at
                FROM personal_ontology_version
                WHERE user_id = ? AND ontology_id = ? AND ontology_version = ?
                """,
                (user, ontology, version),
            ).fetchone()
            if existing is not None:
                if existing["supersedes_version"] != prior_version:
                    raise ValueError(
                        "immutable ontology version already exists with "
                        "different content"
                    )
                verify_stored_definition(
                    stored_json=existing["definition_json"],
                    stored_hash=existing["definition_hash"],
                    expected_json=definition_json,
                    expected_hash=definition_hash,
                    record_name="ontology version",
                )
                verify_group_projection(
                    conn,
                    user_id=user,
                    ontology_id=ontology,
                    ontology_version=version,
                    expected=groups,
                )
                return {
                    "created": False,
                    "userId": user,
                    "ontologyId": ontology,
                    "ontologyVersion": version,
                    "definitionHash": definition_hash,
                    "supersedesVersion": prior_version,
                    "createdAt": existing["created_at"],
                }
            created_at = now_iso()
            conn.execute(
                """
                INSERT INTO personal_ontology_version
                (user_id, ontology_id, ontology_version, definition_json,
                 definition_hash, supersedes_version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user,
                    ontology,
                    version,
                    definition_json,
                    definition_hash,
                    prior_version,
                    created_at,
                ),
            )
            conn.executemany(
                """
                INSERT INTO personal_ontology_group
                (user_id, ontology_id, ontology_version, community_id,
                 boundary_definition)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        user,
                        ontology,
                        version,
                        group["communityId"],
                        group["definition"],
                    )
                    for group in groups
                ],
            )
            conn.commit()
        return {
            "created": True,
            "userId": user,
            "ontologyId": ontology,
            "ontologyVersion": version,
            "definitionHash": definition_hash,
            "supersedesVersion": prior_version,
            "createdAt": created_at,
        }

    def register_ontology_task(
        self,
        *,
        user_id: str,
        ontology_id: str,
        ontology_version: int,
        task_id: str,
        target_type: str,
        definition: Mapping[str, Any],
    ) -> Dict[str, Any]:
        user = require_text(user_id, field="user_id")
        ontology = require_text(ontology_id, field="ontology_id")
        version = positive_version(
            ontology_version,
            field="ontology_version",
        )
        task = require_text(task_id, field="task_id")
        target = require_text(target_type, field="target_type")
        if target not in TARGET_TYPES:
            raise ValueError(
                f"target_type must be one of: {', '.join(sorted(TARGET_TYPES))}"
            )
        normalized = normalize_task_definition(definition)
        definition_json, definition_hash = canonical_json_hash(
            normalized
        )
        with self._open() as conn:
            ontology_row = conn.execute(
                """
                SELECT 1
                FROM personal_ontology_version
                WHERE user_id = ? AND ontology_id = ? AND ontology_version = ?
                """,
                (user, ontology, version),
            ).fetchone()
            if ontology_row is None:
                raise ValueError(
                    "ontology version must be registered before its task"
                )
            existing = conn.execute(
                """
                SELECT target_type, definition_json,
                       definition_hash, created_at
                FROM personal_ontology_task
                WHERE user_id = ? AND ontology_id = ?
                  AND ontology_version = ? AND task_id = ?
                """,
                (user, ontology, version, task),
            ).fetchone()
            if existing is not None:
                if str(existing["target_type"]) != target:
                    raise ValueError(
                        "immutable ontology task already exists with "
                        "different content"
                    )
                verify_stored_definition(
                    stored_json=existing["definition_json"],
                    stored_hash=existing["definition_hash"],
                    expected_json=definition_json,
                    expected_hash=definition_hash,
                    record_name="ontology task",
                )
                return {
                    "created": False,
                    "taskId": task,
                    "targetType": target,
                    "definitionHash": definition_hash,
                    "createdAt": existing["created_at"],
                }
            created_at = now_iso()
            conn.execute(
                """
                INSERT INTO personal_ontology_task
                (user_id, ontology_id, ontology_version, task_id, target_type,
                 definition_json, definition_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user,
                    ontology,
                    version,
                    task,
                    target,
                    definition_json,
                    definition_hash,
                    created_at,
                ),
            )
            conn.commit()
        return {
            "created": True,
            "taskId": task,
            "targetType": target,
            "definitionHash": definition_hash,
            "createdAt": created_at,
        }
