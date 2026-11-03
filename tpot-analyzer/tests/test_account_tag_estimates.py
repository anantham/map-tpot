from __future__ import annotations

import math

import pytest

from src.data.account_tag_estimates import AccountTagEstimateStore


@pytest.mark.integration
def test_estimate_store_appends_a_review_trajectory(tmp_path) -> None:
    """Test intent.

    - Keep every deliberate review instead of overwriting the latest estimate.
    - Derive the current estimate from the final event in chronological order.
    - Preserve review-session identity for later convergence analysis.
    """
    store = AccountTagEstimateStore(tmp_path / "account_tags.db")

    first = store.append_estimate(
        ego="Aditya",
        account_id="123",
        tag="Dharma",
        point_estimate=0.60,
        plausible_low=0.35,
        plausible_high=0.80,
        review_session_id="review-one",
        source="human_curator_api",
    )
    second = store.append_estimate(
        ego="aditya",
        account_id="123",
        tag="dharma",
        point_estimate=0.75,
        plausible_low=0.60,
        plausible_high=0.88,
        review_session_id="review-two",
        source="human_curator_api",
    )

    current, history = store.get_estimates(
        ego="ADITYA",
        account_id="123",
        tag="DHARMA",
    )
    assert current == second
    assert [row.event_id for row in history] == [first.event_id, second.event_id]
    assert [row.review_session_id for row in history] == [
        "review-one",
        "review-two",
    ]
    assert history[0].evidence_binding_status == "unbound"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("point", "low", "high", "session", "message"),
    [
        (0.5, 0.6, 0.8, "review", "low <= point <= high"),
        (0.5, 0.2, 0.4, "review", "low <= point <= high"),
        (-0.1, 0.0, 0.4, "review", "between 0 and 1"),
        (math.inf, 0.0, 1.0, "review", "finite"),
        (0.5, 0.2, 0.8, " ", "review_session_id cannot be empty"),
    ],
)
def test_estimate_store_rejects_invalid_ranges(
    tmp_path, point, low, high, session, message
) -> None:
    """Test intent.

    - Reject values that cannot represent a bounded subjective trajectory.
    - Return descriptive errors instead of allowing corrupt samples.
    """
    store = AccountTagEstimateStore(tmp_path / "account_tags.db")

    with pytest.raises(ValueError, match=message):
        store.append_estimate(
            ego="aditya",
            account_id="123",
            tag="Dharma",
            point_estimate=point,
            plausible_low=low,
            plausible_high=high,
            review_session_id=session,
            source="human_curator_api",
        )


@pytest.mark.integration
def test_estimate_store_isolates_curator_account_and_tag(tmp_path) -> None:
    """Test intent.

    - Scope trajectory reads to the exact curator, account, and tag.
    - Keep an unknown subject empty rather than borrowing a nearby estimate.
    """
    store = AccountTagEstimateStore(tmp_path / "account_tags.db")
    for ego, account_id, tag in [
        ("aditya", "123", "Dharma"),
        ("other", "123", "Dharma"),
        ("aditya", "456", "Dharma"),
        ("aditya", "123", "AI"),
    ]:
        store.append_estimate(
            ego=ego,
            account_id=account_id,
            tag=tag,
            point_estimate=0.5,
            plausible_low=0.25,
            plausible_high=0.75,
            review_session_id=f"{ego}-{account_id}-{tag}",
            source="verification_script",
        )

    _, history = store.get_estimates(
        ego="aditya", account_id="123", tag="Dharma"
    )
    assert len(history) == 1
    current, missing = store.get_estimates(
        ego="aditya", account_id="missing", tag="Dharma"
    )
    assert current is None
    assert missing == []
