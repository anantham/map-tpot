#!/usr/bin/env python3
"""Human-readable, read-only verification of the Research Notes feedback loop."""
from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dev_runtime import DevRuntimeError, resolve_dev_runtime


def _check(label: str, passed: bool, detail: str) -> bool:
    print(f"{'✓' if passed else '✗'} {label}: {detail}")
    return passed


def _tag_counts(path: Path) -> tuple[int, int]:
    if not path.exists() or path.stat().st_size == 0:
        return 0, 0
    with sqlite3.connect(path) as conn:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        current = (
            conn.execute("SELECT COUNT(*) FROM account_tags").fetchone()[0]
            if "account_tags" in tables
            else 0
        )
        events = (
            conn.execute("SELECT COUNT(*) FROM account_tag_events").fetchone()[0]
            if "account_tag_events" in tables
            else 0
        )
    return int(current), int(events)


def _frontend_contract() -> tuple[bool, str]:
    result = subprocess.run(
        [
            "npx",
            "vitest",
            "run",
            "src/ResearchNotesInbox.test.jsx",
            "src/AccountTagPanel.test.jsx",
            "src/researchNotes/WorkingTagImpact.test.jsx",
            "src/researchNotes/researchNotesApi.test.js",
        ],
        cwd=PROJECT_ROOT / "graph-explorer",
        capture_output=True,
        text=True,
        timeout=60,
    )
    summary = next(
        (
            line.strip()
            for line in reversed(result.stdout.splitlines())
            if "Tests" in line and "passed" in line
        ),
        f"exit={result.returncode}",
    )
    return result.returncode == 0, summary


def verify(*, ego: str, tag: str) -> int:
    print("Research Notes feedback-loop verification")
    print("=" * 41)
    checks: list[bool] = []
    try:
        runtime = resolve_dev_runtime(PROJECT_ROOT)
    except DevRuntimeError as exc:
        _check("runtime", False, str(exc))
        print("Next: repair ./scripts/start_dev.sh --check, then rerun.")
        return 1

    token = "research-notes-flywheel-verifier"
    os.environ["ARCHIVE_DB_PATH"] = str(runtime.archive_db)
    os.environ["SNAPSHOT_DIR"] = str(runtime.snapshot_dir)
    os.environ["TPOT_CURATOR_TOKEN"] = token
    from src.api.server import create_app

    app = create_app({"TESTING": True})
    client = app.test_client()
    headers = {"X-TPOT-Curator-Token": token}
    before = _tag_counts(runtime.account_tags_db)

    source_response = client.get("/api/research-notes/source", headers=headers)
    source = source_response.get_json() or {}
    source_receipt = source.get("source") or {}
    suggestions = source.get("suggestionsByHandle") or {}
    suggestion_count = sum(len(rows) for rows in suggestions.values())
    source_text = source_receipt.get("text", "")
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    checks.append(_check(
        "Takes source",
        source_response.status_code == 200
        and source.get("configured") is True
        and len(suggestions) == 57
        and suggestion_count == 115,
        f"status={source_response.status_code}, handles={len(suggestions)}, "
        f"proposals={suggestion_count}",
    ))
    checks.append(_check(
        "source provenance/privacy",
        source_hash == source_receipt.get("sha256")
        and source_response.headers.get("Cache-Control") == "private, no-store"
        and all(
            row.get("proposalStatus") == "model-proposed"
            and row.get("goldStatus") == "not-gold"
            for rows in suggestions.values()
            for row in rows
        ),
        f"sha256={source_hash[:12]}…, cache=private/no-store, proposals=not-gold",
    ))

    query = urlencode({"ego": ego, "tag": tag, "limit": 20})
    frontier_response = client.get(
        f"/api/research-notes/frontier?{query}",
        headers=headers,
    )
    frontier = frontier_response.get_json() or {}
    semantics = frontier.get("semantics") or {}
    positive = frontier.get("anchors", {}).get("positive", {}).get("count", 0)
    negative = frontier.get("anchors", {}).get("negative", {}).get("count", 0)
    candidate_count = frontier.get("diagnostics", {}).get("candidateCount", 0)
    checks.append(_check(
        "exact-tag frontier",
        frontier_response.status_code == 200
        and frontier.get("target", {}).get("ego") == ego
        and frontier.get("target", {}).get("tagKey") == tag.casefold(),
        f"status={frontier.get('status')}, IN={positive}, NOT_IN={negative}, "
        f"candidates={candidate_count}",
    ))
    checks.append(_check(
        "honest score semantics",
        semantics.get("calibrated") is False
        and semantics.get("method") == "source_selectivity_contrast_v1"
        and "cluster exists" in semantics.get("statusMeaning", ""),
        "uncalibrated source-selectivity contrast; status is not cluster existence",
    ))

    frontend_ok, frontend_detail = _frontend_contract()
    checks.append(_check("browser contract tests", frontend_ok, frontend_detail))
    after = _tag_counts(runtime.account_tags_db)
    checks.append(_check(
        "read-only verifier",
        before == after,
        f"current/events stayed {before[0]}/{before[1]}",
    ))

    passed = sum(checks)
    print(f"\nResult: {passed}/{len(checks)} checks passed")
    print("Spend: $0; no external API or model call is part of this verifier.")
    if passed == len(checks):
        print(
            "Next: review one proposal in the UI; its IN/NOT IN write should "
            "refresh this exact-tag frontier and show the observed delta."
        )
        return 0
    print("Next: inspect the failed check before collecting a human judgment.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ego", default="adityaarpitha")
    parser.add_argument("--tag", default="neo-buddhist")
    args = parser.parse_args()
    try:
        import flask  # noqa: F401
    except ModuleNotFoundError:
        if os.environ.get("TPOT_FLYWHEEL_VERIFIER_REEXEC") == "1":
            print("✗ backend dependencies: Flask is unavailable", file=sys.stderr)
            return 1
        try:
            runtime = resolve_dev_runtime(PROJECT_ROOT)
        except DevRuntimeError as exc:
            print(f"✗ runtime: {exc}", file=sys.stderr)
            return 1
        candidates = [PROJECT_ROOT / ".venv" / "bin" / "python"]
        if runtime.primary_project_root is not None:
            candidates.append(
                runtime.primary_project_root / ".venv" / "bin" / "python"
            )
        interpreter = next((path for path in candidates if path.is_file()), None)
        if interpreter is None:
            print(
                "✗ backend dependencies: no project Python environment found",
                file=sys.stderr,
            )
            return 1
        child_env = dict(os.environ)
        child_env["TPOT_FLYWHEEL_VERIFIER_REEXEC"] = "1"
        return subprocess.run(
            [str(interpreter), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=PROJECT_ROOT,
            env=child_env,
            check=False,
        ).returncode
    return verify(ego=args.ego, tag=args.tag)


if __name__ == "__main__":
    raise SystemExit(main())
