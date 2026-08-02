#!/usr/bin/env python3
"""Verify the Research Notes thin slice without real data or network calls."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph-explorer"


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 60,
) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    combined = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )
    tail = " | ".join(combined.splitlines()[-3:])
    return result.returncode == 0, tail or f"exit={result.returncode}"


def _frontend_check() -> Check:
    vitest = GRAPH / "node_modules" / ".bin" / "vitest"
    if not vitest.is_file():
        return Check(
            "Frontend behavior",
            False,
            f"missing local Vitest binary: {vitest}",
        )
    passed, detail = _run(
        [
            str(vitest),
            "run",
            "--configLoader",
            "runner",
            "src/researchNotes/parseResearchNotes.test.js",
            "src/researchNotes/researchNotesApi.test.js",
            "src/researchNotes/RawDossier.test.jsx",
            "src/accountsApi.test.js",
            "src/accountTagsApi.test.js",
            "src/data.membership.test.js",
            "src/AccountTagPanel.test.jsx",
            "src/communityGoldApi.test.js",
            "src/ResearchNotesInbox.test.jsx",
            "src/App.researchNotes.test.jsx",
        ],
        cwd=GRAPH,
    )
    return Check("Frontend behavior", passed, detail)


def _takes_snapshot_check(path: Path, expected_count: int | None) -> Check:
    if not path.is_file():
        return Check("Takes snapshot", False, f"missing input file: {path}")

    probe = """
import crypto from 'node:crypto'
import fs from 'node:fs'
import { parseResearchNotes } from './graph-explorer/src/researchNotes/parseResearchNotes.js'

const path = process.argv[1]
const expected = process.argv[2] ? Number(process.argv[2]) : null
const text = fs.readFileSync(path, 'utf8')
const rows = parseResearchNotes(text)
const falseSubjects = ['cisco', 'ai4bharat'].filter((handle) =>
  rows.some((row) => row.normalizedHandle === handle))
const spanErrors = rows.filter((row) =>
  row.sourceText !== text.slice(row.sourceStart, row.sourceEnd)).length
const requiredMissing = ['meaningaligned', 'chrislakin'].filter((handle) =>
  !rows.some((row) => row.normalizedHandle === handle))
