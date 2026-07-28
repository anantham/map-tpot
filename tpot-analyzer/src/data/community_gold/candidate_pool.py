"""Candidate-source assembly for account-community review queues."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from .artifacts import SnapshotArtifacts
from .schema import split_for_account

SOURCE_POOL_LIMIT = 120
GRAPH_POOL_LIMIT = 240


class CommunityGoldCandidatePoolMixin:
    """Build review pools without deciding how candidates are ranked."""

    def _candidate_pool(
        self,
        *,
        conn: sqlite3.Connection,
        artifacts: SnapshotArtifacts,
        community: Dict[str, Any],
        reviewer: str,
        split: Optional[str],
    ) -> tuple[Dict[str, Dict[str, Any]], set[str], List[str], List[str]]:
        active_rows = conn.execute(
            """
            SELECT ls.account_id, ls.judgment, s.split
            FROM account_community_gold_label_set ls
            JOIN account_community_gold_split s ON s.account_id = ls.account_id
            WHERE ls.community_id = ? AND ls.reviewer = ? AND ls.is_active = 1
              AND ls.identity_status = 'legacy_unbound'
            """,
            (community["communityId"], reviewer),
        ).fetchall()
        active_ids = {str(row["account_id"]) for row in active_rows}
        train_positive = [
            str(row["account_id"])
            for row in active_rows
            if row["split"] == "train" and row["judgment"] == "in"
        ]
        train_negative = [
            str(row["account_id"])
            for row in active_rows
            if row["split"] == "train" and row["judgment"] == "out"
        ]

        candidate_map: Dict[str, Dict[str, Any]] = {}
        self._merge_candidate_rows(
            candidate_map,
            conn.execute(
                """
                SELECT ca.account_id, p.username, p.display_name, ca.weight
                FROM community_account ca
                LEFT JOIN profiles p ON p.account_id = ca.account_id
                WHERE ca.community_id = ?
                ORDER BY ca.weight DESC, ca.account_id ASC
                LIMIT ?
                """,
                (community["communityId"], SOURCE_POOL_LIMIT),
            ).fetchall(),
        )
        if community.get("seededFromRun") and community.get("seededFromIdx") is not None:
            self._merge_candidate_rows(
                candidate_map,
                conn.execute(
                    """
                    SELECT cm.account_id, p.username, p.display_name, cm.weight
                    FROM community_membership cm
                    LEFT JOIN profiles p ON p.account_id = cm.account_id
                    WHERE cm.run_id = ? AND cm.community_idx = ?
                    ORDER BY cm.weight DESC, cm.account_id ASC
                    LIMIT ?
                    """,
                    (
                        community["seededFromRun"],
                        int(community["seededFromIdx"]),
                        SOURCE_POOL_LIMIT,
                    ),
                ).fetchall(),
                score_key="nmfSeededWeight",
            )
        try:
            for account_id in artifacts.load_node_ids()[:GRAPH_POOL_LIMIT]:
                account_id = str(account_id)
                if split is not None and split_for_account(account_id) != split:
                    continue
                candidate_map.setdefault(
                    account_id,
                    {"accountId": account_id, "inGraph": True},
                )
                candidate_map[account_id]["inGraph"] = True
        except FileNotFoundError:
            pass

        missing = [
            account_id
            for account_id, row in candidate_map.items()
            if row.get("username") is None
        ]
        if missing:
            placeholders = ",".join("?" * len(missing))
            for row in conn.execute(
                f"""
                SELECT account_id, username, display_name
                FROM profiles
                WHERE account_id IN ({placeholders})
                """,
                tuple(missing),
            ).fetchall():
                candidate_map[str(row["account_id"])]["username"] = row["username"]
                candidate_map[str(row["account_id"])]["displayName"] = row["display_name"]
        return candidate_map, active_ids, train_positive, train_negative

    def _merge_candidate_rows(
        self,
        candidate_map: Dict[str, Dict[str, Any]],
        rows: Iterable[sqlite3.Row],
        *,
        score_key: str = "canonicalWeight",
    ) -> None:
        for row in rows:
            account_id = str(row["account_id"])
            candidate = candidate_map.setdefault(
                account_id,
                {"accountId": account_id, "inGraph": False},
            )
            candidate["username"] = candidate.get("username") or row["username"]
            candidate["displayName"] = (
                candidate.get("displayName") or row["display_name"]
            )
            candidate[score_key] = float(row["weight"])
