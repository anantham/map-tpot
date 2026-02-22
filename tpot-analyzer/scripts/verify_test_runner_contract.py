#!/usr/bin/env python3
"""Verify local/CI test-runner contracts for interpreter consistency."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def _print_result(name: str, passed: bool, detail: str) -> bool:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}: {detail}")
    return passed


def _check_makefile(makefile: Path) -> list[tuple[str, bool, str]]:
    text = makefile.read_text(encoding="utf-8")
    checks: list[tuple[str, bool, str]] = []

    has_venv_python = "VENV_PY ?= .venv/bin/python" in text
    checks.append(
        ("make-venv-default", has_venv_python, "VENV_PY defaults to .venv/bin/python")
    )

    test_target_uses_pytest_module = bool(
        re.search(r"^test:\s.*\n(?:[ \t].*\n)*[ \t].*\$\(PYTEST\)", text, re.MULTILINE)
    )
    checks.append(
        (
            "make-test-target",
            test_target_uses_pytest_module,
            "test target executes $(PYTEST)",
        )
    )

    smoke_target_exists = bool(re.search(r"^test-smoke:\s", text, re.MULTILINE))
    checks.append(
        ("make-test-smoke-target", smoke_target_exists, "test-smoke target exists")
    )

    return checks


def _check_workflow(workflow: Path) -> list[tuple[str, bool, str]]:
    text = workflow.read_text(encoding="utf-8")
    checks: list[tuple[str, bool, str]] = []

    has_louvain_step = "Verify Louvain dependency contract" in text
    checks.append(
        ("ci-louvain-step", has_louvain_step, "workflow includes dependency contract step")
    )

    runs_louvain_script = "verify_louvain_dependency_contract.py" in text
    checks.append(
        (
            "ci-louvain-script",
            runs_louvain_script,
            "workflow invokes verify_louvain_dependency_contract.py",
        )
    )

    uses_python_module_pytest = "python -m pytest" in text
    checks.append(
        ("ci-python-module-pytest", uses_python_module_pytest, "workflow runs tests via python -m pytest")
    )

    return checks


def main() -> int:
    print("Test Runner Contract Verification")
    print("=" * 34)

    root = Path(__file__).resolve().parent.parent
    makefile = root / "Makefile"
    workflow = root / ".github" / "workflows" / "test.yml"

    checks: list[tuple[str, bool, str]] = []

    if not makefile.exists():
        checks.append(("makefile-exists", False, f"missing {makefile}"))
    else:
        checks.append(("makefile-exists", True, str(makefile)))
        checks.extend(_check_makefile(makefile))

    if not workflow.exists():
        checks.append(("workflow-exists", False, f"missing {workflow}"))
    else:
        checks.append(("workflow-exists", True, str(workflow)))
        checks.extend(_check_workflow(workflow))

    passed = 0
    for name, ok, detail in checks:
        if _print_result(name, ok, detail):
            passed += 1

    total = len(checks)
    print("\nMetrics")
    print(f"- checks_passed: {passed}/{total}")

    if passed == total:
        print("\nNext steps: run `make test-smoke` before opening a PR.")
        return 0

    print("\nNext steps: fix failed contracts, then rerun this verifier.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
