#!/usr/bin/env python3
"""Verify that GitHub can discover and enforce the portable CI contract."""
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
WORKFLOW = REPOSITORY_ROOT / ".github/workflows/test.yml"
NESTED_WORKFLOW = PROJECT_ROOT / ".github/workflows/test.yml"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@dataclass
class Report:
    passed: int = 0
    failed: int = 0

    def check(self, label: str, ok: bool, detail: str) -> None:
        print(f"{'✓' if ok else '✗'} {label}: {detail}")
        self.passed += int(ok)
        self.failed += int(not ok)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def valid_base(revision: str) -> tuple[bool, str]:
    if revision == "0" * 40:
        parent = run("git", "rev-parse", "--verify", "HEAD^")
        if parent.returncode == 0:
            return True, parent.stdout.strip()
        return True, EMPTY_TREE
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        return False, revision or "empty"
    exists = run("git", "cat-file", "-e", f"{revision}^{{commit}}")
    return exists.returncode == 0, revision


def verify_patch_hygiene(report: Report, base: str | None) -> None:
    marker_scan = run(
        "git", "grep", "-n", "-I", "-E",
        r"^(<<<<<<< |=======$|>>>>>>> )",
        "--", ".",
    )
    report.check(
        "tracked conflict markers",
        marker_scan.returncode == 1,
        marker_scan.stdout.strip() or "none",
    )
    for label, args in (
        ("unstaged whitespace", ("git", "diff", "--check")),
        ("staged whitespace", ("git", "diff", "--cached", "--check")),
    ):
        result = run(*args)
        report.check(label, result.returncode == 0, result.stdout.strip() or "clean")
    if base is None:
        return
    ok, resolved = valid_base(base)
    report.check("base revision", ok, resolved)
    if not ok:
        return
    result = run("git", "diff", "--check", f"{resolved}..HEAD")
    report.check(
        "committed patch whitespace",
        result.returncode == 0,
        result.stdout.strip() or f"{resolved[:12]}..HEAD clean",
    )


def verify_workflow(report: Report) -> None:
    report.check("root workflow exists", WORKFLOW.is_file(), str(WORKFLOW))
    report.check(
        "nested workflow retired",
        not NESTED_WORKFLOW.exists(),
        str(NESTED_WORKFLOW),
    )
    if not WORKFLOW.is_file():
        return
    text = WORKFLOW.read_text(encoding="utf-8")
    checks = (
        ("push trigger", "  push:" in text),
        ("pull-request trigger", "  pull_request:" in text),
        ("read-only contents permission", "  contents: read" in text),
        ("full history for patch gate", "fetch-depth: 0" in text),
        ("Python 3.11", "python-version: '3.11'" in text),
        ("Python test job", "name: Python (pytest)" in text),
        ("public-site test job", "name: public-site (vitest + build)" in text),
        ("graph-explorer test job", "name: graph-explorer (vitest + build)" in text),
        ("credential-free pytest selection", "not selenium and not requires_supabase" in text),
        ("API contract verifier", "verify_api_contracts.py" in text),
        ("docs hygiene verifier", "verify_docs_hygiene.py" in text),
        ("CI discovery verifier", "verify_ci_discovery.py" in text),
    )
    for label, ok in checks:
        report.check(label, ok, "present" if ok else "missing")
    node_job_count = text.count("node-version: '22'")
    npm_install_count = text.count("npm ci --no-audit --no-fund")
    build_count = text.count("run: npm run build")
    report.check(
        "Node 22 jobs",
        node_job_count == 2,
        f"count={node_job_count}",
    )
    report.check(
        "clean npm installs",
        npm_install_count == 2,
        f"count={npm_install_count}",
    )
    report.check(
        "production builds",
        build_count == 2,
        f"count={build_count}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="40-character base commit for a committed-range whitespace check",
    )
    args = parser.parse_args()
    report = Report()
    print("CI Discovery Verification")
    print("=" * 25)
    verify_workflow(report)
    verify_patch_hygiene(report, args.base)
    print(f"\nResult: {report.passed}/{report.passed + report.failed} checks passed")
    print("Next steps:")
    if report.failed:
        print("1. Fix the first failed discovery or patch-hygiene invariant.")
        print("2. Do not configure required checks until a real PR run is green.")
    else:
        print("1. Push a branch and confirm all three hosted jobs complete.")
        print("2. Protect main using the check names observed on that run.")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
