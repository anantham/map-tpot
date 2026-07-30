"""Validation and arithmetic contracts for named-seed coverage."""
from __future__ import annotations

import hashlib
from typing import Any


class SeedCoverageInputError(ValueError):
    """Raised when a coverage input cannot support the declared contract."""


def validate_seed_panel(panel: dict[str, Any]) -> list[dict[str, Any]]:
    if (
        panel.get("schema_version") != 1
        or not isinstance(panel.get("panel_id"), str)
        or type(panel.get("panel_version")) is not int
        or not isinstance(panel.get("seeds"), list)
        or not panel["seeds"]
    ):
        raise SeedCoverageInputError("seed panel is missing its versioned identity")
    ids: set[str] = set()
    handles: set[str] = set()
    for seed in panel["seeds"]:
        if not isinstance(seed, dict):
            raise SeedCoverageInputError("each seed must be an object")
        account_id = seed.get("account_id")
        handle = seed.get("handle_at_freeze")
        claim = seed.get("claimed_following")
        normalized = str(handle or "").lower().lstrip("@")
        if (
            not isinstance(account_id, str)
            or not account_id.isdigit()
            or not normalized
            or (claim is not None and (type(claim) is not int or claim < 0))
        ):
            raise SeedCoverageInputError(f"invalid pinned seed row: {seed}")
        if account_id in ids or normalized in handles:
            raise SeedCoverageInputError("seed account IDs and handles must be unique")
        ids.add(account_id)
        handles.add(normalized)
    return panel["seeds"]


def estimate_full_followings_refresh(
    claimed_following: int,
    price_card: dict[str, Any],
) -> dict[str, int | float]:
    """Estimate complete traversal, never a claimed-minus-observed shortcut."""
    if (
        type(claimed_following) is not int
        or claimed_following < 0
        or price_card.get("schema_version") != 1
    ):
        raise SeedCoverageInputError(
            "claimed_following must be a nonnegative integer and price schema must be 1"
        )
    endpoint = price_card.get("user_followings")
    credits_per_usd = price_card.get("credits_per_usd")
    if (
        not isinstance(endpoint, dict)
        or type(credits_per_usd) is not int
        or credits_per_usd <= 0
    ):
        raise SeedCoverageInputError(
            "price card requires user_followings and positive credits_per_usd"
        )
    page_size = endpoint.get("maximum_page_size")
    minimum = endpoint.get("minimum_call_credits")
    tiers = endpoint.get("tiers")
    if (
        type(page_size) is not int
        or page_size <= 0
        or type(minimum) is not int
        or minimum < 0
        or not isinstance(tiers, list)
    ):
        raise SeedCoverageInputError("followings price tiers are incomplete")

    def page_credits(returned: int) -> int:
        for tier in tiers:
            if (
                isinstance(tier, dict)
                and type(tier.get("returned_min")) is int
                and type(tier.get("returned_max")) is int
                and type(tier.get("credits_per_item")) is int
                and tier["returned_min"] <= returned <= tier["returned_max"]
            ):
                return max(minimum, returned * tier["credits_per_item"])
        valid_tiers = [tier for tier in tiers if isinstance(tier, dict)]
        if valid_tiers and returned < min(tier["returned_min"] for tier in valid_tiers):
            return minimum
        raise SeedCoverageInputError(
            f"price card has no tier for a page returning {returned} items"
        )

    page_counts = []
    remaining = claimed_following
    while remaining > 0:
        returned = min(page_size, remaining)
        page_counts.append(returned)
        remaining -= returned
    if not page_counts:
        page_counts.append(0)
    credits = sum(page_credits(returned) for returned in page_counts)
    return {
        "estimated_calls": len(page_counts),
        "estimated_credits": credits,
        "estimated_usd": round(credits / credits_per_usd, 10),
    }


def target_set_digest(values: set[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def compare_seed_coverage_reports(
    selected: dict[str, Any],
    comparison: dict[str, Any],
) -> dict[str, Any]:
    selected_seeds = {row["account_id"]: row for row in selected["seeds"]}
    comparison_seeds = {row["account_id"]: row for row in comparison["seeds"]}
    if selected_seeds.keys() != comparison_seeds.keys():
        raise SeedCoverageInputError(
            "coverage comparison requires identical pinned seed account IDs"
        )
    rows = []
    for account_id, seed in selected_seeds.items():
        selected_union = seed["follows"]["stored_key_union"]
        comparison_union = comparison_seeds[account_id]["follows"][
            "stored_key_union"
        ]
        rows.append(
            {
                "account_id": account_id,
                "handle_at_freeze": seed["handle_at_freeze"],
                "selected_distinct_targets": selected_union["distinct_targets"],
                "comparison_distinct_targets": comparison_union[
                    "distinct_targets"
                ],
                "delta": (
                    selected_union["distinct_targets"]
                    - comparison_union["distinct_targets"]
                ),
                "selected_target_set_sha256": selected_union[
                    "target_set_sha256"
                ],
                "comparison_target_set_sha256": comparison_union[
                    "target_set_sha256"
                ],
                "same_target_digest": (
                    selected_union["target_set_sha256"]
                    == comparison_union["target_set_sha256"]
                ),
            }
        )
    selected_receipt = selected["inputs"]["archive_db"]
    comparison_receipt = comparison["inputs"]["archive_db"]
    return {
        "selected_archive_db": selected_receipt,
        "comparison_archive_db": comparison_receipt,
        "same_inode": selected_receipt["inode"] == comparison_receipt["inode"],
        "seed_deltas": rows,
        "selected_candidate_count": selected["ranking"]["candidate_count"],
        "comparison_candidate_count": comparison["ranking"]["candidate_count"],
    }


def hypothesis_results(seed_rows: list[dict[str, Any]], candidates: Any) -> dict:
    acquisition_attributed = all(
        row["follows"]["source_attribution"].get(
            "merged_sqlite_attributed",
            False,
        )
        for row in seed_rows
    )
    acquisition_result: dict[str, Any] = {
        "falsified": not acquisition_attributed
    }
    if not acquisition_attributed:
        acquisition_result["reason"] = (
            "current follow tables have no source, fetched_at, or run ID"
        )
    return {
        "H-C1_pinned_identity_uncontested": {
            "falsified": any(
                row["identity"]["status"] == "conflicting" for row in seed_rows
            )
        },
        "H-C2_outgoing_neighborhood_observed": {
            "falsified": any(
                row["follows"]["stored_key_union"]["distinct_targets"] == 0
                for row in seed_rows
            )
        },
        "H-C3_follow_acquisition_attributed": acquisition_result,
        "H-C4_source_selectivity_operational": {
            "falsified": not bool(candidates),
            "quality_tested": False,
        },
    }
