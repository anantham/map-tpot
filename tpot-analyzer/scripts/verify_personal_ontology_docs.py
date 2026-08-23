#!/usr/bin/env python3
"""Verify the personal-ontology documentation slice without external I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from scripts._personal_ontology_adr_contracts import ADR_SEMANTIC_CONTRACTS


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FILES = {
    "vision": DOCS / "VISION.md",
    "publishing": DOCS / "product/2026-07-26-publishing-and-privacy-boundary.md",
    "adr21": DOCS / "adr/021-independent-overlapping-membership-and-evidence-semantics.md",
    "adr22": DOCS / "adr/022-budget-constrained-active-evidence-acquisition.md",
    "adr07": DOCS / "adr/007-observation-aware-clustering-membership.md",
    "adr11": DOCS / "adr/011-content-aware-fingerprinting-and-community-visualization.md",
    "adr12": DOCS / "adr/012-community-seeded-cluster-navigation.md",
    "adr13": DOCS / "adr/013-probabilistic-cluster-color-contract.md",
    "adr18": DOCS / "adr/018-propagation-engine-and-confidence.md",
    "pilot": DOCS / "experiments/2026-07-26-budgeted-personal-ontology-local-first-pilot.md",
    "methods": DOCS / "experiments/2026-07-26-personal-ontology-evaluation-methods.md",
    "plan": DOCS / "plans/2026-07-26-personal-ontology-active-discovery-implementation.md",
    "debt": DOCS / "plans/2026-07-26-personal-ontology-refactor-ledger.md",
    "index": DOCS / "index.md",
    "roadmap": DOCS / "ROADMAP.md",
    "worklog": DOCS / "WORKLOG.md",
    "graph": DOCS / "modules/graph.md",
    "about": ROOT / "public-site/src/About.jsx",
}
NEW_DOC_KEYS = ("publishing", "adr21", "adr22", "pilot", "methods", "plan", "debt")


def read(key: str) -> str:
    return FILES[key].read_text(encoding="utf-8")


def contains_all(text: str, needles: tuple[str, ...]) -> bool:
    normalized = " ".join(text.split())
    return all(" ".join(needle.split()) in normalized for needle in needles)


def run_checks() -> tuple[list[Check], dict[str, int]]:
    checks: list[Check] = []
    missing = [str(path.relative_to(ROOT)) for path in FILES.values() if not path.exists()]
    checks.append(Check("Required artifacts exist", not missing, "none missing" if not missing else ", ".join(missing)))
    if missing:
        return checks, {}

    line_counts = {key: len(read(key).splitlines()) for key in FILES}
    oversized = {key: line_counts[key] for key in NEW_DOC_KEYS if line_counts[key] >= 300}
    checks.append(
        Check(
            "New docs remain below 300 lines",
            not oversized,
            ", ".join(f"{key}={line_counts[key]}" for key in NEW_DOC_KEYS),
        )
    )

    adr_headings = ("## Issue", "## Decision", "## Assumptions", "## Falsifiers", "## Consequences")
    for key, number in (("adr21", "021"), ("adr22", "022")):
        text = read(key)
        ok = f"- Status: Accepted" in text and contains_all(text, adr_headings)
        checks.append(Check(f"ADR {number} decision record complete", ok, "Accepted + required sections" if ok else "status/section missing"))

    vision = read("vision")
    vision_ok = contains_all(
        vision,
        (
            "## Applied Mission",
            "## The Four-Part Evidence Architecture",
            "Group affinities overlap independently",
            "explicitly approved",
            "egress receipt",
        ),
    )
    stale_phrases = ("soft membership percentages", "All computation happens locally")
    stale_hits = [phrase for phrase in stale_phrases if phrase in vision]
    checks.append(Check("Vision matches evidence semantics", vision_ok and not stale_hits, f"stale phrases: {stale_hits or 'none'}"))

    publishing = read("publishing")
    publishing_ok = contains_all(
        publishing,
        (
            "independently overlapping values need not sum to one",
            "Current optional OpenRouter",
            "## Publication gate",
            "Private dossiers",
        ),
    )
    checks.append(Check("Publishing boundary is explicit", publishing_ok, "overlap, egress, gate, and local-only fields"))

    adr21 = read("adr21")
    target_ok = contains_all(
        adr21,
        (
            "publicly expressed participation interest",
            "They do not sum to",
            "coverage, provenance, freshness, and missingness metadata",
            "J_{u,\\mathrm{train}}^{<t}",
            "Use local SQLite for the pilot",
        ),
    )
    checks.append(Check("ADR 021 separates targets and coverage", target_ok, "affiliation/competence/interest/coverage contract"))

    adr22 = read("adr22")
    acquisition_ok = contains_all(
        adr22,
        (
            "development loss",
            "estimated knapsack",
            "randomization seed",
            "transmitted fields",
            "wrong-time",
            "scripts/active_learning.py",
        ),
    )
    checks.append(Check("ADR 022 prices typed, auditable actions", acquisition_ok, "risk reduction + receipts + temporal controls"))

    pilot = read("pilot")
    tranche_values = [
        int(value)
        for value in re.findall(
            r"^\| (?:Retrospective|Microtrial|Adaptive|Safety reserve) \| USD (\d+) \|",
            pilot,
            flags=re.MULTILINE,
        )
    ]
    budget_total = sum(tranche_values)
    pilot_ok = (
        "Status: Planned; no paid action authorized" in pilot
        and budget_total == 100
        and "Exactly 20%" in pilot
        and "## Frozen decision thresholds" in pilot
        and "sealed test opens once" in pilot
    )
    checks.append(Check("Pilot is bounded and falsifiable", pilot_ok, f"tranches={tranche_values}, total=USD {budget_total}"))

    methods = read("methods")
    methods_ok = contains_all(
        methods,
        (
            "## Frozen evaluation universe",
            "U_{\\mathrm{eval}}",
            "Every \\(U_{\\mathrm{eval}}\\) account has positive final-test inclusion probability",
            "never claim unconditional risk, all-\\(U_0\\) performance",
            "## Prospective expansion cohort",
            "Partition-specific inclusion probabilities",
            "**Policy panel:** a stratified probability sample",
            "drawn through the joint role allocation",
            "## Two one-use evaluation gates",
            "one joint randomized allocation",
            "selective risk versus retained coverage",
            "H1 is confirmatory only",
            "AUAC}_{11}",
            "anytime-valid confidence sequence",
            "routing-evaluation",
            "resample account clusters",
            "unspent safety margin",
        ),
    )
    checks.append(Check("Evaluation methods prevent reuse and sampling bias", methods_ok, "universe, panels, abstain, one-shot test, sequential rule"))

    plan = read("plan")
    missing_slices = [number for number in range(10) if f"## Slice {number} " not in plan]
    plan_ok = (
        not missing_slices
        and "Status: Slice 1 implemented" in plan
        and FILES["debt"].name in plan
        and "src/api/routes/community_gold.py" in plan
        and "No slice may make a remote call" in plan
        and "final sealed \\(U_{\\mathrm{eval}}\\) task-head test" in plan
    )
    checks.append(Check("Implementation plan has ten gated slices", plan_ok, f"missing slices: {missing_slices or 'none'}"))

    index = read("index")
    index_missing = [FILES[key].name for key in NEW_DOC_KEYS if FILES[key].name not in index]
    checks.append(Check("Docs index links new records", not index_missing, f"missing links: {index_missing or 'none'}"))

    roadmap = read("roadmap")
    roadmap_ok = contains_all(roadmap, ("ADR 021", "ADR 022", FILES["plan"].name, FILES["debt"].name))
    checks.append(Check("Roadmap tracks implementation and debt", roadmap_ok, "decisions, plan, and ledger referenced"))

    graph = read("graph")
    graph_ok = contains_all(
        graph,
        (
            "bounded graph affinities",
            "affinities are uncalibrated",
            "heuristic prioritization score",
            "otherwise `unknown`",
        ),
    )
    checks.append(Check("Graph methods separate affinity, uncertainty, and coverage", graph_ok, "GRF and IPW semantics"))

    for key, name, needles, detail in ADR_SEMANTIC_CONTRACTS:
        checks.append(Check(name, contains_all(read(key), needles), detail))

    about = read("about")
    about_ok = contains_all(
        about,
        (
            "heuristic, not a membership probability",
            "relative factor shares, not probabilities of belonging",
            "point-in-time legacy measurement",
            "Different producers use different",
            "Target-scoped anchors, cache keys, responses, and cross-target-isolation tests",
            "Planned Active Learning Loop",
        ),
    )
    stale_about = (
        "These memberships don&rsquo;t sum to one",
        "Confidence decays with distance",
        "The Active Learning Engine",
    )
    stale_about_hits = [phrase for phrase in stale_about if phrase in about]
    checks.append(
        Check(
            "About page states current score semantics",
            about_ok and not stale_about_hits,
            f"stale phrases: {stale_about_hits or 'none'}",
        )
    )

    adr18 = read("adr18")
    adr18_ok = contains_all(
        adr18,
        (
            "seed-holdout sensitivity range",
            "not a 95% confidence interval",
            "falsified the documented iteration plumbing",
        ),
    )
    checks.append(
        Check(
            "ADR 018 records propagation claim limits",
            adr18_ok,
            "affinity, rerun range, and solver falsifiers",
        )
    )

    worklog = read("worklog")
    worklog_ok = contains_all(
        worklog,
        (
            "Personal-Ontology Documentation Foundation",
            "Personal-Ontology Slice 1",
        ),
    )
    checks.append(Check("Worklog records this phase", worklog_ok, "Slice 0 and Slice 1 entries found" if worklog_ok else "phase entry missing"))
    return checks, line_counts


def main() -> int:
    checks, line_counts = run_checks()
    print("Personal-Ontology Documentation Verification")
    print("=" * 48)
    for check in checks:
        print(f"{'✓' if check.passed else '✗'} {check.name}: {check.detail}")

    failures = [check for check in checks if not check.passed]
    print("-" * 48)
    print(f"Checks: {len(checks)} | Passed: {len(checks) - len(failures)} | Failed: {len(failures)}")
    if line_counts:
        sample = ", ".join(f"{key}={line_counts[key]}" for key in NEW_DOC_KEYS)
        print(f"Metrics: line counts [{sample}]")
        print("Sample: ADR 021 target semantics → ADR 022 action policy → planned USD 100 pilot")

    print("Next steps:")
    if failures:
        print("1. Repair the named documentation contract failures.")
        print("2. Re-run this verifier; do not begin implementation or spend.")
        return 1
    print("1. Review the Slice 1 handoff before beginning the backend-neutral inference slice.")
    print("2. Keep paid actions blocked until Slices 2–5 and 7 plus the USD 10 entry gate pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
