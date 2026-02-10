#!/usr/bin/env python3
"""Verify documentation hygiene for canonical TPOT docs.

Checks:
- Canonical docs exist.
- Active guides no longer reference legacy `scripts/api_server.py`.
- ADR references use current `docs/reference/...` paths.
- Docs index includes canonical + historical signposts.
- Roadmap marks PLAYBOOK workflow documentation as complete.
- Historical docs include modernization/supersession notes.
- Legacy references in historical docs are explicitly contextualized.
- Historical docs avoid stale runnable command examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _contains(path: Path, needle: str) -> bool:
    return needle in _read_text(path)


def _markdown_files(path: Path) -> List[Path]:
    if not path.exists():
        return []
    return sorted(candidate for candidate in path.glob("*.md") if candidate.is_file())


def run_checks(project_root: Path) -> List[CheckResult]:
    docs = project_root / "docs"
    checks: List[CheckResult] = []

    required_docs = [
        docs / "index.md",
        docs / "PLAYBOOK.md",
        docs / "guides" / "QUICKSTART.md",
        docs / "guides" / "TEST_MODE.md",
        docs / "TESTING_METHODOLOGY.md",
    ]
    missing = [str(path.relative_to(project_root)) for path in required_docs if not path.exists()]
    checks.append(
        CheckResult(
            name="Canonical docs present",
            passed=not missing,
            detail="all required files exist" if not missing else f"missing: {', '.join(missing)}",
        )
    )

    active_docs = [
        docs / "guides" / "QUICKSTART.md",
        docs / "guides" / "TEST_MODE.md",
        docs / "PLAYBOOK.md",
        docs / "TESTING_METHODOLOGY.md",
    ]
    legacy_refs = []
    for path in active_docs:
        if path.exists() and _contains(path, "scripts/api_server.py"):
            legacy_refs.append(str(path.relative_to(project_root)))
    checks.append(
        CheckResult(
            name="No legacy api_server in active docs",
            passed=not legacy_refs,
            detail="no legacy references found" if not legacy_refs else f"legacy refs in: {', '.join(legacy_refs)}",
        )
    )

    adr003 = docs / "adr" / "003-backend-api-integration.md"
    adr005 = docs / "adr" / "005-blob-storage-import.md"
    bad_refs = []
    if adr003.exists() and _contains(adr003, "docs/BACKEND_IMPLEMENTATION.md"):
        bad_refs.append("docs/adr/003-backend-api-integration.md -> docs/BACKEND_IMPLEMENTATION.md")
    if adr005.exists() and _contains(adr005, "docs/DATABASE_SCHEMA.md"):
        bad_refs.append("docs/adr/005-blob-storage-import.md -> docs/DATABASE_SCHEMA.md")
    checks.append(
        CheckResult(
            name="ADR reference paths modernized",
            passed=not bad_refs,
            detail="ADR paths point to docs/reference/" if not bad_refs else "; ".join(bad_refs),
        )
    )

    index_path = docs / "index.md"
    index_ok = (
        index_path.exists()
        and _contains(index_path, "[Playbook](PLAYBOOK.md)")
        and _contains(index_path, "## Historical / Planning Notes")
    )
    checks.append(
        CheckResult(
            name="Docs index includes canonical + historical guidance",
            passed=index_ok,
            detail="Playbook + Historical/Planning sections present" if index_ok else "missing Playbook link or Historical section",
        )
    )

    roadmap_path = docs / "ROADMAP.md"
    roadmap_ok = roadmap_path.exists() and _contains(
        roadmap_path,
        "[x] Document end-to-end enrichment + explorer refresh workflow in `docs/PLAYBOOK.md`",
    )
    checks.append(
        CheckResult(
            name="Roadmap tracks PLAYBOOK completion",
            passed=roadmap_ok,
            detail="ROADMAP marks PLAYBOOK item complete" if roadmap_ok else "PLAYBOOK completion not marked in ROADMAP",
        )
    )

    testing_path = docs / "TESTING_METHODOLOGY.md"
    stale_wording = testing_path.exists() and _contains(testing_path, "NEW, untracked")
    checks.append(
        CheckResult(
            name="Testing methodology stale wording removed",
            passed=not stale_wording,
            detail="no 'NEW, untracked' wording present" if not stale_wording else "found stale 'NEW, untracked' wording",
        )
    )

    historical_task_doc = docs / "tasks" / "E2E_TESTS.md"
    historical_bugfix_doc = docs / "archive" / "BUGFIXES.md"
    historical_files = _markdown_files(docs / "tasks") + _markdown_files(docs / "archive")
    historical_notes_ok = (
        historical_task_doc.exists()
        and _contains(historical_task_doc, "## Modernization Note (2026-02-09)")
        and historical_bugfix_doc.exists()
        and _contains(historical_bugfix_doc, "Historical note (updated 2026-02-09)")
    )
    checks.append(
        CheckResult(
            name="Historical docs have modernization notes",
            passed=historical_notes_ok,
            detail=(
                "E2E task + bugfix archive include modernization/supersession notes"
                if historical_notes_ok
                else "missing modernization note in docs/tasks/E2E_TESTS.md or docs/archive/BUGFIXES.md"
            ),
        )
    )

    legacy_context_requirements = {
        "scripts/api_server.py": ("historical", "at the time"),
        "scripts/create_test_fixtures.py": ("superseded", "modernization note"),
        "scripts/start_test_backend.sh": ("superseded", "modernization note"),
        "scripts/run_all_tests.sh": ("superseded", "modernization note"),
    }
    contextualization_failures = []
    for path in historical_files:
        lowered = _read_text(path).lower()
        for needle, markers in legacy_context_requirements.items():
            if needle in lowered and not all(marker in lowered for marker in markers):
                contextualization_failures.append(f"{path.relative_to(project_root)} -> {needle}")
    checks.append(
        CheckResult(
            name="Historical legacy references are contextualized",
            passed=not contextualization_failures,
            detail=(
                f"checked {len(historical_files)} historical markdown files"
                if not contextualization_failures
                else "; ".join(contextualization_failures)
            ),
        )
    )

    historical_stale_patterns = [
        "python scripts/create_test_fixtures.py",
        ".venv/bin/python3 scripts/api_server.py",
        "python3 scripts/api_server.py",
    ]
    stale_hits = []
    for path in historical_files:
        content = _read_text(path)
        for pattern in historical_stale_patterns:
            if pattern in content:
                stale_hits.append(f"{path.relative_to(project_root)} -> {pattern}")
    checks.append(
        CheckResult(
            name="Historical docs avoid stale runnable commands",
            passed=not stale_hits,
            detail=(
                f"no direct stale runnable commands found across {len(historical_files)} historical files"
                if not stale_hits
                else "; ".join(stale_hits)
            ),
        )
    )

    return checks


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    checks = run_checks(project_root)

    passed = 0
    failed = 0
    print("TPOT Docs Hygiene Verification")
    print("=" * 40)
    for check in checks:
        mark = "✓" if check.passed else "✗"
        print(f"{mark} {check.name}: {check.detail}")
        if check.passed:
            passed += 1
        else:
            failed += 1

    print("-" * 40)
    print(f"Checks run: {len(checks)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        print("Next steps:")
        print("1. Update the failing docs listed above.")
        print("2. Re-run `python -m scripts.verify_docs_hygiene`.")
        return 1

    print("Next steps:")
    print("1. Add this command to release/docs QA checklists.")
    print("2. Keep docs/index.md in sync when adding or superseding docs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
