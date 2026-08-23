"""Public-output privacy tests after dossier network execution begins."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import scripts.run_dossier_pretrial_acquisition as cli
from tests.test_run_dossier_pretrial_acquisition import _args, _plan, _preflight


@pytest.mark.parametrize(
    "stage,error_type,diagnostic_write_fails",
    [
        ("evidence", ValueError, False),
        ("evidence", RuntimeError, False),
        ("evidence", ValueError, True),
        ("client_close", RuntimeError, False),
    ],
)
def test_post_network_errors_are_redacted_without_reacquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stage: str,
    error_type: type[Exception],
    diagnostic_write_fails: bool,
) -> None:
    private_root = tmp_path / "data" / "private"
    private_root.mkdir(parents=True)
    executions = 0
    private_message = "@privatepanelhandle included private tweet text"
    diagnostics: list[dict[str, Any]] = []

    class Bundle:
        path = private_root / "run"

        @classmethod
        def initialize(cls, **kwargs: Any):
            return cls()

        def source_object(self, label: str) -> dict[str, Any]:
            return _plan()

        def write_execution_receipt(self, receipt: dict[str, Any]) -> None:
            pass

        def write_response_records(self, **kwargs: Any) -> None:
            pass

        def write_json(self, name: str, value: Any) -> None:
            if name == "post-network-error.json":
                if diagnostic_write_fails:
                    raise RuntimeError("secondary private diagnostic failure")
                diagnostics.append(value)

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            if stage == "client_close":
                raise error_type(private_message)

    class Transport:
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def response_records(self) -> list[dict[str, Any]]:
            return []

    def execute(**kwargs: Any) -> dict[str, Any]:
        nonlocal executions
        executions += 1
        return {"balance": {"debited_credits": 0}}

    def fail_evidence(**kwargs: Any) -> dict[str, Any]:
        if stage == "evidence":
            raise error_type(private_message)
        return {"evidence": True}

    monkeypatch.setattr(cli, "PRIVATE_ROOT", private_root, raising=False)
    monkeypatch.setattr(cli, "DossierExecutionBundle", Bundle)
    monkeypatch.setattr(cli, "preflight_dossier_execution", lambda **_: _preflight())
    monkeypatch.setattr(cli, "_load_key", lambda _: "secret")
    monkeypatch.setattr(cli.httpx, "Client", lambda **_: Client())
    monkeypatch.setattr(cli, "TwitterApiIoHttpTransport", Transport)
    monkeypatch.setattr(cli, "execute_dossier_acquisition_plan", execute)
    monkeypatch.setattr(cli, "build_dossier_evidence_artifact", fail_evidence)
    monkeypatch.setattr(
        cli,
        "build_research_notes_snapshot_from_evidence",
        lambda **_: {"snapshotHash": "d" * 64},
    )

    result = cli.main(_args(tmp_path, private_root / "run"))
    rendered = capsys.readouterr()

    assert result == 1
    assert executions == 1
    assert "privatepanelhandle" not in rendered.out + rendered.err
    assert "private tweet text" not in rendered.out + rendered.err
    assert "secondary private diagnostic failure" not in rendered.out + rendered.err
    if diagnostic_write_fails:
        assert diagnostics == []
    else:
        assert len(diagnostics) == 1
        assert diagnostics[0]["phase"] == (
            "build_evidence" if stage == "evidence" else "client_close"
        )
        assert "detail" not in diagnostics[0]