const metrics = {
  sha256: crypto.createHash('sha256').update(text).digest('hex'),
  bytes: Buffer.byteLength(text),
  subjects: rows.length,
  falseSubjects,
  spanErrors,
  requiredMissing,
}
console.log(JSON.stringify(metrics))
const countMatches = expected === null || rows.length === expected
if (!countMatches || falseSubjects.length || spanErrors || requiredMissing.length) process.exit(1)
""".strip()
    command = ["node", "--input-type=module", "-e", probe, str(path)]
    if expected_count is not None:
        command.append(str(expected_count))
    passed, detail = _run(command, cwd=ROOT)
    return Check("Takes snapshot", passed, detail)


def _backend_check() -> Check:
    passed, detail = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_research_notes_routes.py",
            "tests/test_account_tags_store.py",
            "tests/test_accounts_search_teleport_tags.py",
            "tests/test_cluster_tag_summary.py",
            "tests/test_cluster_membership_endpoint.py",
            "tests/test_curator_auth.py",
            "tests/test_community_gold_integrity_routes.py",
            "tests/test_community_gold_routes.py",
            "-q",
        ],
        cwd=ROOT,
    )
    return Check("Synthetic backend and auth", passed, detail)


def _contract_checks() -> list[Check]:
    route = (ROOT / "src/api/routes/research_notes.py").read_text()
    dossier = (
        GRAPH / "src/researchNotes/RawDossier.jsx"
    ).read_text()
    hook = (
        GRAPH / "src/researchNotes/useResearchNotesInbox.js"
    ).read_text()
    inbox = (GRAPH / "src/ResearchNotesInbox.jsx").read_text()
    account_tags = (GRAPH / "src/AccountTagPanel.jsx").read_text()
    accounts_api = (GRAPH / "src/accountsApi.js").read_text()
    tag_route = (ROOT / "src/api/routes/account_tags.py").read_text()
    tag_schema = (ROOT / "src/data/account_tag_schema.py").read_text()
    app = (GRAPH / "src/App.jsx").read_text()
    forbidden = (
        "canonicalMembership",
        "tpot_score",
        "previewCommunities",
        "legacy score",
    )
    leaks = [token for token in forbidden if token in route or token in dossier]
    return [
        Check(
            "Blind dossier allowlist",
            not leaks,
            f"forbidden markers={leaks or 'none'}",
        ),
        Check(
            "Working tags use the existing durable surface",
            "recordStudyJudgment" not in hook
            and "AccountTagPanel" in inbox
            and "account={identity.account}" in inbox
            and "Account tags" in account_tags,
            "evidence review composes the existing ego-scoped tag editor",
        ),
        Check(
            "False binding is rejected",
            "frame-bound dossiers are not implemented" in route
            and "bindingStatus" in route
            and '"unbound"' in route,
            "frameId cannot relabel mutable rows as frozen evidence",
        ),
        Check(
            "Staleness is visible",
            '"source": "mutable_local_archive"' in route
            and '"snapshotBound": False' in route
            and '"fetchedAt"' in route
            and "not snapshot-bound" in dossier
            and "provenance.snapshotBound === false" in dossier
            and "Captured" in dossier,
            "source, snapshot status, and capture times are rendered",
        ),
        Check(
            "No intensional definition is required",
            "studyConfig" not in hook
            and "targetQuestion" not in inbox
            and "Provisional boundary probes" not in inbox
            and "No first-principles definition is required" in inbox,
            "the working category is defined extensionally by tagged accounts",
        ),
        Check(
            "Model state is provenance-honest",
            "no target-scoped prediction" in inbox
            and "Legacy NMF percentages are intentionally not shown" in inbox
            and "not disagreement-ranked" in inbox,
            "manual order is explicit until comparable predictions exist",
        ),
        Check(
            "Investigation notes are account keyed",
            "drafts[selectedKey]" in hook
            and "setNote" in hook
            and "setProbeJudgment" not in hook,
            "session notes survive account navigation without recreating probes",
        ),
        Check(
            "Unresolved accounts cannot write tags",
            "handle:${selectedItem.normalizedHandle}" not in inbox
            and "Tagging stays locked until retry resolves a stable archive account ID." in inbox
            and "Open @{inbox.selectedItem.handle} on X" in inbox,
            "investigation stays available while writes wait for a durable archive ID",
        ),
        Check(
            "Working tags are curator-private",
            accounts_api.count("withCuratorAuth") >= 5,
            "tag reads, writes, removal, and vocabulary requests carry curator auth",
        ),
        Check(
            "Working-tag provenance fails closed",
            "CURATION_SOURCE_HEADER" in accounts_api
            and "human_curator_api" in accounts_api
            and "is required for tag mutations" in tag_route
            and "evidence_binding_status" in tag_schema,
            "human UI, verification, and unbound evidence remain distinguishable",
        ),
        Check(
            "App route is mounted",
            "'research-notes'" in app
            and "ResearchNotesInbox" in app
            and "accountStatus.valid ? accountStatus.handle : ''" in app,
            "?view=research-notes receives only the validated ego handle",
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--takes-file",
        type=Path,
        help="optional private takes snapshot to parse without copying it into the repo",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        help="optional expected subject count for --takes-file",
    )
    args = parser.parse_args()
    if args.expected_count is not None and args.takes_file is None:
        parser.error("--expected-count requires --takes-file")

    print("Research Notes Inbox Verification")
    print("=" * 44)
    checks = [_backend_check(), _frontend_check(), *_contract_checks()]
    if args.takes_file is not None:
        checks.append(_takes_snapshot_check(args.takes_file, args.expected_count))
    for check in checks:
        print(f"{'✓' if check.passed else '✗'} {check.name}: {check.detail}")
    failures = [check for check in checks if not check.passed]
    scoped_files = [
        ROOT / "src/api/routes/research_notes.py",
        ROOT / "src/api/routes/account_tags.py",
        ROOT / "src/data/account_tags.py",
        ROOT / "tests/test_research_notes_routes.py",
        GRAPH / "src/ResearchNotesInbox.jsx",
        GRAPH / "src/AccountTagPanel.jsx",
        GRAPH / "src/researchNotes/useResearchNotesInbox.js",
    ]
    sizes = {path.name: len(path.read_text().splitlines()) for path in scoped_files}
    print("-" * 44)
    print(
        f"Checks: {len(checks)} | "
        f"Passed: {len(checks) - len(failures)} | Failed: {len(failures)}"
    )
    print(f"Metrics: file_lines={sizes}")
    print(
        "Boundary: tests use temporary SQLite; a supplied takes file is read-only "
        "and is never copied into the repo. Frontend checks mock all API writes; "
        "no real tag, acquisition call, or external request occurs."
    )
    if failures:
        print("Next: inspect the named failed contract before opening real data.")
        return 1
    print(
        "Next: review real accounts in the manual queue, build the working tag "
        "extension, then freeze a version before evaluating model retrieval."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
