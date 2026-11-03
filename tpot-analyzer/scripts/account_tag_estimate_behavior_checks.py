"""Focused subprocess checks for the estimate-trajectory verifier."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph-explorer"


@dataclass(frozen=True)
class BehaviorCheck:
    name: str
    passed: bool
    detail: str


def command_check(
    name: str, command: Sequence[str], cwd: Path
) -> BehaviorCheck:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return BehaviorCheck(name, False, f"{type(exc).__name__}: {exc}")
    output = "\n".join((result.stdout, result.stderr))
    summary = next(
        (
            line.strip()
            for line in reversed(output.splitlines())
            if " passed" in line or " Tests  " in line
        ),
        f"exit={result.returncode}",
    )
    return BehaviorCheck(name, result.returncode == 0, summary)


def behavior_checks() -> list[BehaviorCheck]:
    backend = command_check(
        "Backend behavior",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_account_tag_estimates.py",
            "tests/test_account_tag_estimate_routes.py",
            "-q",
        ],
        ROOT,
    )
    frontend = command_check(
        "Frontend behavior",
        [
            str(GRAPH / "node_modules" / ".bin" / "vitest"),
            "run",
            "--configLoader",
            "runner",
            "src/tagEstimateApi.test.js",
            "src/researchNotes/TagEstimateEditor.test.jsx",
            "src/AccountTagPanel.estimates.test.jsx",
        ],
        GRAPH,
    )
    return [backend, frontend]
