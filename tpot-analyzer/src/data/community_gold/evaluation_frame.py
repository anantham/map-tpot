"""Frozen evaluation-frame contract for personal ontologies."""
from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

from src.artifacts.digests import json_sha256, ordered_node_digest

from .frame_validation import (
    json_value,
    normalize_scope,
    require_sha256,
    require_text,
    require_utc_aware,
    unique_ids,
)
from .role_allocation import (
    allocate_roles,
    normalize_quotas_by_stratum,
    normalize_role_catalog,
    normalize_strata_by_account,
)

def _digest_payload(payload: Dict[str, Any]) -> str:
    without_digest = {
        key: value
        for key, value in payload.items()
        if key != "manifestDigest"
    }
    return json_sha256(without_digest)


def _rule_manifest(value: Any, *, field: str) -> Dict[str, Any]:
    normalized = json_value(value, field=field)
    if not isinstance(normalized, dict) or not normalized:
        raise ValueError(f"{field} must be a non-empty object")
    return normalized


def freeze_evaluation_frame(
    *,
    frame_id: str,
    scope: Mapping[str, Any],
    u0_account_ids: Sequence[Any],
    fixed_training_ids: Sequence[Any],
    fixed_challenge_ids: Sequence[Any],
    rich_account_ids: Sequence[Any],
    strata_by_account: Mapping[str, str],
    role_catalog: Mapping[str, Mapping[str, Any]],
    quotas_by_stratum: Mapping[str, Mapping[str, int]],
    terminal_test_roles: Sequence[str],
    role_registry_id: str,
    seed: str,
    evidence_snapshot_id: str,
    evidence_snapshot_hash: str,
    graph_manifest_hash: str,
    identity_resolution_digest: str,
    evidence_cutoff: str,
    candidate_rules: Mapping[str, Any],
    ood_rules: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build a validated, content-addressed evaluation frame."""

    frame_name = require_text(frame_id, field="frame_id")
    normalized_scope = normalize_scope(scope)
    u0 = unique_ids(u0_account_ids, field="u0_account_ids")
    if not u0:
        raise ValueError("u0_account_ids must not be empty")
    training = unique_ids(
        fixed_training_ids,
        field="fixed_training_ids",
    )
    challenge = unique_ids(
        fixed_challenge_ids,
        field="fixed_challenge_ids",
    )
    u0_set = set(u0)
    training_set = set(training)
    challenge_set = set(challenge)
    if not training_set <= u0_set:
        raise ValueError(
            "fixed_training_ids must be a subset of u0_account_ids: "
            f"{sorted(training_set - u0_set)}"
        )
    if not challenge_set <= u0_set:
        raise ValueError(
            "fixed_challenge_ids must be a subset of u0_account_ids: "
            f"{sorted(challenge_set - u0_set)}"
        )
    overlap = sorted(training_set & challenge_set)
    if overlap:
        raise ValueError(
            f"fixed_training_ids and fixed_challenge_ids overlap: {overlap}"
        )

    excluded = training_set | challenge_set
    u_eval = [account_id for account_id in u0 if account_id not in excluded]
    if not u_eval:
        raise ValueError("u_eval is empty after fixed training/challenge exclusions")
    rich = unique_ids(rich_account_ids, field="rich_account_ids")
    u_eval_set = set(u_eval)
    if not set(rich) <= u_eval_set:
        raise ValueError(
            "rich_account_ids must be a subset of u_eval: "
            f"{sorted(set(rich) - u_eval_set)}"
        )

    normalized_catalog, normalized_terminal_roles = normalize_role_catalog(
        role_catalog,
        terminal_test_roles,
    )
    normalized_quotas = normalize_quotas_by_stratum(quotas_by_stratum)
    normalized_strata = normalize_strata_by_account(strata_by_account)
    assignments = allocate_roles(
        u_eval,
        strata_by_account=normalized_strata,
        rich_account_ids=rich,
        role_catalog=normalized_catalog,
        quotas_by_stratum=normalized_quotas,
        terminal_test_roles=normalized_terminal_roles,
        seed=seed,
        role_registry_id=role_registry_id,
    )
    payload: Dict[str, Any] = {
        "schemaVersion": 1,
        "frameId": frame_name,
        "scope": normalized_scope,
        "evidence": {
            "snapshotId": require_text(
                evidence_snapshot_id,
                field="evidence_snapshot_id",
            ),
            "snapshotHash": require_sha256(
                evidence_snapshot_hash,
                field="evidence_snapshot_hash",
            ),
            "graphManifestHash": require_sha256(
                graph_manifest_hash,
                field="graph_manifest_hash",
            ),
            "identityResolutionDigest": require_sha256(
                identity_resolution_digest,
                field="identity_resolution_digest",
            ),
            "cutoff": require_utc_aware(
                evidence_cutoff,
                field="evidence_cutoff",
            ),
        },
        "candidateRules": _rule_manifest(
            candidate_rules,
            field="candidate_rules",
        ),
        "oodRules": _rule_manifest(ood_rules, field="ood_rules"),
        "u0AccountIds": u0,
        "fixedTrainingIds": training,
        "fixedChallengeIds": challenge,
        "uEvalAccountIds": u_eval,
        "uRichAccountIds": rich,
        "strataByAccount": normalized_strata,
        "u0Digest": ordered_node_digest(u0),
        "uEvalDigest": ordered_node_digest(u_eval),
        "uRichDigest": ordered_node_digest(rich),
        "roleRegistry": {
            "id": require_text(
                role_registry_id,
                field="role_registry_id",
            ),
            "seed": require_text(seed, field="seed"),
            "catalog": normalized_catalog,
            "quotasByStratum": normalized_quotas,
            "terminalTestRoles": normalized_terminal_roles,
        },
        "randomizationAudit": {
            "status": "caller_seed_unverified",
            "designInferenceEligible": False,
            "probabilitySemantics": (
                "nominal_quota_fraction_conditional_on_uniform_"
                "precommitted_seed"
            ),
        },
        "roleAssignments": assignments,
        "roleAssignmentsDigest": json_sha256(assignments),
        "counts": {
            "u0": len(u0),
            "uEval": len(u_eval),
            "uRich": len(rich),
        },
    }
    payload["manifestDigest"] = _digest_payload(payload)
    return payload


def validate_evaluation_frame(frame: Dict[str, Any]) -> None:
    """Fail when a serialized evaluation frame is incomplete or tampered."""

    if not isinstance(frame, dict):
        raise ValueError("evaluation frame must be an object")
    observed_digest = frame.get("manifestDigest")
    if not isinstance(observed_digest, str):
        raise ValueError("manifestDigest is required")
    expected_digest = _digest_payload(frame)
    if observed_digest != expected_digest:
        raise ValueError(
            "manifestDigest mismatch: "
            f"expected={expected_digest}, observed={observed_digest}"
        )
    try:
        evidence = frame["evidence"]
        registry = frame["roleRegistry"]
        expected = freeze_evaluation_frame(
            frame_id=frame["frameId"],
            scope=frame["scope"],
            u0_account_ids=frame["u0AccountIds"],
            fixed_training_ids=frame["fixedTrainingIds"],
            fixed_challenge_ids=frame["fixedChallengeIds"],
            rich_account_ids=frame["uRichAccountIds"],
            strata_by_account=frame["strataByAccount"],
            role_catalog=registry["catalog"],
            quotas_by_stratum=registry["quotasByStratum"],
            terminal_test_roles=registry["terminalTestRoles"],
            role_registry_id=registry["id"],
            seed=registry["seed"],
            evidence_snapshot_id=evidence["snapshotId"],
            evidence_snapshot_hash=evidence["snapshotHash"],
            graph_manifest_hash=evidence["graphManifestHash"],
            identity_resolution_digest=evidence["identityResolutionDigest"],
            evidence_cutoff=evidence["cutoff"],
            candidate_rules=frame["candidateRules"],
            ood_rules=frame["oodRules"],
        )
    except KeyError as exc:
        raise ValueError(f"evaluation frame is missing field: {exc.args[0]}") from exc
    if expected != frame:
        mismatched = sorted(
            key
            for key in set(expected) | set(frame)
            if expected.get(key) != frame.get(key)
        )
        raise ValueError(
            f"evaluation frame derived fields mismatch: {mismatched}"
        )
