"""Validation and projection checks for immutable ontology definitions."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Mapping, Tuple

from src.artifacts.digests import json_sha256

from .frame_validation import json_value, require_text

_TARGET_TYPES = frozenset(
    {"affiliation", "competence", "participation_interest"}
)


def positive_version(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def canonical_json_hash(value: Mapping[str, Any]) -> Tuple[str, str]:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
        json_sha256(value),
    )


def normalize_ontology_definition(
    definition: Mapping[str, Any],
) -> tuple[Dict[str, Any], list[Dict[str, str]]]:
    normalized = json_value(definition, field="definition")
    if not isinstance(normalized, dict):
        raise ValueError("definition must be an object")
    groups = normalized.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("definition.groups must be a non-empty list")

    projection = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise ValueError(f"definition.groups[{index}] must be an object")
        community_id = require_text(
            group.get("communityId"),
            field=f"definition.groups[{index}].communityId",
        )
        boundary = require_text(
            group.get("definition"),
            field=f"definition.groups[{index}].definition",
        )
        group["communityId"] = community_id
        group["definition"] = boundary
        projection.append(
            {
                "communityId": community_id,
                "definition": boundary,
            }
        )
    community_ids = [row["communityId"] for row in projection]
    if len(community_ids) != len(set(community_ids)):
        raise ValueError(
            "definition.groups contains duplicate communityId values"
        )
    return normalized, projection


def normalize_task_definition(
    definition: Mapping[str, Any],
) -> Dict[str, Any]:
    normalized = json_value(definition, field="definition")
    if not isinstance(normalized, dict) or not normalized:
        raise ValueError("task definition must be a non-empty object")
    return normalized


def verify_stored_definition(
    *,
    stored_json: Any,
    stored_hash: Any,
    expected_json: str,
    expected_hash: str,
    record_name: str,
) -> None:
    parsed = json.loads(str(stored_json))
    observed_hash = json_sha256(parsed)
    if (
        observed_hash != str(stored_hash)
        or str(stored_hash) != expected_hash
        or str(stored_json) != expected_json
    ):
        raise ValueError(
            f"immutable {record_name} already exists with different content"
        )


def verify_group_projection(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    ontology_id: str,
    ontology_version: int,
    expected: list[Dict[str, str]],
) -> None:
    rows = conn.execute(
        """
        SELECT community_id, boundary_definition
        FROM personal_ontology_group
        WHERE user_id = ? AND ontology_id = ? AND ontology_version = ?
        ORDER BY community_id
        """,
        (user_id, ontology_id, ontology_version),
    ).fetchall()
    observed = sorted(
        [
            {
                "communityId": str(row["community_id"]),
                "definition": str(row["boundary_definition"]),
            }
            for row in rows
        ],
        key=lambda row: row["communityId"],
    )
    if observed != sorted(expected, key=lambda row: row["communityId"]):
        raise ValueError(
            "immutable ontology group projection differs from its definition"
        )


def verified_ontology_community_ids(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    ontology_id: str,
    ontology_version: int,
) -> set[str]:
    row = conn.execute(
        """
        SELECT definition_json, definition_hash
        FROM personal_ontology_version
        WHERE user_id = ? AND ontology_id = ? AND ontology_version = ?
        """,
        (user_id, ontology_id, ontology_version),
    ).fetchone()
    if row is None:
        raise ValueError("study ontology version does not exist")
    try:
        parsed = json.loads(str(row["definition_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "immutable ontology definition JSON is invalid"
        ) from exc
    canonical, groups = normalize_ontology_definition(parsed)
    canonical_json, canonical_hash = canonical_json_hash(canonical)
    if (
        str(row["definition_json"]) != canonical_json
        or str(row["definition_hash"]) != canonical_hash
    ):
        raise ValueError(
            "immutable ontology definition hash/canonical JSON mismatch"
        )
    verify_group_projection(
        conn,
        user_id=user_id,
        ontology_id=ontology_id,
        ontology_version=ontology_version,
        expected=groups,
    )
    return {group["communityId"] for group in groups}


def verified_study_community_ids(
    conn: sqlite3.Connection,
    *,
    scope: Mapping[str, Any],
) -> set[str]:
    """Verify the immutable ontology and task records bound to a study."""

    community_ids = verified_ontology_community_ids(
        conn,
        user_id=str(scope["userId"]),
        ontology_id=str(scope["ontologyId"]),
        ontology_version=int(scope["ontologyVersion"]),
    )
    row = conn.execute(
        """
        SELECT target_type, definition_json, definition_hash
        FROM personal_ontology_task
        WHERE user_id = ? AND ontology_id = ?
          AND ontology_version = ? AND task_id = ?
        """,
        (
            scope["userId"],
            scope["ontologyId"],
            scope["ontologyVersion"],
            scope["taskId"],
        ),
    ).fetchone()
    if row is None:
        raise ValueError("study ontology task does not exist")
    target_type = str(row["target_type"])
    if target_type not in _TARGET_TYPES:
        raise ValueError(
            f"stored ontology task target_type is invalid: {target_type}"
        )
    try:
        parsed = json.loads(str(row["definition_json"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "immutable ontology task definition JSON is invalid"
        ) from exc
    normalized = normalize_task_definition(parsed)
    canonical_json, canonical_hash = canonical_json_hash(normalized)
    if (
        str(row["definition_json"]) != canonical_json
        or str(row["definition_hash"]) != canonical_hash
    ):
        raise ValueError(
            "immutable ontology task definition hash/canonical JSON mismatch"
        )
    return community_ids
