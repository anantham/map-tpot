#!/usr/bin/env python3
"""Human-readable synthetic check for source-side selectivity."""

from __future__ import annotations

import math
import sys
from pathlib import Path

if not __package__:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from src.graph.source_selectivity import rank_follow_candidates


def verify() -> int:
    edges = [
        ("selective", "niche"),
        ("selective", "shared"),
        ("selective", "shared"),
        ("broad", "popular"),
        ("broad", "shared"),
    ]
    result = rank_follow_candidates(
        ["selective", "broad", "unknown"],
        edges,
        {"selective": 1, "broad": 100},
    )
    candidates = {row.account_id: row for row in result.candidates}
    seeds = {row.seed_id: row for row in result.seed_diagnostics}
    checks = [
        (
            "effective degree uses max(claimed, observed)",
            seeds["selective"].effective_degree == 2
            and seeds["broad"].effective_degree == 100,
        ),
        (
            "duplicate edges do not inflate distinct support",
            candidates["shared"].raw_support == 2
            and candidates["shared"].supporting_seeds == ("broad", "selective"),
        ),
        (
            "selective evidence contributes more",
            math.isclose(candidates["niche"].selectivity_score, 0.5)
            and candidates["niche"].selectivity_score
            > candidates["popular"].selectivity_score,
        ),
        ("missing seed degree remains visible", seeds["unknown"].degree_unknown),
    ]
    for label, passed in checks:
        print(f"{'✓' if passed else '✗'} {label}")

    print(
        f"Metrics: input_edges={len(edges)}, candidates={len(result.candidates)}, "
        "degree_unknown_seeds="
        f"{sum(row.degree_unknown for row in result.seed_diagnostics)}"
    )
    for row in result.candidates:
        print(f"  {row.account_id}: score={row.selectivity_score:.6f}, "
              f"support={row.raw_support}")
    print("Boundary: synthetic arithmetic only; score is not calibrated membership.")
    if all(passed for _, passed in checks):
        print("Next: compare held-out Recall@K with raw-support ranking.")
        return 0
    print("Next: inspect the failed invariant before ranking real edges.")
    return 1

if __name__ == "__main__":  # pragma: no branch - CLI entrypoint
    raise SystemExit(verify())
