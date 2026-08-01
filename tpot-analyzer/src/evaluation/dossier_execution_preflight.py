"""Filesystem and archive preflight for a frozen dossier acquisition."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .acquisition_manifest import (
    AcquisitionPlanError,
    canonical_json_hash,
    hash_plan_manifest,
    normalize_handle,
    parse_time,
)
from .dossier_execution_contract import validate_execution_acceptance
from .dossier_executor_types import AcquisitionExecutionError
from .holdout_snapshot import HoldoutSnapshotError, read_holdout_snapshot


class DossierPreflightError(ValueError):
    """Raised before transport when frozen acquisition inputs do not agree."""


_SHA256 = re.compile(r"[0-9a-f]{64}")
_PANEL_FIELDS = set("schema_version run_id created_at source_takes_sha256 selection_policy accounts".split())
_POLICY_FIELDS = set("source selected_before_pretrial_answers excluded_existing_holdout_handles counts".split())
_ACCOUNT_FIELDS = {"handle", "stratum", "fetch_profile", "recent_tweets_limit"}
_EXPECTED_STRATA = {"likely_positive": 4, "boundary": 6, "likely_negative": 2}


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DossierPreflightError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise DossierPreflightError(f"{label} must be a JSON object")
    return value


def _file_sha256(path: Path, label: str) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise DossierPreflightError(f"cannot hash {label}: {error}") from error
    return digest.hexdigest()


def _exact_fields(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise DossierPreflightError(
            f"{label} fields are not exact: missing={missing}, extra={extra}"
        )


def _normalized_handle(value: Any, label: str) -> str:
    try:
        return normalize_handle(value)
    except AcquisitionPlanError as error:
        raise DossierPreflightError(f"{label} contains an invalid handle") from error


def _validate_panel(panel: dict[str, Any]) -> tuple[
    dict[str, tuple[bool, int]], dict[str, int]
]:
    _exact_fields(panel, _PANEL_FIELDS, "panel")
    if type(panel["schema_version"]) is not int or panel["schema_version"] != 1:
        raise DossierPreflightError("panel schema_version must be exactly 1")
    run_id = panel["run_id"]
    if not isinstance(run_id, str) or re.fullmatch(r"[a-z0-9][a-z0-9-]*", run_id) is None:
        raise DossierPreflightError("panel run_id must be a nonempty slug")
    try:
        parse_time(panel["created_at"], "panel.created_at")
    except AcquisitionPlanError as error:
        raise DossierPreflightError(str(error)) from error
    if not _is_sha256(panel["source_takes_sha256"]):
        raise DossierPreflightError("panel source_takes_sha256 must be SHA-256")

    policy = panel["selection_policy"]
    if not isinstance(policy, dict):
        raise DossierPreflightError("panel selection_policy must be an object")
    _exact_fields(policy, _POLICY_FIELDS, "panel selection_policy")
    source = policy["source"]
    if not isinstance(source, str) or not source.strip() or source != source.strip():
        raise DossierPreflightError("panel selection source must be nonempty")
    if policy["selected_before_pretrial_answers"] is not True:
        raise DossierPreflightError("panel must be selected before pretrial answers")
    if policy["excluded_existing_holdout_handles"] is not True:
        raise DossierPreflightError("panel must declare prior holdout exclusion")
    declared = policy["counts"]
    if (
        not isinstance(declared, dict)
        or set(declared) != set(_EXPECTED_STRATA)
        or any(type(value) is not int for value in declared.values())
        or declared != _EXPECTED_STRATA
    ):
        raise DossierPreflightError("panel declared strata must be exactly 4/6/2")

    accounts = panel["accounts"]
    if not isinstance(accounts, list) or len(accounts) != 12:
        raise DossierPreflightError("panel must contain exactly 12 accounts")
    intents: dict[str, tuple[bool, int]] = {}
    strata: Counter[str] = Counter()
    for account in accounts:
        if not isinstance(account, dict):
            raise DossierPreflightError("each panel account must be an object")
        _exact_fields(account, _ACCOUNT_FIELDS, "panel account")
        handle = _normalized_handle(account["handle"], "panel")
        if handle in intents:
            raise DossierPreflightError("panel requires unique normalized handles")
        stratum = account["stratum"]
        if stratum not in _EXPECTED_STRATA:
            raise DossierPreflightError("panel account has an unapproved stratum")
        fetch_profile = account["fetch_profile"]
        tweet_limit = account["recent_tweets_limit"]
        if type(fetch_profile) is not bool:
            raise DossierPreflightError("panel fetch_profile must be boolean")
        if type(tweet_limit) is not int or not 0 <= tweet_limit <= 20:
            raise DossierPreflightError(
                "panel recent_tweets_limit must be an integer from 0 through 20"
            )
        if not fetch_profile and tweet_limit == 0:
            raise DossierPreflightError("panel account must request evidence")
        intents[handle] = (fetch_profile, tweet_limit)
        strata[stratum] += 1
    observed = {name: strata[name] for name in _EXPECTED_STRATA}
    if observed != _EXPECTED_STRATA:
        raise DossierPreflightError("panel observed strata must be exactly 4/6/2")
    return intents, observed


def _plan_intents(plan: dict[str, Any]) -> tuple[
    dict[str, tuple[bool, int]], dict[str, int]
]:
    """Derive intent after validate_execution_acceptance proved plan shape."""
    intents: dict[str, tuple[bool, int]] = {}
    tweet_count = 0
    maximum_tweets = 0
    for target in plan["targets"]:
        handle = target["handle"]
        actions = target["actions"]
        tweet_limit = actions[1]["maximum_returned"] if len(actions) == 2 else 0
        if tweet_limit:
            tweet_count += 1
            maximum_tweets += tweet_limit
        intents[handle] = (True, tweet_limit)
    return intents, {
        "profile_request_count": len(intents),
        "recent_tweets_request_count": tweet_count,
        "maximum_tweet_count": maximum_tweets,
    }


def _validate_static_plan(
    plan: dict[str, Any], expected_hash: str, checked_at: str
) -> None:
    try:
        reservation = plan["reservation"]
        validate_execution_acceptance(
            plan=plan,
            expected_plan_sha256=expected_hash,
            accepted_max_credits=reservation["total_credits"],
            accepted_max_usd=reservation["total_usd"],
            executed_at=checked_at,
        )
    except (AcquisitionExecutionError, AcquisitionPlanError, KeyError, TypeError) as error:
        detail = str(error)
        suffix = f": {detail}" if "@" not in detail else ""
        raise DossierPreflightError(
            f"full plan execution contract failed at checked_at{suffix}"
        ) from None


def preflight_dossier_execution(
    *,
    plan_path: Path,
    panel_path: Path,
    price_card_path: Path,
    archive_db_path: Path,
    expected_plan_sha256: str,
    checked_at: str,
) -> dict[str, Any]:
    """Validate immutable local inputs without credentials or network access."""
    if not _is_sha256(expected_plan_sha256):
        raise DossierPreflightError("expected plan hash must be lowercase SHA-256")
    plan = _load_object(plan_path, "plan")
    try:
        actual_plan_hash = hash_plan_manifest(plan)
    except AcquisitionPlanError as error:
        raise DossierPreflightError(f"plan is not canonical JSON: {error}") from error
    if plan.get("plan_sha256") != actual_plan_hash:
        raise DossierPreflightError("plan self-hash does not match its contents")
    if actual_plan_hash != expected_plan_sha256:
        raise DossierPreflightError("plan hash does not match explicitly accepted hash")
    _validate_static_plan(plan, expected_plan_sha256, checked_at)

    panel = _load_object(panel_path, "raw panel")
    panel_hash = _file_sha256(panel_path, "raw panel")
    if plan.get("selection_manifest_sha256") != panel_hash:
        raise DossierPreflightError("raw panel SHA-256 does not match frozen plan")
    panel_intents, strata = _validate_panel(panel)

    price_card = _load_object(price_card_path, "price card")
    try:
        price_hash = canonical_json_hash(price_card)
    except AcquisitionPlanError as error:
        raise DossierPreflightError(
            f"price card is not canonical JSON: {error}"
        ) from error
    plan_price = plan.get("price_card")
    if (
        not isinstance(plan_price, dict)
        or plan_price.get("sha256") != price_hash
        or plan_price.get("card_id") != price_card.get("card_id")
        or plan_price.get("verified_at") != price_card.get("verified_at")
    ):
        raise DossierPreflightError("semantic price-card hash does not match plan")

    plan_intents, action_metrics = _plan_intents(plan)
    if set(plan_intents) != set(panel_intents):
        raise DossierPreflightError("plan target set does not match frozen panel")
    if any(plan_intents[key] != panel_intents[key] for key in panel_intents):
        raise DossierPreflightError("plan acquisition intent does not match panel")
    try:
        holdout = read_holdout_snapshot(
            archive_db_path, frozenset(panel_intents)
        )
    except HoldoutSnapshotError as error:
        raise DossierPreflightError(str(error)) from error
    if holdout.panel_handle_overlap_count:
        raise DossierPreflightError(
            "historical holdout overlap is nonzero: "
            f"count={holdout.panel_handle_overlap_count}"
        )
    return {
        "plan_sha256": actual_plan_hash,
        "checked_at": checked_at,
        "selection_manifest_sha256": panel_hash,
        "price_card_sha256": price_hash,
        "panel_run_id": panel["run_id"],
        "panel_account_count": len(panel_intents),
        "strata_counts": strata,
        "plan_target_count": len(plan_intents),
        **action_metrics,
        "holdout_table_present": True,
        "holdout_overlap_count": holdout.panel_handle_overlap_count,
        "holdout_handle_count": holdout.normalized_handle_count,
        "holdout_account_id_count": holdout.account_id_count,
        "holdout_snapshot_sha256": holdout.logical_sha256,
        "_frozen_holdout_handles": holdout.handles,
        "_frozen_holdout_account_ids": holdout.account_ids,
    }
