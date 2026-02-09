"""Run API route/service regression tests with human-friendly output."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


CHECK = "✓"
CROSS = "✗"


def _status(ok: bool, message: str) -> str:
    return f"{CHECK if ok else CROSS} {message}"


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    python_bin = project_root / ".venv" / "bin" / "python"
    tests = [
        "tests/test_cache_manager.py",
        "tests/test_signal_feedback_store.py",
        "tests/test_api_contract_routes.py",
        "tests/test_discovery_endpoint_matrix.py",
    ]

    lines: list[str] = []
    lines.append("TPOT API Route/Service Regression Verification")
    lines.append(f"- project_root: {project_root}")
    lines.append("")

    ok_python = python_bin.exists()
    lines.append(_status(ok_python, f"venv python exists at {python_bin}"))
    if not ok_python:
        lines.append("")
        lines.append("Next steps:")
        lines.append("- Create venv and install deps: `cd tpot-analyzer && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`")
        print("\n".join(lines))
        return 1

    missing_tests = [test for test in tests if not (project_root / test).exists()]
    lines.append(_status(not missing_tests, f"target tests present ({len(tests) - len(missing_tests)}/{len(tests)})"))
    if missing_tests:
        for test in missing_tests:
            lines.append(f"  missing: {test}")
        print("\n".join(lines))
        return 1

    cmd = [str(python_bin), "-m", "pytest", *tests, "-q"]
    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
    )

    summary_text = (result.stdout + "\n" + result.stderr).strip()
    summary_line = ""
    for line in summary_text.splitlines():
        if " passed" in line or " failed" in line or " error" in line:
            summary_line = line

    lines.append(_status(result.returncode == 0, f"pytest exit code == 0 ({result.returncode})"))
    if summary_line:
        lines.append(f"  summary: {summary_line.strip()}")

    # Surface concrete metrics (test counts and duration when available).
    metrics_match = re.search(r"(\d+)\s+passed(?:,?\s+(\d+)\s+failed)?(?:.*?in\s+([0-9.]+)s)?", summary_text)
    if metrics_match:
        passed = int(metrics_match.group(1))
        failed = int(metrics_match.group(2) or 0)
        duration = metrics_match.group(3) or "unknown"
        lines.append(f"  metrics: passed={passed} failed={failed} duration_s={duration}")

    if result.returncode != 0:
        lines.append("")
        lines.append("Pytest output tail:")
        tail = summary_text.splitlines()[-25:]
        lines.extend(tail)

    lines.append("")
    lines.append("Next steps:")
    lines.append("- If this fails, fix route/service regressions before frontend contract work.")
    lines.append("- If this passes, run broader suite: `.venv/bin/python -m pytest tests/test_api.py -q`.")
    print("\n".join(lines))
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
