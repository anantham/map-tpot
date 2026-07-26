"""Synthetic inputs shared by personal-ontology integrity tests."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


def role_inputs() -> Dict[str, Any]:
    u0 = [f"acct-{index:02d}" for index in range(20)]
    u_eval = u0[2:]
    rich = u_eval[:9]
    strata = {
        account_id: ("rich" if account_id in rich else "sparse")
        for account_id in u_eval
    }
    catalog = {
        "model_development": {
            "readPurposes": ["training", "selection"],
            "requiresRich": False,
        },
        "policy_development": {
            "readPurposes": ["selection"],
            "requiresRich": True,
        },
        "policy_evaluation": {
            "readPurposes": [],
            "requiresRich": True,
        },
        "terminal_test": {
            "readPurposes": ["terminal_evaluation"],
            "requiresRich": False,
        },
        "frame_only": {
            "readPurposes": [],
            "requiresRich": False,
        },
    }
    quotas = {
        "rich": {
            "model_development": 2,
            "policy_development": 2,
            "policy_evaluation": 2,
            "terminal_test": 1,
            "frame_only": 2,
        },
        "sparse": {
            "model_development": 4,
            "policy_development": 0,
            "policy_evaluation": 0,
            "terminal_test": 2,
            "frame_only": 3,
        },
    }
    return {
        "u0": u0,
        "u_eval": u_eval,
        "rich": rich,
        "strata": strata,
        "catalog": catalog,
        "quotas": quotas,
    }


def allocation_kwargs() -> Dict[str, Any]:
    fixture = role_inputs()
    return {
        "account_ids": fixture["u_eval"],
        "strata_by_account": fixture["strata"],
        "rich_account_ids": fixture["rich"],
        "role_catalog": deepcopy(fixture["catalog"]),
        "quotas_by_stratum": deepcopy(fixture["quotas"]),
        "terminal_test_roles": ["terminal_test"],
        "seed": "slice-1-synthetic-seed",
        "role_registry_id": "synthetic-role-registry-v1",
    }


def frame_kwargs() -> Dict[str, Any]:
    fixture = role_inputs()
    return {
        "frame_id": "synthetic-frame-v1",
        "scope": {
            "userId": "user-aditya",
            "ontologyId": "personal-subcultures",
            "ontologyVersion": 1,
            "taskId": "affiliation",
        },
        "u0_account_ids": fixture["u0"],
        "fixed_training_ids": [fixture["u0"][0]],
        "fixed_challenge_ids": [fixture["u0"][1]],
        "rich_account_ids": fixture["rich"],
        "strata_by_account": fixture["strata"],
        "role_catalog": deepcopy(fixture["catalog"]),
        "quotas_by_stratum": deepcopy(fixture["quotas"]),
        "terminal_test_roles": ["terminal_test"],
        "role_registry_id": "synthetic-role-registry-v1",
        "seed": "slice-1-synthetic-seed",
        "evidence_snapshot_id": "snapshot-synthetic-v1",
        "evidence_snapshot_hash": "a" * 64,
        "graph_manifest_hash": "b" * 64,
        "identity_resolution_digest": "c" * 64,
        "evidence_cutoff": "2026-07-26T00:00:00+00:00",
        "candidate_rules": {"source": "synthetic", "deduplicate": True},
        "ood_rules": {"statistic": "distance", "threshold": 0.8},
    }
