from __future__ import annotations

from src.evaluation.seed_coverage_contract import (
    compare_seed_coverage_reports,
    estimate_full_followings_refresh,
    hypothesis_results,
)


def _price_card() -> dict:
    return {
        "schema_version": 1,
        "card_id": "test-card",
        "credits_per_usd": 100_000,
        "user_followings": {
            "maximum_page_size": 200,
            "minimum_call_credits": 60,
            "tiers": [
                {"returned_min": 20, "returned_max": 99, "credits_per_item": 3},
                {"returned_min": 100, "returned_max": 199, "credits_per_item": 2},
                {"returned_min": 200, "returned_max": 200, "credits_per_item": 1},
            ],
        },
    }


def _report(*, path: str, inode: int, count: int, digest: str) -> dict:
    return {
        "inputs": {"archive_db": {"path": path, "inode": inode}},
        "seeds": [
            {
                "account_id": "1",
                "handle_at_freeze": "Alpha",
                "follows": {
                    "stored_key_union": {
                        "distinct_targets": count,
                        "target_set_sha256": digest,
                    }
                },
            }
        ],
        "ranking": {"candidate_count": count},
    }


def test_full_refresh_cost_uses_page_tiers_not_observed_gap() -> None:
    estimate = estimate_full_followings_refresh(2167, _price_card())

    assert estimate == {
        "estimated_calls": 11,
        "estimated_credits": 2334,
        "estimated_usd": 0.02334,
    }
    assert estimate_full_followings_refresh(59, _price_card())[
        "estimated_credits"
    ] == 177
    assert estimate_full_followings_refresh(0, _price_card())[
        "estimated_credits"
    ] == 60


def test_comparison_preserves_database_receipts_and_target_digests() -> None:
    selected = _report(path="/selected.db", inode=1, count=5, digest="selected")
    comparison = _report(
        path="/comparison.db",
        inode=2,
        count=3,
        digest="comparison",
    )

    result = compare_seed_coverage_reports(selected, comparison)

    assert result["selected_archive_db"] == selected["inputs"]["archive_db"]
    assert result["comparison_archive_db"] == comparison["inputs"]["archive_db"]
    assert result["seed_deltas"] == [
        {
            "account_id": "1",
            "handle_at_freeze": "Alpha",
            "selected_distinct_targets": 5,
            "comparison_distinct_targets": 3,
            "delta": 2,
            "selected_target_set_sha256": "selected",
            "comparison_target_set_sha256": "comparison",
            "same_target_digest": False,
        }
    ]


def test_acquisition_attribution_hypothesis_is_derived_from_rows() -> None:
    row = {
        "identity": {"status": "pinned"},
        "follows": {
            "stored_key_union": {"distinct_targets": 1},
            "source_attribution": {"merged_sqlite_attributed": True},
        },
    }

    result = hypothesis_results([row], candidates=["candidate"])

    assert result["H-C3_follow_acquisition_attributed"] == {"falsified": False}
