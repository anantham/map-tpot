"""Behavioral tests for the credential-free dossier execution preflight."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from src.evaluation.acquisition_manifest import hash_plan_manifest
from src.evaluation.dossier_acquisition_plan import build_dossier_acquisition_plan
from src.evaluation.dossier_execution_preflight import (
    DossierPreflightError,
    preflight_dossier_execution,
)


ROOT = Path(__file__).parents[1]
PRICE_CARD = ROOT / "data/manifests/twitterapiio_price_card_20260730.json"
STRATA = ["likely_positive"] * 4 + ["boundary"] * 6 + ["likely_negative"] * 2


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _panel() -> dict:
    accounts = [
        {
            "handle": f"Pilot{index:02d}",
            "stratum": stratum,
            "fetch_profile": True,
            "recent_tweets_limit": 20,
        }
        for index, stratum in enumerate(STRATA)
    ]
    return {
        "schema_version": 1,
        "run_id": "dharma-boundary-pretrial-v1",
        "created_at": "2026-07-31T13:45:05Z",
        "source_takes_sha256": "b" * 64,
        "selection_policy": {
            "source": "dated private takes snapshot",
            "selected_before_pretrial_answers": True,
            "excluded_existing_holdout_handles": True,
            "counts": {
                "likely_positive": 4,
                "boundary": 6,
                "likely_negative": 2,
            },
        },
        "accounts": accounts,
    }


def _bundle(tmp_path: Path) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    panel_path = tmp_path / "panel.json"
    plan_path = tmp_path / "plan.json"
    price_path = tmp_path / "price.json"
    db_path = tmp_path / "archive.db"
    panel = _panel()
    _write_json(panel_path, panel)
    price = json.loads(PRICE_CARD.read_text(encoding="utf-8"))
    _write_json(price_path, price)
    plan = build_dossier_acquisition_plan(
        targets=panel["accounts"],
        price_card=price,
        selection_manifest_sha256=_file_hash(panel_path),
        planned_at="2026-07-31T14:34:51Z",
        hard_cap_usd="0.05",
        max_price_age_days=7,
    )
    _write_json(plan_path, plan)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE tpot_directory_holdout (handle TEXT, account_id TEXT)"
        )
        connection.execute(
            "INSERT INTO tpot_directory_holdout VALUES ('unrelated', '99')"
        )
    return {
        "panel": panel,
        "panel_path": panel_path,
        "plan": plan,
        "plan_path": plan_path,
        "price": price,
        "price_path": price_path,
        "db_path": db_path,
        "expected": plan["plan_sha256"],
    }


def _run(bundle: dict) -> dict:
    return preflight_dossier_execution(
        plan_path=bundle["plan_path"],
        panel_path=bundle["panel_path"],
        price_card_path=bundle["price_path"],
        archive_db_path=bundle["db_path"],
        expected_plan_sha256=bundle["expected"],
        checked_at="2026-07-31T15:00:00Z",
    )


def _rewrite_panel_and_rebind(bundle: dict, panel: dict) -> None:
    _write_json(bundle["panel_path"], panel)
    bundle["plan"]["selection_manifest_sha256"] = _file_hash(
        bundle["panel_path"]
    )
    bundle["plan"]["plan_sha256"] = hash_plan_manifest(bundle["plan"])
    bundle["expected"] = bundle["plan"]["plan_sha256"]
    _write_json(bundle["plan_path"], bundle["plan"])


def _rewrite_plan(bundle: dict, plan: dict) -> None:
    plan["plan_sha256"] = hash_plan_manifest(plan)
    bundle["expected"] = plan["plan_sha256"]
    _write_json(bundle["plan_path"], plan)


def test_valid_bundle_returns_only_aggregate_evidence(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)

    result = _run(bundle)

    assert result == {
        "plan_sha256": bundle["expected"],
        "checked_at": "2026-07-31T15:00:00Z",
        "selection_manifest_sha256": _file_hash(bundle["panel_path"]),
        "price_card_sha256": bundle["plan"]["price_card"]["sha256"],
        "panel_run_id": "dharma-boundary-pretrial-v1",
        "panel_account_count": 12,
        "strata_counts": {
            "likely_positive": 4,
            "boundary": 6,
            "likely_negative": 2,
        },
        "plan_target_count": 12,
        "profile_request_count": 12,
        "recent_tweets_request_count": 12,
        "maximum_tweet_count": 240,
        "holdout_table_present": True,
        "holdout_overlap_count": 0,
        "holdout_handle_count": 1,
        "holdout_account_id_count": 1,
        "holdout_snapshot_sha256": result["holdout_snapshot_sha256"],
        "_frozen_holdout_handles": frozenset({"unrelated"}),
        "_frozen_holdout_account_ids": frozenset({"99"}),
    }
    safe = {key: value for key, value in result.items() if not key.startswith("_")}
    serialized = json.dumps(safe)
    assert not any(
        account["handle"].lower() in serialized
        for account in bundle["panel"]["accounts"]
    )
    assert "unrelated" not in serialized
    assert "99" not in serialized


def test_hash_bindings_fail_closed(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    plan = deepcopy(bundle["plan"])
    plan["reservation"]["request_count"] = 999
    _write_json(bundle["plan_path"], plan)
    with pytest.raises(DossierPreflightError, match="self-hash"):
        _run(bundle)

    bundle = _bundle(tmp_path / "expected")
    bundle["expected"] = "f" * 64
    with pytest.raises(DossierPreflightError, match="explicitly accepted"):
        _run(bundle)

    bundle = _bundle(tmp_path / "panel")
    bundle["panel_path"].write_text(
        bundle["panel_path"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DossierPreflightError, match="raw panel"):
        _run(bundle)

    bundle = _bundle(tmp_path / "price")
    price = deepcopy(bundle["price"])
    price["notes"].append("semantic drift")
    _write_json(bundle["price_path"], price)
    with pytest.raises(DossierPreflightError, match="semantic price-card"):
        _run(bundle)


@pytest.mark.parametrize(
    "mutate,message",
    [
        (lambda panel: panel.update(schema_version=2), "schema_version"),
        (
            lambda panel: panel["selection_policy"].update(
                selected_before_pretrial_answers=False
            ),
            "selected before",
        ),
        (
            lambda panel: panel["selection_policy"].update(
                excluded_existing_holdout_handles=False
            ),
            "holdout exclusion",
        ),
        (
            lambda panel: panel["selection_policy"]["counts"].update(boundary=5),
            "declared strata",
        ),
        (
            lambda panel: panel["accounts"][1].update(
                handle=panel["accounts"][0]["handle"].lower()
            ),
            "unique normalized handles",
        ),
        (lambda panel: panel["accounts"].pop(), "exactly 12"),
        (
            lambda panel: panel["accounts"][0].update(unapproved="field"),
            "account fields",
        ),
    ],
)
def test_panel_schema_and_selection_policy_are_strict(
    tmp_path: Path, mutate, message: str
) -> None:
    bundle = _bundle(tmp_path)
    panel = deepcopy(bundle["panel"])
    mutate(panel)
    _rewrite_panel_and_rebind(bundle, panel)

    with pytest.raises(DossierPreflightError, match=message):
        _run(bundle)


def test_full_static_execution_contract_is_part_of_dry_preflight(
    tmp_path: Path,
) -> None:
    bundle = _bundle(tmp_path)
    plan = deepcopy(bundle["plan"])
    plan["reservation"]["request_count"] = 999
    _rewrite_plan(bundle, plan)

    with pytest.raises(
        DossierPreflightError, match="execution contract.*request_count"
    ):
        _run(bundle)


def test_valid_plan_intent_drift_from_panel_is_rejected(tmp_path: Path) -> None:
    bundle = _bundle(tmp_path)
    targets = deepcopy(bundle["panel"]["accounts"])
    targets[0]["recent_tweets_limit"] = 19
    plan = build_dossier_acquisition_plan(
        targets=targets,
        price_card=bundle["price"],
        selection_manifest_sha256=_file_hash(bundle["panel_path"]),
        planned_at="2026-07-31T14:34:51Z",
        hard_cap_usd="0.05",
    )
    bundle["expected"] = plan["plan_sha256"]
    _write_json(bundle["plan_path"], plan)

    with pytest.raises(DossierPreflightError, match="acquisition intent"):
        _run(bundle)


def test_archive_holdout_must_exist_and_have_zero_overlap(tmp_path: Path) -> None:
    overlap = _bundle(tmp_path / "overlap")
    with sqlite3.connect(overlap["db_path"]) as connection:
        connection.execute(
            "INSERT INTO tpot_directory_holdout VALUES ('@PILOT00', '1')"
        )
    with pytest.raises(DossierPreflightError, match="overlap is nonzero"):
        _run(overlap)
