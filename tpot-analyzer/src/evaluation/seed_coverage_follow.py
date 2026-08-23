"""Follow-view composition for named-seed coverage."""
from __future__ import annotations

import sqlite3
from typing import Any

from src.evaluation.seed_coverage_contract import (
    estimate_full_followings_refresh,
    target_set_digest,
)
from src.evaluation.seed_coverage_io import identity_conflicts, relation_view


def build_seed_follow_rows(
    archive: sqlite3.Connection,
    cache: sqlite3.Connection,
    seeds: list[dict[str, Any]],
    price_card: dict[str, Any],
    content: dict[str, dict[str, Any]],
    seed_aliases: dict[str, str],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    output, ranking_edges = [], []
    for seed in seeds:
        account_id = seed["account_id"]
        handle = seed["handle_at_freeze"]
        shadow_ids = {account_id, f"shadow:{handle.lower().lstrip('@')}"}
        direct, direct_targets = relation_view(
            archive,
            table="account_following",
            source_column="account_id",
            target_column="following_account_id",
            source_ids=[account_id],
            timestamp_status="not_recorded",
        )
        inverse, inverse_targets = relation_view(
            archive,
            table="account_followers",
            source_column="follower_account_id",
            target_column="account_id",
            source_ids=[account_id],
            timestamp_status="not_recorded",
        )
        shadow_direct, shadow_direct_targets = relation_view(
            cache,
            table="shadow_edge",
            source_column="source_id",
            target_column="target_id",
            source_ids=shadow_ids,
            direction="outbound",
            timestamp_status="captured_at",
        )
        shadow_inverse, shadow_inverse_targets = relation_view(
            cache,
            table="shadow_edge",
            source_column="source_id",
            target_column="target_id",
            source_ids=shadow_ids,
            direction="inbound",
            timestamp_status="captured_at",
        )
        views = (direct, inverse, shadow_direct, shadow_inverse)
        targets = (
            direct_targets
            | inverse_targets
            | shadow_direct_targets
            | shadow_inverse_targets
        )
        for target in targets:
            ranking_edges.append((account_id, seed_aliases.get(target, target)))
        claim = seed.get("claimed_following")
        union = {
            "status": (
                "partial"
                if any(view["status"] == "unavailable" for view in views)
                else "observed"
            ),
            "distinct_targets": len(targets),
            "target_set_sha256": target_set_digest(targets),
            "identity_semantics": "stored keys; unresolved aliases may duplicate people",
        }
        row = {
            **seed,
            "identity": identity_conflicts(archive, cache, account_id, handle),
            "follows": {
                "merged_sqlite_direct": direct,
                "merged_sqlite_inverse": inverse,
                "shadow_direct_following": shadow_direct,
                "shadow_inverse_following": shadow_inverse,
                "stored_key_union": union,
                "full_refresh_estimate": (
                    estimate_full_followings_refresh(claim, price_card)
                    if claim is not None
                    else None
                ),
                "source_attribution": {
                    "merged_sqlite": (
                        "unknown_or_mixed_ingestion_sources; current tables "
                        "lack source, fetched_at, and run_id"
                    ),
                    "merged_sqlite_attributed": False,
                    "shadow": "source_channel and fetched_at retained per view",
                    "union": "mixed sources; not attribution-clean",
                },
            },
            "content": content[account_id],
        }
        output.append(row)
    return output, ranking_edges
