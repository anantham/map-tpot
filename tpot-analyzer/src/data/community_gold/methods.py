"""Method-specific score generators for account-community evaluation."""
from __future__ import annotations

from typing import Any, Dict, List

from src.graph.membership_grf import compute_grf_membership

from .artifacts import SnapshotArtifacts


class CommunityGoldMethodMixin:
    def _canonical_scores(self, conn, community_id: str, account_ids: List[str]) -> Dict[str, float]:
        if not account_ids:
            return {}
        placeholders = ",".join("?" * len(account_ids))
        rows = conn.execute(
            f"""
            SELECT account_id, weight
            FROM community_account
            WHERE community_id = ? AND account_id IN ({placeholders})
            """,
            (community_id, *account_ids),
        ).fetchall()
        scores = {account_id: 0.0 for account_id in account_ids}
        for row in rows:
            scores[str(row["account_id"])] = float(row["weight"])
        return scores

    def _nmf_scores(self, conn, community: Dict[str, Any], account_ids: List[str]) -> Dict[str, Any]:
        run_id = community.get("seededFromRun")
        seeded_idx = community.get("seededFromIdx")
        if not run_id or seeded_idx is None:
            return {"available": False, "reason": "community has no seeded NMF mapping"}
        if not account_ids:
            return {"available": True, "scores": {}}
        placeholders = ",".join("?" * len(account_ids))
        rows = conn.execute(
            f"""
            SELECT account_id, weight
            FROM community_membership
            WHERE run_id = ? AND community_idx = ? AND account_id IN ({placeholders})
            """,
            (run_id, int(seeded_idx), *account_ids),
        ).fetchall()
        scores = {account_id: 0.0 for account_id in account_ids}
        for row in rows:
            scores[str(row["account_id"])] = float(row["weight"])
        return {"available": True, "scores": scores}

    def _louvain_scores(
        self,
        artifacts: SnapshotArtifacts,
        community: Dict[str, Any],
        train_split: str,
        train_binary_ids: List[str],
        account_ids: List[str],
    ) -> Dict[str, Any]:
        try:
            louvain = artifacts.load_louvain()
        except FileNotFoundError as exc:
            return {"available": False, "reason": str(exc)}

        train_positive = set(community["labels"][train_split]["in"])
        train_negative = set(community["labels"][train_split]["out"])
        if not train_positive or not train_negative:
            return {"available": False, "reason": "need positive and negative train labels for Louvain transfer"}

        cluster_counts: Dict[int, Dict[str, int]] = {}
        train_total = 0
        train_positive_count = 0
        for account_id in train_binary_ids:
            cluster = louvain.get(account_id)
            if cluster is None:
                continue
            bucket = cluster_counts.setdefault(int(cluster), {"pos": 0, "total": 0})
            if account_id in train_positive:
                bucket["pos"] += 1
                train_positive_count += 1
            bucket["total"] += 1
            train_total += 1
        if train_total == 0:
            return {"available": False, "reason": "no train labels overlap Louvain artifact"}

        global_prior = train_positive_count / train_total
        smoothing = 2.0
        scores = {}
        for account_id in account_ids:
            cluster = louvain.get(account_id)
            if cluster is None:
                scores[account_id] = global_prior
                continue
            bucket = cluster_counts.get(int(cluster))
            if not bucket:
                scores[account_id] = global_prior
                continue
            scores[account_id] = (bucket["pos"] + smoothing * global_prior) / (bucket["total"] + smoothing)
        return {"available": True, "scores": scores}

    def _train_grf_scores(self, artifacts: SnapshotArtifacts, community: Dict[str, Any], train_split: str) -> Dict[str, Any]:
        positive_ids = community["labels"][train_split]["in"]
        negative_ids = community["labels"][train_split]["out"]
        if not positive_ids or not negative_ids:
            return {"available": False, "reason": "need positive and negative train labels for GRF"}
        try:
            adjacency = artifacts.load_adjacency()
            id_to_idx = artifacts.id_to_index()
        except FileNotFoundError as exc:
            return {"available": False, "reason": str(exc)}

        pos_idx = [id_to_idx[account_id] for account_id in positive_ids if account_id in id_to_idx]
        neg_idx = [id_to_idx[account_id] for account_id in negative_ids if account_id in id_to_idx]
        if not pos_idx or not neg_idx:
            return {"available": False, "reason": "train labels do not overlap graph artifacts"}

        result = compute_grf_membership(adjacency, pos_idx, neg_idx)
        node_ids = artifacts.load_node_ids()
        scores = {str(node_ids[idx]): float(prob) for idx, prob in enumerate(result.probabilities)}
        return {
            "available": True,
            "scores": scores,
            "solver": {
                "converged": bool(result.converged),
                "cgIterations": int(result.cg_iterations),
            },
        }
