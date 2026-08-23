"""CLI safety contracts before the one paid dossier acquisition."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.run_dossier_pretrial_acquisition as cli
from src.evaluation.dossier_executor_types import AcquisitionExecutionError


PLAN_HASH = "a" * 64


def _preflight() -> dict[str, Any]:
    return {
        "plan_sha256": PLAN_HASH,
        "selection_manifest_sha256": "b" * 64,
        "price_card_sha256": "c" * 64,
        "panel_run_id": "dharma-boundary-pretrial-v1",
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
        "holdout_handle_count": 1,
        "holdout_account_id_count": 1,
        "holdout_snapshot_sha256": "e" * 64,
        "_frozen_holdout_handles": frozenset({"heldout"}),
        "_frozen_holdout_account_ids": frozenset({"99"}),
    }


def _plan() -> dict[str, Any]:
    return {
        "plan_sha256": PLAN_HASH,
        "reservation": {
            "total_credits": 3_846,
            "total_usd": "0.03846",
            "request_count": 26,
        },
    }


def _args(tmp_path: Path, output: Path) -> list[str]:
    plan = tmp_path / "plan.json"
    panel = tmp_path / "panel.json"
    card = tmp_path / "card.json"
    database = tmp_path / "archive.db"
    env_file = tmp_path / "paid.env"
    plan.write_text(json.dumps(_plan()))
    panel.write_text("{}")
    card.write_text("{}")
    database.write_bytes(b"")
    env_file.write_text("TWITTERAPI_IO_API_KEY=not-read-in-invalid-test\n")
    return [
        "--plan", str(plan),
        "--panel", str(panel),
        "--price-card", str(card),
        "--archive-db", str(database),
        "--expected-plan-sha256", PLAN_HASH,
        "--execute",
        "--accepted-max-credits", "3846",
        "--accepted-max-usd", "0.03846",
        "--env-file", str(env_file),
        "--output-dir", str(output),
    ]


def test_outside_output_is_rejected_before_credential_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_root = tmp_path / "repo" / "data" / "private"
    private_root.mkdir(parents=True)
    credential_reads = 0

    def forbidden_key_read(path: Path) -> str:
        nonlocal credential_reads
        credential_reads += 1
        raise AssertionError("credential read before output validation")

    monkeypatch.setattr(cli, "PRIVATE_ROOT", private_root, raising=False)
    monkeypatch.setattr(cli, "preflight_dossier_execution", lambda **_: _preflight())
    monkeypatch.setattr(cli, "_load_key", forbidden_key_read)

    result = cli.main(_args(tmp_path, tmp_path / "outside" / "run"))

    assert result == 1
    assert credential_reads == 0


def test_cap_mismatch_is_rejected_before_bundle_or_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    private_root = tmp_path / "data" / "private"
    private_root.mkdir(parents=True)
    bundle_calls = 0
    credential_reads = 0

    class Bundle:
        @classmethod
        def initialize(cls, **kwargs: Any):
            nonlocal bundle_calls
            bundle_calls += 1
            return cls()

        def source_object(self, label: str) -> dict[str, Any]:
            return _plan()

    def key_read(path: Path) -> str:
        nonlocal credential_reads
        credential_reads += 1
        return "secret"

    monkeypatch.setattr(cli, "PRIVATE_ROOT", private_root, raising=False)
    monkeypatch.setattr(cli, "DossierExecutionBundle", Bundle)
    monkeypatch.setattr(cli, "preflight_dossier_execution", lambda **_: _preflight())
    monkeypatch.setattr(cli, "_load_key", key_read)
    args = _args(tmp_path, private_root / "run")
    args[args.index("--accepted-max-credits") + 1] = "3847"

    result = cli.main(args)

    assert result == 1
    assert bundle_calls == 0
    assert credential_reads == 0


def test_private_execution_failure_is_not_rendered_to_console(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = tmp_path / "data" / "private"
    private_root.mkdir(parents=True)
    private_message = "@privatepanelhandle failed identity binding"
    stored_receipts: list[dict[str, Any]] = []

    class Bundle:
        path = private_root / "run"

        @classmethod
        def initialize(cls, **kwargs: Any):
            return cls()

        def source_object(self, label: str) -> dict[str, Any]:
            return _plan()

        def write_execution_receipt(self, receipt: dict[str, Any]) -> None:
            stored_receipts.append(receipt)

        def write_response_records(self, **kwargs: Any) -> None:
            pass

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    class Transport:
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def response_records(self) -> list[dict[str, Any]]:
            return []

    receipt = {"status": "aborted", "failure": {"message": private_message}}
    monkeypatch.setattr(cli, "PRIVATE_ROOT", private_root, raising=False)
    monkeypatch.setattr(cli, "DossierExecutionBundle", Bundle)
    monkeypatch.setattr(cli, "preflight_dossier_execution", lambda **_: _preflight())
    monkeypatch.setattr(cli, "_load_key", lambda _: "secret")
    monkeypatch.setattr(cli.httpx, "Client", lambda **_: Client())
    monkeypatch.setattr(cli, "TwitterApiIoHttpTransport", Transport)

    def fail(**kwargs: Any) -> dict[str, Any]:
        raise AcquisitionExecutionError(private_message, receipt=receipt)

    monkeypatch.setattr(cli, "execute_dossier_acquisition_plan", fail)

    result = cli.main(_args(tmp_path, private_root / "run"))

    assert result == 1
    assert stored_receipts == [receipt]
    assert "privatepanelhandle" not in capsys.readouterr().out


def test_success_artifacts_are_durable_before_client_close_and_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    private_root = tmp_path / "data" / "private"
    private_root.mkdir(parents=True)

    class Bundle:
        path = private_root / "run"

        @classmethod
        def initialize(cls, **kwargs: Any):
            events.append("bundle")
            return cls()

        def source_object(self, label: str) -> dict[str, Any]:
            assert label == "plan"
            return _plan()

        def write_json(self, name: str, value: Any) -> None:
            events.append(name)

        def write_execution_receipt(self, receipt: dict[str, Any]) -> None:
            events.append("execution-receipt.json")

        def write_response_records(self, *, filename: str, **kwargs: Any) -> None:
            events.append(filename)

    class Client:
        def __enter__(self):
            events.append("client-open")
            return self

        def __exit__(self, *args: Any) -> None:
            assert "execution-receipt.json" in events
            assert "raw-response-records.json" in events
            assert "response-evidence.json" in events
            events.append("client-close")

    class Transport:
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def response_records(self) -> list[dict[str, Any]]:
            return []

    receipt = {"balance": {"debited_credits": 48}}
    monkeypatch.setattr(cli, "PRIVATE_ROOT", private_root, raising=False)
    monkeypatch.setattr(cli, "DossierExecutionBundle", Bundle, raising=False)
    monkeypatch.setattr(cli, "preflight_dossier_execution", lambda **_: _preflight())
    monkeypatch.setattr(cli, "_load_key", lambda _: "secret")
    monkeypatch.setattr(cli.httpx, "Client", lambda **_: Client())
    monkeypatch.setattr(cli, "TwitterApiIoHttpTransport", Transport)
    def execute(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["frozen_holdout_account_ids"] == frozenset({"99"})
        return receipt

    monkeypatch.setattr(cli, "execute_dossier_acquisition_plan", execute)
    monkeypatch.setattr(cli, "build_dossier_evidence_artifact", lambda **_: {"e": 1})

    def snapshot(**kwargs: Any) -> dict[str, Any]:
        assert "response-evidence.json" in events
        assert kwargs["snapshot_id"] == "dharma-boundary-pretrial-v1"
        events.append("snapshot-transform")
        return {"snapshotHash": "d" * 64}

    monkeypatch.setattr(cli, "build_research_notes_snapshot_from_evidence", snapshot)

    result = cli.main(_args(tmp_path, private_root / "run"))

    assert result == 0
    assert events.index("response-evidence.json") < events.index("snapshot-transform")
    assert events.index("dossier-snapshot.json") < events.index("client-close")
