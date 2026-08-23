"""Direct script-path invocation contracts for dossier operator tools."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    "name,marker",
    [
        ("run_dossier_pretrial_acquisition.py", "usage:"),
        ("verify_dossier_pretrial_execution.py", "checks_passed=6/6"),
    ],
)
def test_script_path_loads_project_without_pythonpath(
    name: str, marker: str
) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), "--help"],
        cwd=ROOT,
        env={"PATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert marker in result.stdout
    assert "ModuleNotFoundError" not in result.stderr
