"""Deterministic role allocation for frozen personal-ontology frames."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Dict, Mapping, Sequence

READ_PURPOSES = frozenset({"training", "selection", "terminal_evaluation"})


def _require_unique_ids(values: Sequence[str], *, field: str) -> list[str]:
    parsed = [str(value).strip() for value in values]
    if any(not value for value in parsed):
        raise ValueError(f"{field} must contain non-empty account IDs")
    if len(parsed) != len(set(parsed)):
        raise ValueError(f"{field} contains duplicate account IDs")
    return parsed


def normalize_role_catalog(
    role_catalog: Mapping[str, Mapping[str, Any]],
    terminal_test_roles: Sequence[str],
) -> tuple[Dict[str, Dict[str, Any]], list[str]]:
    if not role_catalog:
        raise ValueError("role_catalog must define at least one role")

    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_role, raw_contract in role_catalog.items():
        role = str(raw_role).strip()
        if not role:
            raise ValueError("role_catalog contains an empty role name")
        if role in normalized:
            raise ValueError(
                f"role_catalog duplicates normalized role '{role}'"
            )
        if not isinstance(raw_contract, Mapping):
            raise ValueError(f"role_catalog['{role}'] must be an object")
        raw_purposes = raw_contract.get("readPurposes", [])
        if not isinstance(raw_purposes, Sequence) or isinstance(raw_purposes, str):
            raise ValueError(f"role_catalog['{role}'].readPurposes must be a list")
        purposes = sorted({str(value).strip() for value in raw_purposes})
        if any(not purpose for purpose in purposes):
            raise ValueError(
                f"role_catalog['{role}'].readPurposes contains an empty value"
            )
        unknown = sorted(set(purposes) - READ_PURPOSES)
        if unknown:
            raise ValueError(
                f"role_catalog['{role}'] has unknown read purposes: {unknown}"
            )
        normalized[role] = {
            "readPurposes": purposes,
            "requiresRich": bool(raw_contract.get("requiresRich", False)),
        }
    if "frame_only" not in normalized:
        raise ValueError("role_catalog must define an explicit frame_only role")

    terminal_roles = sorted({str(value).strip() for value in terminal_test_roles})
    if not terminal_roles or any(not value for value in terminal_roles):
        raise ValueError("terminal_test_roles must contain at least one role")
    unknown_terminal = sorted(set(terminal_roles) - set(normalized))
    if unknown_terminal:
        raise ValueError(
            f"terminal_test_roles reference unknown roles: {unknown_terminal}"
        )
    for role, contract in normalized.items():
        purposes = set(contract["readPurposes"])
        if role in terminal_roles:
            if "terminal_evaluation" not in purposes:
                raise ValueError(
                    f"terminal-test role '{role}' must allow terminal_evaluation"
                )
            forbidden = purposes & {"training", "selection"}
            if forbidden:
                raise ValueError(
                    f"terminal-test role '{role}' cannot be readable for "
                    f"training or selection: {sorted(forbidden)}"
                )
        elif "terminal_evaluation" in purposes:
            raise ValueError(
                f"non-terminal role '{role}' cannot allow terminal_evaluation"
            )
    return dict(sorted(normalized.items())), terminal_roles


def normalize_quotas_by_stratum(
    quotas_by_stratum: Mapping[str, Mapping[str, int]],
) -> Dict[str, Dict[str, int]]:
    normalized: Dict[str, Dict[str, int]] = {}
    for raw_stratum, raw_quotas in quotas_by_stratum.items():
        stratum = str(raw_stratum).strip()
        if not stratum:
            raise ValueError("quotas_by_stratum contains an empty stratum")
        if stratum in normalized:
            raise ValueError(
                f"quotas_by_stratum duplicates normalized stratum '{stratum}'"
            )
        if not isinstance(raw_quotas, Mapping):
            raise ValueError(
                f"quotas_by_stratum['{stratum}'] must be an object"
            )
        role_quotas: Dict[str, int] = {}
        for raw_role, quota in raw_quotas.items():
            role = str(raw_role).strip()
            if not role:
                raise ValueError(
                    f"quotas_by_stratum['{stratum}'] contains an empty role"
                )
            if role in role_quotas:
                raise ValueError(
                    f"quotas for stratum '{stratum}' duplicate role '{role}'"
                )
            role_quotas[role] = quota
        normalized[stratum] = dict(sorted(role_quotas.items()))
    return dict(sorted(normalized.items()))


def normalize_strata_by_account(
    strata_by_account: Mapping[str, str],
) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for raw_account, raw_stratum in strata_by_account.items():
        account = str(raw_account).strip()
        stratum = str(raw_stratum).strip()
        if not account:
            raise ValueError("strata_by_account contains an empty account ID")
        if not stratum:
            raise ValueError(
                f"strata_by_account['{account}'] is empty"
            )
        if account in normalized:
            raise ValueError(
                f"strata_by_account duplicates normalized account '{account}'"
            )
        normalized[account] = stratum
    return normalized


def _allocation_key(
    *,
    account_id: str,
    stratum: str,
    seed: str,
    role_registry_id: str,
) -> str:
    encoded = "\x1f".join(
        (role_registry_id, seed, stratum, account_id)
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def allocate_roles(
    account_ids: Sequence[str],
    *,
    strata_by_account: Mapping[str, str],
    rich_account_ids: Sequence[str],
    role_catalog: Mapping[str, Mapping[str, Any]],
    quotas_by_stratum: Mapping[str, Mapping[str, int]],
    terminal_test_roles: Sequence[str],
    seed: str,
    role_registry_id: str,
) -> list[Dict[str, Any]]:
    """Allocate one role per account from a frozen role registry."""

    accounts = _require_unique_ids(account_ids, field="account_ids")
    if not accounts:
        raise ValueError("account_ids must not be empty")
    registry_id = str(role_registry_id).strip()
    parsed_seed = str(seed).strip()
    if not registry_id:
        raise ValueError("role_registry_id is required")
    if not parsed_seed:
        raise ValueError("seed is required")

    catalog, terminal_roles = normalize_role_catalog(
        role_catalog,
        terminal_test_roles,
    )
    normalized_quotas = normalize_quotas_by_stratum(quotas_by_stratum)
    normalized_strata = normalize_strata_by_account(strata_by_account)
    account_set = set(accounts)
    rich_set = set(_require_unique_ids(rich_account_ids, field="rich_account_ids"))
    if not rich_set <= account_set:
        outside = sorted(rich_set - account_set)
        raise ValueError(f"rich_account_ids must be inside account_ids: {outside}")

    stratum_keys = set(normalized_strata)
    missing_strata = sorted(account_set - stratum_keys)
    extra_strata = sorted(stratum_keys - account_set)
    if missing_strata or extra_strata:
        raise ValueError(
            "strata_by_account keys must exactly match account_ids; "
            f"missing={missing_strata}, extra={extra_strata}"
        )

    grouped: Dict[str, list[str]] = defaultdict(list)
    for account_id in accounts:
        stratum = normalized_strata[account_id]
        grouped[stratum].append(account_id)
    if set(normalized_quotas) != set(grouped):
        raise ValueError(
            "quotas_by_stratum keys must exactly match observed strata; "
            f"observed={sorted(grouped)}, configured={sorted(normalized_quotas)}"
        )

    assignments: Dict[str, Dict[str, Any]] = {}
    roles = list(catalog)
    for stratum in sorted(grouped):
        members = grouped[stratum]
        rich_flags = {account_id in rich_set for account_id in members}
        if len(rich_flags) > 1:
            raise ValueError(
                f"stratum '{stratum}' mixes rich and non-rich accounts; "
                "eligibility must be part of the frozen stratum"
            )
        stratum_is_rich = True in rich_flags
        configured = normalized_quotas[stratum]
        if set(configured) != set(roles):
            raise ValueError(
                f"quotas for stratum '{stratum}' must name every role exactly; "
                f"expected={roles}, observed={sorted(configured)}"
            )
        quotas: Dict[str, int] = {}
        for role in roles:
            raw_quota = configured[role]
            if isinstance(raw_quota, bool) or not isinstance(raw_quota, int):
                raise ValueError(
                    f"quota for stratum '{stratum}', role '{role}' must be an integer"
                )
            if raw_quota < 0:
                raise ValueError(
                    f"quota for stratum '{stratum}', role '{role}' must be non-negative"
                )
            if raw_quota and catalog[role]["requiresRich"] and not stratum_is_rich:
                raise ValueError(
                    f"stratum '{stratum}' assigns non-rich accounts to "
                    f"rich-only role '{role}'"
                )
            quotas[role] = raw_quota
        if sum(quotas.values()) != len(members):
            raise ValueError(
                f"quota total for stratum '{stratum}' is {sum(quotas.values())}; "
                f"expected {len(members)}"
            )
        terminal_quota = sum(quotas[role] for role in terminal_roles)
        if terminal_quota <= 0:
            raise ValueError(
                f"stratum '{stratum}' must have a positive terminal-test quota"
            )

        ordered = sorted(
            members,
            key=lambda account_id: (
                _allocation_key(
                    account_id=account_id,
                    stratum=stratum,
                    seed=parsed_seed,
                    role_registry_id=registry_id,
                ),
                account_id,
            ),
        )
        probabilities = {
            role: quotas[role] / len(members)
            for role in roles
        }
        cursor = 0
        for role in roles:
            for account_id in ordered[cursor : cursor + quotas[role]]:
                assignments[account_id] = {
                    "accountId": account_id,
                    "stratum": stratum,
                    "assignedRole": role,
                    "assignedProbability": probabilities[role],
                    "terminalTestProbability": terminal_quota / len(members),
                    "roleProbabilities": probabilities,
                    "roleRegistryId": registry_id,
                }
            cursor += quotas[role]

    if set(assignments) != account_set:
        missing = sorted(account_set - set(assignments))
        raise RuntimeError(
            f"role allocation failed to assign every account; missing={missing}"
        )
    return [assignments[account_id] for account_id in accounts]
