#!/usr/bin/env python3
"""Verify that legacy community outputs are not presented as memberships."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "graph-explorer/src/Communities.jsx": (
        "Legacy Map Groups",
        "account placements",
        "formatLegacyScore(m.weight)",
        "formatLegacySource(m.source)",
    ),
    "graph-explorer/src/AccountDeepDive.jsx": (
        "Legacy Map Scores",
        "<LegacyMapNotice compact />",
        "Save Legacy Scores",
        "formatLegacySource(c.source)",
    ),
    "public-site/src/App.jsx": (
        "Explore a legacy map of TPOT affinities",
        "hypotheses, not membership probabilities",
        "Legacy groups shown:",
    ),
    "public-site/src/CommunityCard.jsx": (
        "relativeLegacyWidths",
        "width: `${bar.relativeWidth}%`",
        "{bar.score}",
    ),
    "public-site/src/EvidenceSummary.jsx": (
        "Highest displayed legacy affinity",
        "uncalibrated score {topBar.score}",
        "compare their ordering only",
        "Legacy-labeled accounts who follow this person",
    ),
    "public-site/src/CommunityPage.jsx": (
        "LegacyMapNotice",
        "legacy score {formatLegacyScore(member.weight)}",
    ),
    "public-site/src/CardGallery.jsx": ("LegacyMapNotice",),
    "public-site/src/styles.css": ("max-height: min(80vh, calc(100vh - 10rem))", '.card-fullscreen-center [role="note"]'),
    "public-site/src/shareText.js": (
        "legacy TPOT map ranks",
        "not membership probabilities",
    ),
    "public-site/api/og.js": (
        "Legacy exploratory map:",
        "not membership probabilities",
    ),
    "public-site/src/legacyCommunitySemantics.js": (
        "not membership probabilities",
        "relative within this card",
        "relativeLegacyWidths",
    ),
    "public-site/src/cardCanvas.js": (
        "MAX_CARD_SCORE_ROWS = 3",
        "selectTopLegacyScores",
        "buildAiCardTextLayout",
    ),
    "public-site/src/CardDownload.jsx": (
        "selectTopLegacyScores(bars)",
        "relativeWidth",
        "additional legacy scores",
        "NOT MEMBERSHIP PROBABILITIES",
    ),
    "public-site/src/cardDownloadAi.js": (
        "buildAiCardTextLayout",
        "additional legacy scores",
        "NOT MEMBERSHIP PROBABILITIES",
    ),
    "public-site/src/legacyCardPrompt.js": (
        "LEGACY EXPLORATORY AFFINITY RANK",
        "uncalibrated and not membership probabilities",
        "visual motifs",
    ),
    "public-site/api/_legacyCardPrompt.js": (
        "LEGACY EXPLORATORY AFFINITY RANK",
        "uncalibrated and not membership probabilities",
        "visual motifs",
    ),
    "public-site/src/GenerateCard.jsx": (
        'import { buildLegacyCardPrompt } from "./legacyCardPrompt"',
        "buildLegacyCardPrompt(cardRequest)",
    ),
    "public-site/api/generate-card.js": (
        'require("./_legacyCardPrompt")',
        "buildLegacyCardPrompt({",
    ),
}

MINIMUM_COUNTS = {
    ("public-site/src/CommunityCard.jsx", "<LegacyMapNotice"): 2,
    ("public-site/src/CardGallery.jsx", "<LegacyMapNotice"): 2,
}

FORBIDDEN = {
    "graph-explorer/src/Communities.jsx": (
        r"\(m\.weight\s*\*\s*100\).*%",
        r"['\"]No members['\"]",
        r"['\"]Loading members\.\.\.['\"]",
        r"\}\s+members\s*<",
        r"source\s*===\s*['\"]human['\"].*['\"]NMF['\"]",
    ),
    "graph-explorer/src/AccountDeepDive.jsx": (
        r"source\s*===\s*['\"]human['\"].*['\"]N['\"]",
        r"Save Weights",
    ),
    "public-site/src/App.jsx": (r"you belong to",),
    "public-site/src/CommunityCard.jsx": (
        r"width:\s*`\$\{bar\.pct\}%",
        r"Math\.round\([^)]*weight\s*\*\s*100",
    ),
    "public-site/src/EvidenceSummary.jsx": (
        r"score \{topBar\.pct\}%",
        r"pct:\s*Math\.round\([^)]*weight",
        r"TPOT Bridge Account",
        r"Connected to .* communities",
        r"Community members who follow",
    ),
    "public-site/src/CommunityPage.jsx": (r"weight \{member\.weight",),
    "public-site/src/shareText.js": (
        r"%",
        r"\bbelong(?:s)?\b",
        r"Find your ingroup",
    ),
    "public-site/api/og.js": (r"Math\.round\(c\.weight", r"\bbelong(?:s)?\b"),
    "public-site/src/CardDownload.jsx": (
        r"\bbar\.pct\b",
        r"weight\s*\*\s*100",
    ),
    "public-site/src/GenerateCard.jsx": (
        r"PRIMARY COMMUNITY",
        r"SECONDARY COMMUNITY",
        r"FEEL (?:the )?community membership",
        r"Math\.round\([^)]*weight\s*\*\s*100",
    ),
    "public-site/api/generate-card.js": (
        r"PRIMARY COMMUNITY",
        r"SECONDARY COMMUNITY",
        r"FEEL (?:the )?community membership",
        r"Math\.round\([^)]*weight\s*\*\s*100",
    ),
}

CONTRACT_SUITES = (
    (
        "public-site",
        (
            "src/legacyCommunitySemantics.test.js",
            "src/cardCanvas.test.js",
            "src/CommunityCard.semantics.test.jsx",
            "src/EvidenceSummary.test.jsx",
            "src/legacyCardPrompt.test.js",
            "src/App.homepage-semantics.test.jsx",
            "src/CardGallery.semantics.test.jsx",
            "__tests__/api/legacy-card-prompt.test.js",
            "__tests__/api/generate-card-prompt-semantics.test.js",
        ),
        (),
    ),
    (
        "graph-explorer",
        (
            "src/legacyCommunitySemantics.test.js",
            "src/AccountDeepDive.legacyScores.test.jsx",
            "src/Communities.truthfulness.test.jsx",
        ),
        ("--configLoader", "runner"),
    ),
)


def run_contract_suite(
    project: str,
    tests: tuple[str, ...],
    extra_args: tuple[str, ...],
) -> tuple[bool, int, str]:
    project_dir = ROOT / project
    vitest = project_dir / "node_modules/.bin/vitest"
    if not vitest.is_file():
        return False, 0, f"{project}: missing {vitest.relative_to(ROOT)}; run npm install"

    result = subprocess.run(
        [str(vitest), "run", *tests, *extra_args],
        cwd=project_dir,
        capture_output=True,
        check=False,
        text=True,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    match = re.search(r"Tests\s+(\d+) passed", combined)
    passed = int(match.group(1)) if match else 0
    if result.returncode == 0:
        return True, passed, f"{project}: {passed} executable contract tests passed"

    tail = "\n".join(combined.strip().splitlines()[-12:])
    return False, passed, f"{project}: contract suite failed\n{tail}"


def main() -> int:
    failures: list[str] = []
    checked_fragments = 0
    checked_patterns = 0

    print("Legacy community truthfulness verification")
    print(f"Repository: {ROOT}")
    print()

    source_text: dict[str, str] = {}
    for relative_path, fragments in REQUIRED.items():
        path = ROOT / relative_path
        if not path.is_file():
            failures.append(f"{relative_path}: file missing")
            print(f"✗ {relative_path}: file missing")
            continue

        text = path.read_text(encoding="utf-8")
        source_text[relative_path] = text
        missing = [fragment for fragment in fragments if fragment not in text]
        checked_fragments += len(fragments)
        if missing:
            failures.append(f"{relative_path}: missing required marker(s): {missing}")
            print(f"✗ {relative_path}: missing {len(missing)} required marker(s)")
        else:
            print(f"✓ {relative_path}: {len(fragments)} required marker(s)")

    for (relative_path, marker), minimum in MINIMUM_COUNTS.items():
        actual = source_text.get(relative_path, "").count(marker)
        checked_fragments += 1
        if actual < minimum:
            failures.append(
                f"{relative_path}: expected at least {minimum} occurrences of {marker!r}, got {actual}"
            )
            print(f"✗ {relative_path}: caveat occurs {actual}/{minimum} required times")
        else:
            print(f"✓ {relative_path}: caveat occurs {actual} times")

    print()
    for relative_path, patterns in FORBIDDEN.items():
        text = source_text.get(relative_path)
        if text is None:
            path = ROOT / relative_path
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
        matches = [pattern for pattern in patterns if re.search(pattern, text, re.I)]
        checked_patterns += len(patterns)
        if matches:
            failures.append(f"{relative_path}: forbidden claim pattern(s): {matches}")
            print(f"✗ {relative_path}: {len(matches)} misleading pattern(s) remain")
        else:
            print(f"✓ {relative_path}: no forbidden membership-like pattern")

    print()
    executable_tests = 0
    for project, tests, extra_args in CONTRACT_SUITES:
        passed, count, detail = run_contract_suite(project, tests, extra_args)
        executable_tests += count
        if passed:
            print(f"✓ {detail}")
        else:
            failures.append(detail)
            print(f"✗ {detail}")

    print()
    print(
        "Metrics: "
        f"{len(REQUIRED)} production surfaces, "
        f"{checked_fragments} required markers, "
        f"{checked_patterns} forbidden patterns, "
        f"{executable_tests} executable contract tests."
    )
    print(
        "Adversarial samples: score 73.3335, score 2, 15-score export, "
        "fullscreen cached art, and raw editor score 0.65."
    )

    if failures:
        print("\nNext steps:")
        for failure in failures:
            print(f"  - {failure}")
        print("  - Repair the surfaced contract, then rerun this verifier.")
        return 1

    print("\n✓ Legacy outputs are visibly quarantined as exploratory, uncalibrated evidence.")
    print("Next steps:")
    print("  - Keep this baseline separate from the raw-first retrieval study.")
    print("  - Hide the legacy artifact entirely if rank order is also rejected.")
    print("  - Do not call these values probabilities without held-out calibration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
