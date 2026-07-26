from __future__ import annotations

from collections import Counter
from copy import deepcopy

import pytest

from src.data.community_gold.role_allocation import allocate_roles
from tests.personal_ontology_fixtures import allocation_kwargs


def test_role_allocation_is_deterministic_exclusive_and_probability_auditable() -> None:
    kwargs = allocation_kwargs()

    first = allocate_roles(**kwargs)
    second = allocate_roles(**kwargs)

    assert first == second
    assert len(first) == len(kwargs["account_ids"])
    assert len({row["accountId"] for row in first}) == len(first)
    assert {row["accountId"] for row in first} == set(kwargs["account_ids"])

    counts = Counter((row["stratum"], row["assignedRole"]) for row in first)
    for stratum, quotas in kwargs["quotas_by_stratum"].items():
        for role, quota in quotas.items():
            assert counts[(stratum, role)] == quota

    for row in first:
        assert row["assignedProbability"] > 0.0
        assert row["terminalTestProbability"] > 0.0
        assert row["assignedProbability"] == row["roleProbabilities"][row["assignedRole"]]


def test_role_allocation_rejects_zero_terminal_test_probability() -> None:
    kwargs = allocation_kwargs()
    kwargs["quotas_by_stratum"]["sparse"]["terminal_test"] = 0
    kwargs["quotas_by_stratum"]["sparse"]["frame_only"] = 5

    with pytest.raises(ValueError, match="positive terminal-test quota"):
        allocate_roles(**kwargs)


def test_role_allocation_rejects_terminal_role_readable_by_selection() -> None:
    kwargs = allocation_kwargs()
    kwargs["role_catalog"]["terminal_test"]["readPurposes"].append("selection")

    with pytest.raises(ValueError, match="terminal-test role"):
        allocate_roles(**kwargs)


def test_role_allocation_rejects_mixed_eligibility_strata() -> None:
    kwargs = allocation_kwargs()
    kwargs["strata_by_account"] = deepcopy(kwargs["strata_by_account"])
    kwargs["strata_by_account"]["acct-11"] = "rich"

    with pytest.raises(ValueError, match="mixes rich and non-rich"):
        allocate_roles(**kwargs)


def test_role_allocation_rejects_unfilled_stratum_quota() -> None:
    kwargs = allocation_kwargs()
    kwargs["quotas_by_stratum"]["rich"]["frame_only"] = 1

    with pytest.raises(ValueError, match="quota total"):
        allocate_roles(**kwargs)
