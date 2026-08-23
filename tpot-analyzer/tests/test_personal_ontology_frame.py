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
    assert first["randomizationAudit"] == {
        "status": "caller_seed_unverified",
        "designInferenceEligible": False,
        "probabilitySemantics": (
            "nominal_quota_fraction_conditional_on_uniform_precommitted_seed"
        ),
    }
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


def test_frame_canonicalizes_role_registry_whitespace_once() -> None:
    kwargs = frame_kwargs()
    catalog = kwargs["role_catalog"]
    quotas = kwargs["quotas_by_stratum"]
    catalog[" terminal_test "] = catalog.pop("terminal_test")
    catalog[" terminal_test "]["readPurposes"] = [
        " terminal_evaluation "
    ]
    for role_quotas in quotas.values():
        role_quotas[" terminal_test "] = role_quotas.pop("terminal_test")
    kwargs["terminal_test_roles"] = [" terminal_test "]

    frame = freeze_evaluation_frame(**kwargs)

    assert "terminal_test" in frame["roleRegistry"]["catalog"]
    assert " terminal_test " not in frame["roleRegistry"]["catalog"]
    assert frame["roleRegistry"]["terminalTestRoles"] == ["terminal_test"]
    assert {
        row["assignedRole"] for row in frame["roleAssignments"]
    } <= set(frame["roleRegistry"]["catalog"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_rules", []),
        ("candidate_rules", {}),
        ("ood_rules", []),
        ("ood_rules", {}),
    ],
)
def test_frame_rejects_empty_or_untyped_rule_manifests(
    field: str,
    value,
) -> None:
    kwargs = frame_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match="non-empty object"):
        freeze_evaluation_frame(**kwargs)
