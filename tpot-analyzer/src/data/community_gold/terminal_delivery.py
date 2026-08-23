"""Create or safely replay one immutable terminal-test release."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Mapping, NoReturn, Optional

from src.artifacts.digests import json_sha256

from .frame_validation import require_text
from .global_roles import verify_global_role_registry
from .judgment_rows import current_study_rows, readable_study_rows
from .ontology_contract import verified_study_community_ids
from .study_access import (
    access_filter_for_purpose,
    accounts_for_purpose,
    consume_terminal_access,
)
from .terminal_contract import normalize_terminal_receipt
from .terminal_release import (
    build_terminal_release_manifest,
    verify_terminal_access_row,
)


class TerminalReleaseConflict(ValueError):
    """A consumed generation was requested with a different identity."""


def _conflict(existing: sqlite3.Row, reason: str) -> NoReturn:
    raise TerminalReleaseConflict(
        "terminal release conflict: evaluation generation is already "
        f"consumed by frame '{existing['frame_id']}'; {reason}"
    )


def _terminal_access_row(
    conn: sqlite3.Connection,
    *,
    role_registry_id: str,
) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM account_community_terminal_test_access
        WHERE role_registry_id = ?
        """,
        (role_registry_id,),
    ).fetchone()


def _request_identity(
    *,
    reviewer: Any,
    accessed_by: Any,
    access_receipt: Any,
) -> tuple[str, str, Dict[str, Any], str]:
    parsed_reviewer = require_text(reviewer, field="reviewer")
    normalized_receipt = normalize_terminal_receipt(access_receipt)
    actor = require_text(accessed_by, field="accessed_by")
    return (
        parsed_reviewer,
        actor,
        normalized_receipt,
        json_sha256(normalized_receipt),
    )


def _replay_identity(
    *,
    existing: sqlite3.Row,
    frame: Mapping[str, Any],
    reviewer: Any,
    accessed_by: Any,
    access_receipt: Any,
) -> str:
    try:
        parsed_reviewer, actor, _receipt, receipt_hash = (
            _request_identity(
                reviewer=reviewer,
                accessed_by=accessed_by,
                access_receipt=access_receipt,
            )
        )
    except ValueError:
        _conflict(existing, "request identity is invalid or differs")
    expected = {
        "frame_id": str(frame["frameId"]),
        "role_registry_id": str(frame["roleRegistry"]["id"]),
        "accessed_by": actor,
        "access_receipt_hash": receipt_hash,
    }
    if any(existing[field] != value for field, value in expected.items()):
        _conflict(existing, "request frame, actor, or receipt differs")
    return parsed_reviewer


def _release_payload(
    conn: sqlite3.Connection,
    *,
    frame: Mapping[str, Any],
    reviewer: str,
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    ontology_communities = verified_study_community_ids(
        conn,
        scope=frame["scope"],
    )
    allowed = accounts_for_purpose(frame, "terminal_evaluation")
    allowed_roles, fixed_accounts = access_filter_for_purpose(
        frame,
        "terminal_evaluation",
    )
    stored_rows = current_study_rows(
        conn,
        frame_id=str(frame["frameId"]),
        reviewer=reviewer,
        allowed_roles=allowed_roles,
        fixed_accounts=fixed_accounts,
    )
    judgments = readable_study_rows(
        stored_rows,
        frame=frame,
        allowed_accounts=allowed,
        ontology_community_ids=ontology_communities,
    )
    manifest = build_terminal_release_manifest(
        conn,
        frame=frame,
        rows=judgments,
        reviewer=reviewer,
        terminal_account_ids=allowed,
    )
    return judgments, manifest


def _verified_delivery(
    conn: sqlite3.Connection,
    *,
    frame: Mapping[str, Any],
    access_row: sqlite3.Row,
    reviewer: str,
    replayed: bool,
) -> Dict[str, Any]:
    terminal_access = verify_terminal_access_row(
        conn,
        row=access_row,
        released_frame=frame,
    )
    if terminal_access["reviewer"] != reviewer:
        _conflict(access_row, "reviewer differs")
    judgments, manifest = _release_payload(
        conn,
        frame=frame,
        reviewer=reviewer,
    )
    observed_hash = json_sha256(manifest)
    if observed_hash != terminal_access["releaseManifestHash"]:
        raise ValueError(
            "terminal replay payload differs from its immutable "
            "release manifest"
        )
    return {
        "judgments": judgments,
        "terminalAccess": terminal_access,
        "replayed": replayed,
    }


class CommunityGoldTerminalDeliveryMixin:
    """Expose one logical release with same-receipt replay."""

    def release_terminal_test(
        self,
        *,
        frame_id: str,
        reviewer: Any,
        accessed_by: Any,
        access_receipt: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        """Create/replay a release; accessed_by is caller-asserted for now."""

        parsed_frame = require_text(frame_id, field="frame_id")
        with self._open() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                frame = self._load_study_frame_with_conn(
                    conn,
                    parsed_frame,
                )
                verify_global_role_registry(conn, frame=frame)
                self._verify_role_projection(conn, frame)
                role_registry_id = str(frame["roleRegistry"]["id"])
                existing = _terminal_access_row(
                    conn,
                    role_registry_id=role_registry_id,
                )
                if existing is not None:
                    parsed_reviewer = _replay_identity(
                        existing=existing,
                        frame=frame,
                        reviewer=reviewer,
                        accessed_by=accessed_by,
                        access_receipt=access_receipt,
                    )
                    result = _verified_delivery(
                        conn,
                        frame=frame,
                        access_row=existing,
                        reviewer=parsed_reviewer,
                        replayed=True,
                    )
                    conn.commit()
                    return result

                (
                    parsed_reviewer,
                    actor,
                    normalized_receipt,
                    _receipt_hash,
                ) = _request_identity(
                    reviewer=reviewer,
                    accessed_by=accessed_by,
                    access_receipt=access_receipt,
                )
                judgments, release_manifest = _release_payload(
                    conn,
                    frame=frame,
                    reviewer=parsed_reviewer,
                )
                consume_terminal_access(
                    conn,
                    frame=frame,
                    accessed_by=actor,
                    access_receipt=normalized_receipt,
                    release_manifest=release_manifest,
                )
                inserted = _terminal_access_row(
                    conn,
                    role_registry_id=role_registry_id,
                )
                if inserted is None:
                    raise RuntimeError(
                        "terminal release insert was not observable "
                        "before commit"
                    )
                result = _verified_delivery(
                    conn,
                    frame=frame,
                    access_row=inserted,
                    reviewer=parsed_reviewer,
                    replayed=False,
                )
                if result["judgments"] != judgments:
                    raise ValueError(
                        "verified terminal release differs from its "
                        "pre-insert payload"
                    )
                conn.commit()
                return result
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
