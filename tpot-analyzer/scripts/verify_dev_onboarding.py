#!/usr/bin/env python3
"""Verify baseline developer onboarding docs/dependency contracts.

Checks:
- Base requirements avoid optional NetworKit compile dependency.
- Optional performance requirements include NetworKit pin.
- Quickstart step 4 uses refresh_graph_snapshot as the baseline path.
- Quickstart keeps spectral build as an explicit optional advanced path.
- Quickstart references optional performance install file.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def run_checks(project_root: Path) -> list[CheckResult]:
    checks: list[CheckResult] = []

    requirements = project_root / "requirements.txt"
    perf_requirements = project_root / "requirements-performance.txt"
    quickstart = project_root / "docs" / "guides" / "QUICKSTART.md"

    if not requirements.exists():
        checks.append(CheckResult("requirements.txt exists", False, f"missing {requirements}"))
    else:
        req_text = _read_text(requirements)
        has_networkit = bool(re.search(r"^networkit==", req_text, re.MULTILINE))
        checks.append(
            CheckResult(
                "base requirements are onboarding-safe",
                not has_networkit,
                "networkit not required in base install path"
                if not has_networkit
                else "networkit pin still present in requirements.txt",
            )
        )

    if not perf_requirements.exists():
        checks.append(
            CheckResult(
                "requirements-performance.txt exists",
                False,
                f"missing {perf_requirements}",
            )
        )
    else:
        perf_text = _read_text(perf_requirements)
        has_networkit_perf = bool(re.search(r"^networkit==", perf_text, re.MULTILINE))
        checks.append(
            CheckResult(
                "performance extras include networkit",
                has_networkit_perf,
                "networkit pin found for optional install path"
                if has_networkit_perf
                else "missing networkit pin in requirements-performance.txt",
            )
        )

    if not quickstart.exists():
        checks.append(CheckResult("quickstart exists", False, f"missing {quickstart}"))
        return checks

    qs_text = _read_text(quickstart)

    uses_perf_optional = "requirements-performance.txt" in qs_text
    checks.append(
        CheckResult(
            "quickstart mentions optional performance install",
            uses_perf_optional,
            "found requirements-performance.txt reference"
            if uses_perf_optional
            else "missing optional requirements-performance.txt note",
        )
    )

    step4_match = re.search(
        r"## 4\. Build Graph Snapshot(?P<body>.*?)(?:\n## |\Z)",
        qs_text,
        re.DOTALL,
    )
    if not step4_match:
        checks.append(
            CheckResult("quickstart has step 4 section", False, "could not locate '## 4. Build Graph Snapshot'")
        )
    else:
        step4 = step4_match.group("body")
        has_refresh = "python -m scripts.refresh_graph_snapshot" in step4
        checks.append(
            CheckResult(
                "step 4 uses refresh_graph_snapshot",
                has_refresh,
                "baseline snapshot command present"
                if has_refresh
                else "step 4 missing refresh_graph_snapshot command",
            )
        )

        has_advanced_spectral = "Advanced (optional)" in step4 and "python -m scripts.build_spectral" in step4
        checks.append(
            CheckResult(
                "spectral path is marked advanced",
                has_advanced_spectral,
                "optional spectral note present"
                if has_advanced_spectral
                else "missing optional advanced spectral note in step 4",
            )
        )

    troubleshooting_refresh = bool(
        re.search(
            r'### "No graph data" in frontend[\s\S]*python -m scripts\.refresh_graph_snapshot',
            qs_text,
            re.MULTILINE,
        )
    )
    checks.append(
        CheckResult(
            'troubleshooting "No graph data" uses refresh command',
            troubleshooting_refresh,
            "refresh command found in troubleshooting"
            if troubleshooting_refresh
            else "troubleshooting still references a non-baseline graph build path",
        )
    )

    return checks


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    checks = run_checks(root)

    passed = 0
    print("Developer Onboarding Verification")
    print("=" * 35)
    for check in checks:
        mark = "✓" if check.passed else "✗"
        print(f"{mark} {check.name}: {check.detail}")
        if check.passed:
            passed += 1

    total = len(checks)
    print("-" * 35)
    print(f"Checks run: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")

    if passed != total:
        print("Next steps:")
        print("1. Update requirements/quickstart per failed checks above.")
        print("2. Re-run `python -m scripts.verify_dev_onboarding`.")
        return 1

    print("Next steps:")
    print("1. Run `python -m scripts.verify_docs_hygiene`.")
    print("2. Run a fresh-shell onboarding smoke test before release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
