"""Immutable global account-role registries shared across study frames."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Mapping

from src.artifacts.digests import json_sha256


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _global_rows(frame: Mapping[str, Any]) -> list[Dict[str, Any]]:
    by_account = {
        str(row["accountId"]): dict(row)
        for row in frame["roleAssignments"]
    }
    for account_id in frame["fixedTrainingIds"]:
        by_account[str(account_id)] = {
            "accountId": str(account_id),
            "assignedRole": "fixed_training",
            "roleRegistryId": frame["roleRegistry"]["id"],
        }
    for account_id in frame["fixedChallengeIds"]:
        by_account[str(account_id)] = {
            "accountId": str(account_id),
            "assignedRole": "fixed_challenge",
            "roleRegistryId": frame["roleRegistry"]["id"],
        }
    missing = [
        account_id
        for account_id in frame["u0AccountIds"]
        if account_id not in by_account
    ]
    if missing:
        raise ValueError(
            f"global role projection is missing U0 accounts: {missing}"
        )
    return [by_account[account_id] for account_id in frame["u0AccountIds"]]


def registry_payload(frame: Mapping[str, Any]) -> Dict[str, Any]:
    rows = _global_rows(frame)
    return {
        "schemaVersion": 1,
        "roleRegistry": frame["roleRegistry"],
        "u0Digest": frame["u0Digest"],
        "uEvalDigest": frame["uEvalDigest"],
        "fixedTrainingIds": frame["fixedTrainingIds"],
        "fixedChallengeIds": frame["fixedChallengeIds"],
        "randomizationAudit": frame["randomizationAudit"],
        "globalRolesDigest": json_sha256(rows),
    }


def persist_global_role_registry(
    conn: sqlite3.Connection,
    *,
    frame: Mapping[str, Any],
    created_at: str,
) -> None:
    registry_id = str(frame["roleRegistry"]["id"])
    payload = registry_payload(frame)
    payload_json = _canonical_json(payload)
    payload_digest = json_sha256(payload)
    existing = conn.execute(
        """
        SELECT registry_json, registry_digest
        FROM account_community_role_registry
        WHERE role_registry_id = ?
        """,
        (registry_id,),
    ).fetchone()
    if existing is not None:
        stored_json = str(existing["registry_json"])
        stored_digest = str(existing["registry_digest"])
        if (
            json_sha256(json.loads(stored_json)) != stored_digest
            or stored_digest != payload_digest
            or stored_json != payload_json
        ):
            raise ValueError(
                f"immutable role registry '{registry_id}' already exists "
                "with a different global allocation"
            )
        verify_global_role_registry(conn, frame=frame)
        return

    rows = _global_rows(frame)
    placeholders = ",".join("?" for _ in rows)
    overlaps = conn.execute(
        f"""
        SELECT account_id, role_registry_id
        FROM account_community_global_role
        WHERE account_id IN ({placeholders})
          AND role_registry_id <> ?
        ORDER BY account_id
        """,
        (*[row["accountId"] for row in rows], registry_id),
    ).fetchall()
    if overlaps:
        sample = [
            {
                "accountId": str(row["account_id"]),
                "existingRoleRegistryId": str(row["role_registry_id"]),
            }
            for row in overlaps[:10]
        ]
        raise ValueError(
            "global account roles cannot be reassigned by selecting a new "
            f"role_registry_id; overlapping accounts={sample}"
        )

    conn.execute(
        """
        INSERT INTO account_community_role_registry
        (role_registry_id, registry_json, registry_digest, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (registry_id, payload_json, payload_digest, created_at),
    )
    conn.executemany(
        """
        INSERT INTO account_community_global_role
        (role_registry_id, account_id, assigned_role, role_json, role_hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                registry_id,
                row["accountId"],
                row["assignedRole"],
                _canonical_json(row),
                json_sha256(row),
            )
            for row in rows
        ],
    )


def verify_global_role_registry(
    conn: sqlite3.Connection,
    *,
    frame: Mapping[str, Any],
) -> None:
    registry_id = str(frame["roleRegistry"]["id"])
    expected_payload = registry_payload(frame)
    expected_payload_json = _canonical_json(expected_payload)
    expected_payload_digest = json_sha256(expected_payload)
    registry = conn.execute(
        """
        SELECT registry_json, registry_digest
        FROM account_community_role_registry
        WHERE role_registry_id = ?
        """,
        (registry_id,),
    ).fetchone()
    if registry is None:
        raise ValueError(f"global role registry '{registry_id}' is missing")
    stored_registry_json = str(registry["registry_json"])
    stored_registry_digest = str(registry["registry_digest"])
    if (
        json_sha256(json.loads(stored_registry_json))
        != stored_registry_digest
        or stored_registry_digest != expected_payload_digest
        or stored_registry_json != expected_payload_json
    ):
        raise ValueError(
            f"global role registry '{registry_id}' content mismatch"
        )
    expected_rows = _global_rows(frame)
    rows = conn.execute(
        """
        SELECT account_id, assigned_role, role_json, role_hash
        FROM account_community_global_role
        WHERE role_registry_id = ?
        """,
        (registry_id,),
    ).fetchall()
    if len(rows) != len(expected_rows):
        raise ValueError(
            "global role projection mismatch: "
            f"expected {len(expected_rows)} rows, observed {len(rows)}"
        )
    by_account = {str(row["account_id"]): row for row in rows}
    observed = []
    for expected in expected_rows:
        row = by_account.get(str(expected["accountId"]))
        if row is None:
            raise ValueError(
                "global role projection mismatch: missing account "
                f"{expected['accountId']}"
            )
        stored = json.loads(str(row["role_json"]))
        if (
            str(row["assigned_role"]) != expected["assignedRole"]
            or json_sha256(stored) != str(row["role_hash"])
            or stored != expected
        ):
            raise ValueError(
                "global role projection mismatch for account "
                f"{expected['accountId']}"
            )
        observed.append(stored)
    if json_sha256(observed) != expected_payload["globalRolesDigest"]:
        raise ValueError("global role projection digest mismatch")
