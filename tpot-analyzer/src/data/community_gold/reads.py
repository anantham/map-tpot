"""Read/query helpers for account-community gold labels."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .constants import JUDGMENT_NAMES, SPLIT_NAMES
from .schema import validate_judgment


class CommunityGoldReadMixin:
    def list_labels(
        self,
        *,
        community_id: Optional[str] = None,
        account_id: Optional[str] = None,
        split: Optional[str] = None,
        reviewer: Optional[str] = None,
        judgment: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if split not in {None, *SPLIT_NAMES}:
            raise ValueError("split must be one of: train, dev, test")
        if judgment is not None:
            judgment = validate_judgment(judgment)

        conditions = []
        params: List[Any] = []
        if not include_inactive:
            conditions.append("ls.is_active = 1")
        if community_id is not None:
            conditions.append("ls.community_id = ?")
            params.append(community_id)
        if account_id is not None:
            conditions.append("ls.account_id = ?")
            params.append(account_id)
        if split is not None:
            conditions.append("s.split = ?")
            params.append(split)
        if reviewer is not None:
            conditions.append("ls.reviewer = ?")
            params.append(reviewer)
        if judgment is not None:
            conditions.append("ls.judgment = ?")
            params.append(judgment)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._open() as conn:
            self._assert_community_table(conn)
            rows = conn.execute(
                f"""
                SELECT ls.id, ls.account_id, ls.community_id, ls.reviewer, ls.judgment,
                       ls.confidence, ls.note, ls.evidence_json, ls.is_active, ls.created_at,
                       ls.supersedes_label_set_id, s.split, c.name AS community_name,
                       c.color AS community_color, p.username, p.display_name,
                       ca.weight AS canonical_weight, ca.source AS canonical_source
                FROM account_community_gold_label_set ls
                JOIN account_community_gold_split s ON s.account_id = ls.account_id
                JOIN community c ON c.id = ls.community_id
                LEFT JOIN profiles p ON p.account_id = ls.account_id
                LEFT JOIN community_account ca
                    ON ca.account_id = ls.account_id AND ca.community_id = ls.community_id
                {where_clause}
                ORDER BY ls.created_at DESC, ls.id DESC
                LIMIT ?
                """,
                (*params, int(limit)),
            ).fetchall()
        return [
            {
                "labelSetId": int(row["id"]),
                "accountId": str(row["account_id"]),
                "communityId": str(row["community_id"]),
                "communityName": row["community_name"],
                "communityColor": row["community_color"],
                "username": row["username"],
                "displayName": row["display_name"],
                "reviewer": row["reviewer"],
                "judgment": row["judgment"],
                "confidence": float(row["confidence"]) if row["confidence"] is not None else None,
                "note": row["note"],
                "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else None,
                "split": row["split"],
                "isActive": bool(int(row["is_active"])),
                "createdAt": row["created_at"],
                "supersedesLabelSetId": (
                    int(row["supersedes_label_set_id"])
                    if row["supersedes_label_set_id"] is not None
                    else None
                ),
                "canonicalMembershipWeight": (
                    float(row["canonical_weight"]) if row["canonical_weight"] is not None else None
                ),
                "canonicalMembershipSource": row["canonical_source"],
            }
            for row in rows
        ]

    def _list_communities_with_conn(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.color,
                   COALESCE(cm.member_count, 0) AS canonical_member_count,
                   COALESCE(gl.active_label_count, 0) AS active_label_count,
                   COALESCE(gl.in_count, 0) AS in_count,
                   COALESCE(gl.out_count, 0) AS out_count,
                   COALESCE(gl.abstain_count, 0) AS abstain_count
            FROM community c
            LEFT JOIN (
                SELECT community_id, COUNT(*) AS member_count
                FROM community_account
                GROUP BY community_id
            ) cm ON cm.community_id = c.id
            LEFT JOIN (
                SELECT community_id,
                       COUNT(*) AS active_label_count,
                       SUM(CASE WHEN judgment = 'in' THEN 1 ELSE 0 END) AS in_count,
                       SUM(CASE WHEN judgment = 'out' THEN 1 ELSE 0 END) AS out_count,
                       SUM(CASE WHEN judgment = 'abstain' THEN 1 ELSE 0 END) AS abstain_count
                FROM account_community_gold_label_set
                WHERE is_active = 1
                GROUP BY community_id
            ) gl ON gl.community_id = c.id
            ORDER BY canonical_member_count DESC, c.name ASC
            """
        ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "color": row["color"],
                "canonicalMemberCount": int(row["canonical_member_count"]),
                "goldLabelCount": int(row["active_label_count"]),
                "goldJudgmentCounts": {
                    "in": int(row["in_count"]),
                    "out": int(row["out_count"]),
                    "abstain": int(row["abstain_count"]),
                },
            }
            for row in rows
        ]

    def list_communities(self) -> List[Dict[str, Any]]:
        with self._open() as conn:
            self._assert_community_table(conn)
            return self._list_communities_with_conn(conn)

    def metrics(self) -> Dict[str, Any]:
        with self._open() as conn:
            self._assert_community_table(conn)
            total_active_labels = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM account_community_gold_label_set WHERE is_active = 1"
                ).fetchone()["n"]
            )
            labeled_account_count = int(
                conn.execute(
                    """
                    SELECT COUNT(DISTINCT account_id) AS n
                    FROM account_community_gold_label_set
                    WHERE is_active = 1
                    """
                ).fetchone()["n"]
            )
            split_counts = {
                name: {
                    "accountCount": 0,
                    "labelCount": 0,
                    "inCount": 0,
                    "outCount": 0,
                    "abstainCount": 0,
                }
                for name in SPLIT_NAMES
            }
            for row in conn.execute(
                """
                SELECT s.split,
                       COUNT(*) AS label_count,
                       COUNT(DISTINCT ls.account_id) AS account_count,
                       SUM(CASE WHEN ls.judgment = 'in' THEN 1 ELSE 0 END) AS in_count,
                       SUM(CASE WHEN ls.judgment = 'out' THEN 1 ELSE 0 END) AS out_count,
                       SUM(CASE WHEN ls.judgment = 'abstain' THEN 1 ELSE 0 END) AS abstain_count
                FROM account_community_gold_label_set ls
                JOIN account_community_gold_split s ON s.account_id = ls.account_id
                WHERE ls.is_active = 1
                GROUP BY s.split
                """
            ).fetchall():
                split_counts[str(row["split"])] = {
                    "accountCount": int(row["account_count"]),
                    "labelCount": int(row["label_count"]),
                    "inCount": int(row["in_count"] or 0),
                    "outCount": int(row["out_count"] or 0),
                    "abstainCount": int(row["abstain_count"] or 0),
                }

            judgment_counts = {name: 0 for name in JUDGMENT_NAMES}
            for row in conn.execute(
                """
                SELECT judgment, COUNT(*) AS n
                FROM account_community_gold_label_set
                WHERE is_active = 1
                GROUP BY judgment
                """
            ).fetchall():
                judgment_counts[str(row["judgment"])] = int(row["n"])

            reviewer_counts = {
                str(row["reviewer"]): int(row["n"])
                for row in conn.execute(
                    """
                    SELECT reviewer, COUNT(*) AS n
                    FROM account_community_gold_label_set
                    WHERE is_active = 1
                    GROUP BY reviewer
                    ORDER BY n DESC, reviewer ASC
                    """
                ).fetchall()
            }
            duplicate_active_labels = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM (
                        SELECT account_id, community_id, reviewer
                        FROM account_community_gold_label_set
                        WHERE is_active = 1
                        GROUP BY account_id, community_id, reviewer
                        HAVING COUNT(*) > 1
                    )
                    """
                ).fetchone()["n"]
            )
            accounts_with_multiple_splits = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM (
                        SELECT account_id, COUNT(DISTINCT split) AS split_count
                        FROM account_community_gold_split
                        GROUP BY account_id
                        HAVING split_count > 1
                    )
                    """
                ).fetchone()["n"]
            )
            return {
                "totalActiveLabels": total_active_labels,
                "labeledAccountCount": labeled_account_count,
                "splitCounts": split_counts,
                "judgmentCounts": judgment_counts,
                "reviewerCounts": reviewer_counts,
                "leakageChecks": {
                    "duplicateActiveLabels": duplicate_active_labels,
                    "accountsWithMultipleSplits": accounts_with_multiple_splits,
                },
                "communities": self._list_communities_with_conn(conn),
            }
