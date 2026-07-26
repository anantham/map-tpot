"""Candidate queue helpers for account-community gold review."""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from .artifacts import SnapshotArtifacts
from .candidate_scoring import summarize_queue_scores
from .constants import SPLIT_NAMES
from .schema import split_for_account

class CommunityGoldCandidateMixin:
    def list_review_candidates(
        self,
        *,
        reviewer: str = "human",
        limit: int = 20,
        split: Optional[str] = None,
        community_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if split not in {None, *SPLIT_NAMES}:
            raise ValueError("split must be one of: train, dev, test")

        with self._open() as conn:
            self._assert_community_table(conn)
            communities = self._load_candidate_communities(conn, community_id=community_id, reviewer=reviewer)
            artifacts = SnapshotArtifacts(self.db_path.parent)
            ranked_by_community = []
            for community in communities:
                ranked = self._rank_candidates_for_community(
                    conn=conn,
                    artifacts=artifacts,
                    community=community,
                    reviewer=reviewer,
                    split=split,
                    limit=limit if community_id else max(limit, 8),
                )
                if ranked:
                    ranked_by_community.append((community, ranked))

        if community_id:
            return ranked_by_community[0][1][:limit] if ranked_by_community else []
        return self._round_robin_candidates(ranked_by_community, limit)

    def _load_candidate_communities(
        self,
        conn: sqlite3.Connection,
        *,
        community_id: Optional[str],
        reviewer: str,
    ) -> List[Dict[str, Any]]:
        conditions = []
        params: List[Any] = [reviewer]
        if community_id is not None:
            conditions.append("c.id = ?")
            params.append(community_id)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"""
            SELECT c.id, c.name, c.color, c.seeded_from_run, c.seeded_from_idx,
                   COALESCE(gl.gold_label_count, 0) AS gold_label_count
            FROM community c
            LEFT JOIN (
                SELECT community_id, COUNT(*) AS gold_label_count
                FROM account_community_gold_label_set
                WHERE is_active = 1 AND reviewer = ?
                GROUP BY community_id
            ) gl ON gl.community_id = c.id
            {where_clause}
            ORDER BY gold_label_count ASC, c.name ASC
            """,
            tuple(params),
        ).fetchall()
        return [
            {
                "communityId": str(row["id"]),
                "communityName": row["name"],
                "communityColor": row["color"],
                "seededFromRun": row["seeded_from_run"],
                "seededFromIdx": row["seeded_from_idx"],
                "goldLabelCount": int(row["gold_label_count"]),
            }
            for row in rows
        ]

    def _rank_candidates_for_community(
        self,
        *,
        conn: sqlite3.Connection,
        artifacts: SnapshotArtifacts,
        community: Dict[str, Any],
        reviewer: str,
        split: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        candidate_map, active_ids, train_positive, train_negative = self._candidate_pool(
            conn=conn,
            artifacts=artifacts,
            community=community,
            reviewer=reviewer,
            split=split,
        )
        if not candidate_map:
            return []

        candidate_ids = sorted(candidate_map.keys())
        community_payload = {
            "communityId": community["communityId"],
            "seededFromRun": community["seededFromRun"],
            "seededFromIdx": community["seededFromIdx"],
            "labels": {"train": {"in": train_positive, "out": train_negative, "abstain": []}},
        }
        warm_ready = bool(train_positive and train_negative)
        louvain = self._louvain_scores(artifacts, community_payload, "train", train_positive + train_negative, candidate_ids) if warm_ready else {"available": False}
        grf = self._train_grf_scores(artifacts, community_payload, "train") if warm_ready else {"available": False}
        canonical = self._canonical_scores(conn, community["communityId"], candidate_ids)
        nmf = self._nmf_scores(conn, community, candidate_ids)

        warm_available = warm_ready and (louvain.get("available") or grf.get("available"))
        ranked: List[Dict[str, Any]] = []
        grf_scores = grf.get("scores", {}) if grf.get("available") else {}
        louvain_scores = louvain.get("scores", {}) if louvain.get("available") else {}
        nmf_scores = nmf.get("scores", {}) if nmf.get("available") else {}
        for account_id in candidate_ids:
            if account_id in active_ids:
                continue
            row = candidate_map[account_id]
            split_name = split_for_account(account_id)
            if split is not None and split_name != split:
                continue

            method_scores = {
                "canonical_map": float(canonical.get(account_id, 0.0)),
                "nmf_seeded": float(nmf_scores.get(account_id, 0.0)),
            }
            if louvain.get("available"):
                method_scores["louvain_transfer"] = float(louvain_scores.get(account_id, 0.0))
            if grf.get("available"):
                method_scores["train_grf"] = float(grf_scores.get(account_id, 0.0))

            if warm_available:
                summary = summarize_queue_scores(method_scores)
                mean_score = summary["meanScore"]
                uncertainty = summary["uncertainty"]
                disagreement = summary["disagreement"]
                queue_score = summary["queueScore"]
                reason = "high disagreement across methods" if disagreement >= 0.25 else "boundary candidate"
                selection_mode = "warm"
            else:
                queue_score = max(method_scores["canonical_map"], method_scores["nmf_seeded"])
                if queue_score <= 0.0:
                    continue
                uncertainty = None
                disagreement = None
                mean_score = queue_score
                reason = "canonical seed candidate" if method_scores["canonical_map"] >= method_scores["nmf_seeded"] else "nmf seed candidate"
                selection_mode = "cold"

            ranked.append(
                {
                    "accountId": account_id,
                    "username": row.get("username"),
                    "displayName": row.get("displayName"),
                    "communityId": community["communityId"],
                    "communityName": community["communityName"],
                    "communityColor": community["communityColor"],
                    "split": split_name,
                    "selectionMode": selection_mode,
                    "reason": reason,
                    "queueScore": queue_score,
                    "meanScore": mean_score,
                    "uncertainty": uncertainty,
                    "disagreement": disagreement,
                    "inGraph": bool(row.get("inGraph")),
                    "methodScores": method_scores,
                }
            )

        ranked.sort(key=lambda row: (0 if row["inGraph"] else 1, -row["queueScore"], row["accountId"]))
        return ranked[: max(limit * 2, limit)]

    def _round_robin_candidates(
        self,
        ranked_by_community: List[tuple[Dict[str, Any], List[Dict[str, Any]]]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        ordered = [
            (community, list(rows))
            for community, rows in ranked_by_community
            if rows
        ]
        result: List[Dict[str, Any]] = []
        while ordered and len(result) < limit:
            next_round = []
            for community, rows in ordered:
                if not rows:
                    continue
                candidate = rows.pop(0)
                candidate["communityGoldLabelCount"] = community["goldLabelCount"]
                result.append(candidate)
                if len(result) >= limit:
                    break
                if rows:
                    next_round.append((community, rows))
            ordered = next_round
        return result
