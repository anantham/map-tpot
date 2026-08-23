#!/usr/bin/env python3
"""Verify the operator-centered tagging workspace without mutating live data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.account_tag_schema import initialize_account_tag_schema  # noqa: E402
from scripts.dev_runtime import resolve_dev_runtime  # noqa: E402


CORE_TABLES = ("account_tags", "account_tag_events")
BACKEND_TESTS = (
    "tests/test_tag_meta_notes.py", "tests/test_account_tags_store.py",
    "tests/test_research_notes_source_route.py",
)
FRONTEND_TESTS = (
    "src/accountsApi.test.js", "src/AccountTagPanel.test.jsx",
    "src/AccountTagPanel.subject.test.jsx",
    "src/ResearchNotesInbox.test.jsx",
    "src/ResearchNotesInbox.persistence.test.jsx",
    "src/ResearchNotesInbox.tagging.test.jsx",
    "src/researchNotes/TagSuggestions.test.jsx",
    "src/researchNotes/TagAutocomplete.test.jsx",
    "src/researchNotes/TagMetaNote.test.jsx",
    "src/researchNotes/WorkingTagImpact.test.jsx", "src/researchNotes/tagSearch.test.js",
    "src/researchNotes/useWorkingTagSelection.test.jsx",
)
def _readonly_connection(path: Path) -> sqlite3.Connection:
    encoded = quote(str(path.resolve()), safe="/")
    conn = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA query_only=ON")
    return conn
def _table_digest(conn: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]
    order = ", ".join(f'"{name}"' for name in columns)
    digest = hashlib.sha256()
    for row in conn.execute(f'SELECT {order} FROM "{table}" ORDER BY {order}'):
        digest.update(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"), default=str)
            .encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()
def _database_state(conn: sqlite3.Connection) -> dict:
    tables = frozenset(
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    )
    counts = {
        table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in (*CORE_TABLES, "tag_meta_notes")
        if table in tables
    }
    digests = {
        table: _table_digest(conn, table)
        for table in (*CORE_TABLES, "tag_meta_notes")
        if table in tables
    }
    account_count, tag_count = 0, 0
    if "account_tags" in tables:
        account_count, tag_count = conn.execute(
            "SELECT COUNT(DISTINCT account_id), COUNT(DISTINCT tag_key) "
            "FROM account_tags"
        ).fetchone()
    return {
        "tables": tables,
        "counts": counts,
        "digests": digests,
        "accounts": int(account_count),
        "tags": int(tag_count),
        "quick_check": str(conn.execute("PRAGMA quick_check(1)").fetchone()[0]),
    }
def _status(passed: bool, label: str, detail: str) -> bool:
    print(f"{'✓' if passed else '✗'} {label}: {detail}")
    return passed

def _pytest_python() -> Path | None:
    candidates: list[Path] = [PROJECT_ROOT / ".venv/bin/python"]
    try:
        runtime = resolve_dev_runtime(PROJECT_ROOT)
        if runtime.primary_project_root is not None:
            candidates.append(runtime.primary_project_root / ".venv/bin/python")
    except Exception:
        pass
    candidates.append(Path(sys.executable))
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        probe = subprocess.run(
            [str(candidate), "-c", "import pytest"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if probe.returncode == 0:
            return candidate
    return None

def _run(label: str, command: list[str], cwd: Path) -> bool:
    printable = shlex.join(command)
    print(f"  command: cd {shlex.quote(str(cwd))} && {printable}")
    started = time.perf_counter()
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False,
    )
    elapsed = time.perf_counter() - started
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    lines = output.splitlines()
    summary = next(
        (line.strip() for line in reversed(lines) if "passed" in line or "failed" in line),
        lines[-1].strip() if lines else "no output",
    )
    passed = result.returncode == 0
    _status(passed, label, f"rc={result.returncode}, {elapsed:.2f}s, {summary}")
    if not passed and lines:
        print("  output tail:")
        for line in lines[-18:]:
            print(f"    {line}")
    return passed

def _verify_database(db_path: Path) -> list[bool]:
    checks: list[bool] = []
    if not db_path.is_file():
        checks.append(_status(False, "live tag database", f"missing at {db_path}"))
        return checks

    print("\nLive data boundary")
    print(f"- path: {db_path.resolve()}")
    print(f"- bytes: {db_path.stat().st_size:,}")
    try:
        with _readonly_connection(db_path) as live:
            query_only = int(live.execute("PRAGMA query_only").fetchone()[0])
            before = _database_state(live)
            checks.append(_status(
                query_only == 1, "live connection is read-only",
                "SQLite URI mode=ro and PRAGMA query_only=1",
            ))
            checks.append(
                _status(
                    before["quick_check"] == "ok",
                    "live SQLite quick_check",
                    before["quick_check"],
                )
            )
            missing = sorted(set(CORE_TABLES) - before["tables"])
            checks.append(_status(
                not missing, "core tag tables", f"missing={missing or 'none'}",
            ))
            if missing:
                return checks
            print(
                "- observed: "
                f"current={before['counts']['account_tags']}, "
                f"events={before['counts']['account_tag_events']}, "
                f"tag_notes={before['counts'].get('tag_meta_notes', 0)}, "
                f"accounts={before['accounts']}, tags={before['tags']}"
            )
            print(
                "- row digests: "
                f"current={before['digests']['account_tags'][:12]}…, "
                f"events={before['digests']['account_tag_events'][:12]}…"
            )
            with tempfile.TemporaryDirectory(prefix="tpot-tagging-ux-") as temp_dir:
                copied_path = Path(temp_dir) / "account_tags.db"
                with sqlite3.connect(copied_path) as copied:
                    live.backup(copied)
                with sqlite3.connect(copied_path) as copied:
                    copied_before = _database_state(copied)
                    initialize_account_tag_schema(copied)
                    copied.commit()
                    copied_after = _database_state(copied)

                same_core = all(
                    copied_before["counts"][table] == copied_after["counts"][table]
                    and copied_before["digests"][table] == copied_after["digests"][table]
                    for table in CORE_TABLES
                )
                notes_preserved = (
                    copied_before["counts"].get("tag_meta_notes", 0)
                    == copied_after["counts"].get("tag_meta_notes", 0)
                    and (
                        "tag_meta_notes" not in copied_before["tables"]
                        or copied_before["digests"]["tag_meta_notes"]
                        == copied_after["digests"]["tag_meta_notes"]
                    )
                )
                checks.append(
                    _status(
                        same_core,
                        "temp-copy migration preserves judgments",
                        f"current={copied_after['counts']['account_tags']}, "
                        f"events={copied_after['counts']['account_tag_events']}",
                    )
                )
                checks.append(
                    _status(
                        "tag_meta_notes" in copied_after["tables"] and notes_preserved,
                        "additive tag-note schema",
                        f"notes={copied_after['counts'].get('tag_meta_notes', 0)}, "
                        "existing note history preserved",
                    )
                )
                checks.append(
                    _status(
                        copied_after["quick_check"] == "ok",
                        "migrated temp copy quick_check",
                        copied_after["quick_check"],
                    )
                )
    except (OSError, sqlite3.DatabaseError) as exc:
        checks.append(
            _status(False, "database verification", f"{type(exc).__name__}: {exc}")
        )
    return checks

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_dir = os.environ.get("SNAPSHOT_DIR", str(PROJECT_ROOT / "data"))
    default_db = Path(default_dir) / "account_tags.db"
    parser.add_argument("--db-path", type=Path, default=default_db)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    print("Tagging Workspace UX Verification")
    print("=" * 33)
    checks = _verify_database(args.db_path.expanduser().resolve())
    print("\nBehavior contracts")
    if args.skip_tests:
        print("- Focused tests skipped by explicit --skip-tests.")
    else:
        python = _pytest_python()
        checks.append(
            _status(
                python is not None,
                "Python test interpreter",
                str(python) if python else "no candidate can import pytest",
            )
        )
        if python is not None:
            checks.append(
                _run(
                    "backend tag storage/API tests",
                    [str(python), "-m", "pytest", "-q", *BACKEND_TESTS],
                    PROJECT_ROOT,
                )
            )
        frontend_root = PROJECT_ROOT / "graph-explorer"
        vitest = frontend_root / "node_modules/.bin/vitest"
        checks.append(
            _status(
                vitest.is_file(),
                "local frontend test runner",
                str(vitest) if vitest.is_file() else "run npm ci in graph-explorer",
            )
        )
        if vitest.is_file():
            checks.append(
                _run(
                    "operator-workspace UI tests",
                    [str(vitest), "run", "--reporter=dot", *FRONTEND_TESTS],
                    frontend_root,
                )
            )
    passed = sum(checks)
    print(f"\nResult: {passed}/{len(checks)} checks passed")
    print("Spend: $0; no network, external API, or model call is used.")
    print("Next steps:")
    if passed == len(checks):
        print("1. Reload Research Notes and review the centered tag workspace.")
        print("2. Add/retract one test tag and confirm IN/NOT IN plus Recent changes.")
        print("3. Save one tag meaning and confirm its earlier version remains visible.")
    else:
        print("1. Inspect the first ✗ and its command/output before restarting the app.")
        print("2. Do not migrate or replace the live tag DB to make this verifier green.")
    return 0 if passed == len(checks) else 1
if __name__ == "__main__":
    raise SystemExit(main())
