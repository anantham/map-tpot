"""Behavioral contracts for durable private dossier execution bundles."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.evaluation.acquisition_manifest import canonical_json_hash, hash_plan_manifest
from src.evaluation.dossier_execution_bundle import (
    DossierExecutionBundle,
    DossierExecutionBundleError,
)


def _source_files(tmp_path: Path) -> tuple[dict[str, Path], dict]:
    source = tmp_path / "source"
    source.mkdir()
    plan = {"kind": "fixture", "selection_manifest_sha256": "pending"}
    panel_bytes = b'{"private":"panel"}\n'
    plan["selection_manifest_sha256"] = hashlib.sha256(panel_bytes).hexdigest()
    plan["plan_sha256"] = hash_plan_manifest(plan)
    price = {"credits_per_usd": 100_000}
    payloads = {
        "plan": (json.dumps(plan, indent=1) + "\n").encode(),
        "panel": panel_bytes,
        "price_card": (json.dumps(price, separators=(",", ":")) + "\n").encode(),
    }
    paths = {}
    for name, payload in payloads.items():
        path = source / f"{name}.json"
        path.write_bytes(payload)
        paths[name] = path
    preflight = {
        "plan_sha256": plan["plan_sha256"],
        "selection_manifest_sha256": hashlib.sha256(panel_bytes).hexdigest(),
        "price_card_sha256": canonical_json_hash(price),
        "panel_run_id": "fixture-run",
        "checked_at": "2026-07-31T14:00:00Z",
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
        "holdout_handle_count": 2,
        "holdout_account_id_count": 2,
        "_frozen_holdout_handles": frozenset({"zeta", "alpha"}),
        "_frozen_holdout_account_ids": frozenset({"20", "3"}),
    }
    preflight["holdout_snapshot_sha256"] = canonical_json_hash({
        "schema_version": 1,
        "normalized_handles": ["alpha", "zeta"],
        "account_ids": ["20", "3"],
    })
    return paths, preflight


def _initialize(tmp_path: Path) -> tuple[DossierExecutionBundle, dict[str, Path]]:
    private_root = tmp_path / "data" / "private"
    private_root.mkdir(parents=True)
    sources, preflight = _source_files(tmp_path)
    bundle = DossierExecutionBundle.initialize(
        output_dir=private_root / "run-001",
        private_root=private_root,
        source_paths=sources,
        preflight=preflight,
        accepted_cap={"credits": 3_846, "usd": "0.03846"},
    )
    return bundle, sources


@pytest.mark.parametrize("escape", ["outside", "symlink"])
def test_rejects_output_outside_resolved_private_root(
    tmp_path: Path, escape: str
) -> None:
    private_root = tmp_path / "data" / "private"
    private_root.mkdir(parents=True)
    sources, preflight = _source_files(tmp_path)
    if escape == "outside":
        output = tmp_path / "outside-run"
    else:
        outside = tmp_path / "outside"
        outside.mkdir()
        link = private_root / "escape"
        link.symlink_to(outside, target_is_directory=True)
        output = link / "run"

    with pytest.raises(DossierExecutionBundleError, match="data/private"):
        DossierExecutionBundle.initialize(
            output_dir=output,
            private_root=private_root,
            source_paths=sources,
            preflight=preflight,
            accepted_cap={"credits": 3_846, "usd": "0.03846"},
        )

    assert not output.exists()


def test_initial_bundle_preserves_exact_sources_and_sanitized_preflight(
    tmp_path: Path,
) -> None:
    bundle, sources = _initialize(tmp_path)

    assert oct(bundle.path.stat().st_mode & 0o777) == "0o700"
    assert oct((bundle.path / "events").stat().st_mode & 0o777) == "0o700"
    for label, source in sources.items():
        copied = bundle.path / f"source-{label.replace('_', '-')}.json"
        assert copied.read_bytes() == source.read_bytes()
        assert oct(copied.stat().st_mode & 0o777) == "0o600"
    receipt = json.loads((bundle.path / "preflight-receipt.json").read_text())
    serialized = json.dumps(receipt)
    assert receipt["kind"] == "twitterapiio-dossier-preflight-receipt"
    assert receipt["accepted_cap"] == {"credits": 3_846, "usd": "0.03846"}
    assert str(tmp_path) not in serialized
    assert not any(key.startswith("_") for key in receipt["checks"])
    holdout = json.loads((bundle.path / "source-holdout-snapshot.json").read_text())
    assert holdout["normalized_handles"] == ["alpha", "zeta"]
    assert holdout["account_ids"] == ["20", "3"]
    assert bundle.source_object("plan")["plan_sha256"] == receipt["plan_sha256"]


def test_artifact_write_is_atomic_exclusive_and_mode_0600(tmp_path: Path) -> None:
    bundle, _ = _initialize(tmp_path)
    bundle.write_json("execution-receipt.json", {"status": "first"})

    with pytest.raises(DossierExecutionBundleError, match="already exists"):
        bundle.write_json("execution-receipt.json", {"status": "replacement"})

    target = bundle.path / "execution-receipt.json"
    assert json.loads(target.read_text()) == {"status": "first"}
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert not list(bundle.path.glob(".*.tmp"))


def test_fsynced_journal_is_append_only_and_contains_no_body(tmp_path: Path) -> None:
    bundle, _ = _initialize(tmp_path)
    call_id = bundle.begin_call(
        "/twitter/user/info",
        {"userName": "pilot"},
        "2026-07-31T14:00:00Z",
    )
    attempt = bundle.path / "events" / "0000-attempt.json"
    assert attempt.is_file()
    assert json.loads(attempt.read_text())["event"] == "attempt"

    bundle.record_response(call_id, {
        "endpoint": "/twitter/user/info",
        "params": {"userName": "pilot"},
        "status_code": 200,
        "requested_at": "2026-07-31T14:00:00Z",
        "received_at": "2026-07-31T14:00:01Z",
        "body": {"data": {"description": "full paid response survives crash"}},
    })
    durable_response = bundle.path / "events" / "0000-response.json"
    assert json.loads(durable_response.read_text())["body"] == {
        "data": {"description": "full paid response survives crash"}
    }

    bundle.finish_call(call_id, {
        "outcome": "safe_response",
        "status_code": 200,
        "received_at": "2026-07-31T14:00:01Z",
        "raw_body_sha256": "a" * 64,
        "raw_body_bytes": 42,
        "response_sha256": "b" * 64,
        "failure_code": None,
    })
    observation = bundle.path / "events" / "0000-observation.json"
    value = json.loads(observation.read_text())
    assert value["event"] == "observation"
    assert "body" not in value
    assert oct(attempt.stat().st_mode & 0o777) == "0o600"
    assert oct(durable_response.stat().st_mode & 0o777) == "0o600"
    assert oct(observation.stat().st_mode & 0o777) == "0o600"

    with pytest.raises(DossierExecutionBundleError, match="already observed"):
        bundle.finish_call(call_id, value)


def test_bundle_rejects_source_drift_before_creating_directory(tmp_path: Path) -> None:
    private_root = tmp_path / "data" / "private"
    private_root.mkdir(parents=True)
    sources, preflight = _source_files(tmp_path)
    sources["panel"].write_text('{"changed":true}\n')
    output = private_root / "run"

    with pytest.raises(DossierExecutionBundleError, match="panel.*hash"):
        DossierExecutionBundle.initialize(
            output_dir=output,
            private_root=private_root,
            source_paths=sources,
            preflight=preflight,
            accepted_cap={"credits": 3_846, "usd": "0.03846"},
        )

    assert not output.exists()
