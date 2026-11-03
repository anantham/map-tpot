#!/usr/bin/env python3
"""Verify the task-focused curator Review shell without touching real judgments."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph-explorer"


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def contains(path: Path, *needles: str) -> bool:
    text = path.read_text()
    return all(needle in text for needle in needles)


def behavior_check() -> Check:
    node = os.environ.get("TPOT_NODE")
    vitest = GRAPH / "node_modules" / "vitest" / "vitest.mjs"
    if node:
        command = [node, str(vitest)]
    else:
        command = [str(GRAPH / "node_modules" / ".bin" / "vitest")]
    command += [
        "run",
        "src/App.researchNotes.test.jsx",
        "src/ResearchNotesInbox.test.jsx",
        "src/ResearchNotesInbox.disclosure.test.jsx",
        "src/researchNotes/TagSuggestions.test.jsx",
        "src/AccountTagPanel.test.jsx",
        "--reporter=dot",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=GRAPH,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check("Focused behavior", False, f"{type(exc).__name__}: {exc}")
    output = "\n".join((result.stdout, result.stderr))
    summary = next(
        (line.strip() for line in output.splitlines() if "Tests  " in line),
        f"exit={result.returncode}",
    )
    return Check("Focused behavior", result.returncode == 0, summary)


def contract_checks() -> list[Check]:
    nav = GRAPH / "src" / "AppNavigation.jsx"
    queue = GRAPH / "src" / "researchNotes" / "ResearchNotesQueuePanel.jsx"
    drawer = GRAPH / "src" / "researchNotes" / "AccountJudgmentDrawer.jsx"
    suggestions = GRAPH / "src" / "researchNotes" / "TagSuggestions.jsx"
    adr = ROOT / "docs" / "adr" / "023-task-focused-curator-review-and-map.md"
    scoped_files = [
        GRAPH / "src" / "App.jsx",
        nav,
        GRAPH / "src" / "ResearchNotesInbox.jsx",
        GRAPH / "src" / "ResearchNotesInbox.css",
        queue,
        GRAPH / "src" / "researchNotes" / "ResearchNotesQueuePanel.css",
        drawer,
        suggestions,
    ]
    sizes = {path.name: len(path.read_text().splitlines()) for path in scoped_files}
    return [
        Check(
            "Task-focused navigation",
            contains(nav, ">\n          Review\n", ">\n          Map\n", "role=\"menu\"", "Tools"),
            "Review and Map persist; legacy routes live in Tools",
        ),
        Check(
            "Progressive disclosure",
            contains(queue, "<details", "Quick add")
            and contains(drawer, "Account note", "How this workspace treats evidence")
            and contains(suggestions, "useState(false)"),
            "setup, capture, notes, provenance, and suggestions reveal on demand",
        ),
        Check(
            "Reusable judgment surface",
            contains(drawer, "AccountTagPanel", "WorkingTagImpact", "TagHistory"),
            "one component owns editable tags, consequences, and history",
        ),
        Check(
            "Schema boundary preserved",
            'type="range"' not in drawer.read_text(),
            "no unapproved probability or evidence-binding schema was introduced",
        ),
        Check(
            "Intent documentation",
            adr.is_file()
            and "ADR 023" in (ROOT / "docs" / "index.md").read_text(),
            "accepted first-slice boundary is indexed",
        ),
        Check(
            "Scoped file sizes",
            max(sizes.values()) < 300,
            f"lines={sizes}",
        ),
    ]


def main() -> int:
    print("Curator Review Shell Verification")
    print("=" * 40)
    checks = [*contract_checks(), behavior_check()]
    for check in checks:
        print(f"{'✓' if check.passed else '✗'} {check.name}: {check.detail}")
    failures = [check for check in checks if not check.passed]
    print("-" * 40)
    print(f"Checks: {len(checks)} | Passed: {len(checks) - len(failures)} | Failed: {len(failures)}")
    print("Writes: none; tests mock account-tag APIs and use browser test storage.")
    if failures:
        print("Next: fix the named contract before opening the UI against real curator data.")
        return 1
    print("Next: visually inspect Review at wide and narrow widths, then exercise one reversible tag edit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
