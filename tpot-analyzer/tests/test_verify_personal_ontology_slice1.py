from __future__ import annotations

import socket

import pytest

from scripts.verify_personal_ontology_slice1 import main


def test_slice1_verifier_is_human_readable_and_network_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_network(*_args, **_kwargs):
        raise AssertionError("Slice 1 verifier attempted network I/O")

    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)

    result = main()

    output = capsys.readouterr().out
    assert result == 0
    assert "Checks: 6 | Passed: 6 | Failed: 0" in output
    assert "✓ Legacy identity remains unbound" in output
    assert "✓ Training result excludes terminal labels" in output
    assert "✓ Terminal release is exact, replay-safe, and sealing" in output
    assert "min_nominal_terminal_pi=" in output
    assert "Digests: frame=" in output
    assert "Next steps:" in output
