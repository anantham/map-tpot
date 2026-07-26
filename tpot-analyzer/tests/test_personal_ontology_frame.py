from __future__ import annotations

from copy import deepcopy

import pytest

from src.data.community_gold.evaluation_frame import (
    freeze_evaluation_frame,
    validate_evaluation_frame,
)
from tests.personal_ontology_fixtures import frame_kwargs


def test_frame_is_deterministic_content_addressed_and_preserves_order() -> None:
    kwargs = frame_kwargs()

    first = freeze_evaluation_frame(**kwargs)
    second = freeze_evaluation_frame(**kwargs)

    assert first == second
    assert first["schemaVersion"] == 1
    assert first["u0AccountIds"] == kwargs["u0_account_ids"]
    assert first["uEvalAccountIds"] == kwargs["u0_account_ids"][2:]
    assert first["counts"] == {"u0": 20, "uEval": 18, "uRich": 9}
    assert len(first["u0Digest"]) == 64
    assert len(first["roleAssignmentsDigest"]) == 64
    assert len(first["manifestDigest"]) == 64
    validate_evaluation_frame(first)


def test_frame_changes_identity_when_ordered_universe_changes() -> None:
    first_kwargs = frame_kwargs()
    second_kwargs = frame_kwargs()
    second_kwargs["u0_account_ids"] = list(reversed(second_kwargs["u0_account_ids"]))

    first = freeze_evaluation_frame(**first_kwargs)
    second = freeze_evaluation_frame(**second_kwargs)

    assert first["u0Digest"] != second["u0Digest"]
    assert first["manifestDigest"] != second["manifestDigest"]


def test_frame_validation_rejects_tampering() -> None:
    frame = freeze_evaluation_frame(**frame_kwargs())
    tampered = deepcopy(frame)
    tampered["evidence"]["snapshotHash"] = "d" * 64

    with pytest.raises(ValueError, match="manifestDigest"):
        validate_evaluation_frame(tampered)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda values: values["u0_account_ids"].append(values["u0_account_ids"][0]), "duplicate"),
        (lambda values: values["fixed_training_ids"].append("outside-u0"), "fixed_training_ids"),
        (lambda values: values["rich_account_ids"].append(values["fixed_training_ids"][0]), "rich_account_ids"),
        (lambda values: values.update(evidence_cutoff="2026-07-26T00:00:00"), "timezone"),
        (lambda values: values.update(graph_manifest_hash="not-a-digest"), "graph_manifest_hash"),
    ],
)
def test_frame_rejects_invalid_identity_and_subset_contracts(mutation, message: str) -> None:
    kwargs = frame_kwargs()
    mutation(kwargs)

    with pytest.raises(ValueError, match=message):
        freeze_evaluation_frame(**kwargs)
