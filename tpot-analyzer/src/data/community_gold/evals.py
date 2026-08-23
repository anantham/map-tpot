"""Evaluation methods for account-community gold labels."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .artifacts import SnapshotArtifacts
from .constants import SPLIT_NAMES
from .evaluation_reporting import (
    DIAGNOSTIC_METRICS_INTERPRETATION,
    evaluate_method_result,
)
from .metrics import macro_average

EVALUATION_METHODS = ("canonical_map", "nmf_seeded", "louvain_transfer", "train_grf")
METHOD_SCORE_SEMANTICS = {
    "canonical_map": "affinity",
    "nmf_seeded": "simplex",
    "louvain_transfer": "affinity",
    "train_grf": "affinity",
}


class CommunityGoldEvaluationMixin:
    def evaluate_scoreboard(
        self,
        *,
        split: str,
        reviewer: str = "human",
        train_split: str = "train",
        methods: Optional[Iterable[str]] = None,
        community_ids: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        if split not in SPLIT_NAMES:
            raise ValueError("split must be one of: train, dev, test")
        if train_split not in SPLIT_NAMES:
            raise ValueError("train_split must be one of: train, dev, test")
        if train_split == split:
            raise ValueError("train_split and split must be different")
        if train_split != "train" or split != "dev":
            raise ValueError(
                "legacy evaluator is limited to train->dev diagnostics; "
                "sealed test access requires the versioned study evaluator"
            )

        requested_methods = list(methods or EVALUATION_METHODS)
        unknown = sorted(set(requested_methods) - set(EVALUATION_METHODS))
        if unknown:
            raise ValueError(f"unknown methods: {unknown}")

        selected_communities = [str(value) for value in (community_ids or []) if str(value).strip()]
        with self._open() as conn:
            self._assert_community_table(conn)
            label_rows = conn.execute(
                """
                SELECT ls.account_id, ls.community_id, ls.judgment, s.split,
                       c.name AS community_name, c.color AS community_color,
                       c.seeded_from_run, c.seeded_from_idx
                FROM account_community_gold_label_set ls
                JOIN account_community_gold_split s ON s.account_id = ls.account_id
                JOIN community c ON c.id = ls.community_id
                WHERE ls.is_active = 1
                  AND ls.identity_status = 'legacy_unbound'
                  AND ls.reviewer = ?
                  AND s.split IN (?, ?)
                ORDER BY c.name ASC, ls.account_id ASC
                """,
                (reviewer, train_split, split),
            ).fetchall()
            if not label_rows:
                raise ValueError(f"No active gold labels found for reviewer='{reviewer}' across splits {train_split}/{split}")

            communities: Dict[str, Dict[str, Any]] = {}
            for row in label_rows:
                community_id = str(row["community_id"])
                if selected_communities and community_id not in selected_communities:
                    continue
                entry = communities.setdefault(
                    community_id,
                    {
                        "communityId": community_id,
                        "communityName": row["community_name"],
                        "communityColor": row["community_color"],
                        "seededFromRun": row["seeded_from_run"],
                        "seededFromIdx": row["seeded_from_idx"],
                        "labels": {train_split: {"in": [], "out": [], "abstain": []}, split: {"in": [], "out": [], "abstain": []}},
                    },
                )
                entry["labels"][str(row["split"])][str(row["judgment"])].append(str(row["account_id"]))
            if not communities:
                raise ValueError("No gold labels matched the requested communities")

            artifacts = SnapshotArtifacts(self.db_path.parent)
            grf_cache: Dict[str, Dict[str, float]] = {}
            results = []
            for community in communities.values():
                per_method = {}
                train_binary_ids = community["labels"][train_split]["in"] + community["labels"][train_split]["out"]
                eval_binary_ids = community["labels"][split]["in"] + community["labels"][split]["out"]
                sample_counts = {
                    train_split: {
                        "in": len(community["labels"][train_split]["in"]),
                        "out": len(community["labels"][train_split]["out"]),
                        "abstain": len(community["labels"][train_split]["abstain"]),
                    },
                    split: {
                        "in": len(community["labels"][split]["in"]),
                        "out": len(community["labels"][split]["out"]),
                        "abstain": len(community["labels"][split]["abstain"]),
                    },
                }
                coverage_by_split = {}
                for split_name, counts in sample_counts.items():
                    labelable_count = counts["in"] + counts["out"]
                    total_reviewed = labelable_count + counts["abstain"]
                    coverage_by_split[split_name] = {
                        "totalReviewed": total_reviewed,
                        "labelableCount": labelable_count,
                        "abstainCount": counts["abstain"],
                        "labelabilityRate": (
                            labelable_count / total_reviewed
                            if total_reviewed
                            else None
                        ),
                    }
                for method in requested_methods:
                    score_result = self._score_method(
                        conn=conn,
                        artifacts=artifacts,
                        grf_cache=grf_cache,
                        method=method,
                        community=community,
                        train_split=train_split,
                        train_binary_ids=train_binary_ids,
                        eval_binary_ids=eval_binary_ids,
                    )
                    method_result = evaluate_method_result(
                        score_result=score_result,
                        community=community,
                        train_split=train_split,
                        eval_split=split,
                    )
                    method_result["scoreSemantics"] = METHOD_SCORE_SEMANTICS[method]
                    per_method[method] = method_result

                results.append(
                    {
                        "communityId": community["communityId"],
                        "communityName": community["communityName"],
                        "communityColor": community["communityColor"],
                        "sampleCounts": sample_counts,
                        "coverageBySplit": coverage_by_split,
                        "methods": per_method,
                    }
                )

        summary = {}
        for method in requested_methods:
            rows = [
                item["methods"][method]["metrics"]
                for item in results
                if item["methods"][method]["available"] and item["methods"][method].get("metrics")
            ]
            summary[method] = {
                "scoreSemantics": METHOD_SCORE_SEMANTICS[method],
                "calibrated": False,
                "probabilityMetricsAvailable": False,
                "metricsInterpretation": DIAGNOSTIC_METRICS_INTERPRETATION,
                "scoredCommunities": len(rows),
                "macroAucPr": macro_average(rows, "aucPr"),
                "macroBrier": macro_average(rows, "brier"),
                "macroEce": macro_average(rows, "ece"),
                "macroF1": macro_average(rows, "f1"),
            }

        best_method = None
        best_auc = -1.0
        for method, row in summary.items():
            auc = row.get("macroAucPr")
            if auc is not None and auc > best_auc:
                best_method = method
                best_auc = auc

        return {
            "reviewer": reviewer,
            "split": split,
            "trainSplit": train_split,
            "evaluationContract": "legacy_train_to_dev_diagnostic",
            "methods": requested_methods,
            "bestMethodByMacroAucPr": best_method,
            "summary": summary,
            "communities": results,
        }

    def _score_method(
        self,
        *,
        conn,
        artifacts: SnapshotArtifacts,
        grf_cache: Dict[str, Dict[str, float]],
        method: str,
        community: Dict[str, Any],
        train_split: str,
        train_binary_ids: List[str],
        eval_binary_ids: List[str],
    ) -> Dict[str, Any]:
        target_ids = sorted(set(train_binary_ids + eval_binary_ids))
        if method == "canonical_map":
            return {
                "available": True,
                "scores": self._canonical_scores(
                    conn,
                    community["communityId"],
                    target_ids,
                ),
                "missingScorePolicy": (
                    "canonical map absence is the explicit zero baseline"
                ),
            }
        if method == "nmf_seeded":
            return self._nmf_scores(conn, community, target_ids)
        if method == "louvain_transfer":
            return self._louvain_scores(artifacts, community, train_split, train_binary_ids, target_ids)
        if method == "train_grf":
            cached = grf_cache.get(community["communityId"])
            if cached is None:
                cached = self._train_grf_scores(artifacts, community, train_split)
                if cached.get("available"):
                    grf_cache[community["communityId"]] = cached["scores"]
            if cached.get("available"):
                return {
                    "available": True,
                    "scores": {
                        account_id: cached["scores"][account_id]
                        for account_id in target_ids
                        if account_id in cached["scores"]
                    },
                    "missingScorePolicy": "unknown_excluded",
                }
            return cached
        raise ValueError(f"Unsupported method '{method}'")
