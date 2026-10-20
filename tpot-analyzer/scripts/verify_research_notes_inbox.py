#!/usr/bin/env python3
"""Verify the Research Notes thin slice without real data or network calls."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph-explorer"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_research_notes_contracts import Check, contract_checks

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
    if result.returncode != 0:
        descriptor, failure_path = tempfile.mkstemp(prefix='tpot-check-failure-',suffix='.log')
        with os.fdopen(descriptor,'w') as failure_log:failure_log.write(combined+'\n')
        tail += f' | Full failure output: {failure_path}'
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
            "--maxWorkers",
            "2",
            "src/researchNotes/parseResearchNotes.test.js",
            "src/researchNotes/researchNotesApi.test.js",
            "src/researchNotes/RawDossier.test.jsx",
            "src/researchNotes/AccountContactCard.test.jsx",
            "src/researchNotes/ShadowNeighborhood.test.jsx",
            "src/researchNotes/ShadowSearch.test.jsx",
            "src/researchNotes/ShadowSearchRanking.test.jsx",
            "src/researchNotes/SavedApiPost.test.jsx",
            "src/researchNotes/SavedApiPaths.test.jsx",
            "src/researchNotes/CachedWebsiteEvidence.test.jsx",
            "src/researchNotes/JoinedEvidence.test.jsx",
            "src/researchNotes/RelationshipEvidence.test.jsx",
            "src/researchNotes/SavedEvidenceSearch.test.jsx",
            "src/researchNotes/StoredPostText.test.jsx",
            "src/researchNotes/UnifiedSearch.test.jsx",
            "src/researchNotes/UnifiedHistorical.test.jsx",
            "src/researchNotes/PageContactClues.test.jsx",
            "src/researchNotes/SavedChannelMentions.test.jsx",
            "src/researchNotes/ChannelLookup.test.jsx",
            "src/researchNotes/SavedFollowSearch.test.jsx",
            "src/researchNotes/PostSearch.test.jsx",
            "src/researchNotes/PostInteractionSearch.test.jsx",
            "src/researchNotes/PostTagDiscovery.test.jsx",
            "src/researchNotes/WorkingTagImpact.test.jsx",
            "src/accountsApi.test.js",
            "src/accountTagsApi.test.js",
            "src/data.membership.test.js",
            "src/AccountTagPanel.test.jsx",
            "src/communityGoldApi.test.js",
            "src/ResearchNotesInbox.test.jsx",
            "src/ResearchNotesInbox.search.test.jsx",
            "src/ResearchNotesInbox.tagging.test.jsx",
            "src/ResearchNotesInbox.persistence.test.jsx",
            "src/ResearchNotesInbox.disclosure.test.jsx",
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
            "tests/test_joined_dossier_routes.py",
            "tests/test_contact_card_routes.py",
            "tests/test_contact_card.py",
            "tests/test_website_context.py",
            "tests/test_public_page_claims.py",
            "tests/test_cached_websites.py",
            "tests/test_cached_website_routes.py",
            "tests/test_cached_website_graph.py",
            "tests/test_cached_website_batch.py",
            "tests/test_publisher_link_graph.py",
            "tests/test_profile_bio_links.py",
            "tests/test_bio_url_mentions.py",
            "tests/test_shadow_bio_links.py",
            "tests/test_bio_links.py",
            "tests/test_saved_provider_profiles.py",
            "tests/test_provider_evidence_batch.py",
            "tests/test_cached_website_graph_routes.py",
            "tests/test_cached_website_refresh.py",
            "tests/test_relationship_dossier.py",
            "tests/test_map_relationship_pilot.py",
            "tests/test_saved_evidence.py",
            "tests/test_saved_work_repair.py",
            "tests/test_saved_work_sources.py",
            "tests/test_research_source_links.py",
            "tests/test_qualified_research_sources.py",
            "tests/test_research_witness_sources.py",
            "tests/test_saved_evidence_text.py",
            "tests/test_stored_post_text.py",
            "tests/test_unified_evidence.py",
            "tests/test_unified_historical.py",
            "tests/test_page_contact_clues.py",
            "tests/test_saved_contacts.py",
            "tests/test_contact_catalog.py",
            "tests/test_channel_lookup.py",
            "tests/test_saved_follow_paths.py",
            "tests/test_shadow_follow_import.py",
            "tests/test_shadow_aliases.py",
            "tests/test_shadow_row_batches.py",
            "tests/test_shadow_alias_routes.py",
            "tests/test_shadow_search.py",
            "tests/test_shadow_word_ranking.py",
            "tests/test_shadow_profile_counts.py",
            "tests/test_saved_api_posts.py",
            "tests/test_saved_api_timeline.py",
            "tests/test_saved_thread_posts.py",
            "tests/test_saved_api_paths.py",
            "tests/test_map_data_sources.py",
            "tests/test_map_interactions.py",
            "tests/test_published_profiles.py",
            "tests/test_published_profile_access.py",
            "tests/test_post_search.py",
            "tests/test_post_interactions.py",
            "tests/test_post_interaction_routes.py",
            "tests/test_post_tag_frontier.py",
            "tests/test_post_tag_content.py",
            "tests/test_archive_refresh.py",
            "tests/test_public_archive_dossier.py",
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
    checks = [_backend_check(), _frontend_check(), *contract_checks()]
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
        ROOT / "src/data/post_tag_frontier.py",
        ROOT / "src/data/cached_websites.py",
        ROOT / "src/enrichment/website_context.py",
        GRAPH / "src/researchNotes/CachedWebsiteEvidence.jsx",
        GRAPH / "src/researchNotes/WorkingTagImpact.jsx",
        ROOT / "src/data/shadow_search.py",
        ROOT / "src/data/shadow_profile_counts.py",
        ROOT / "src/data/page_contact_clues.py",
        ROOT / "src/data/contact_catalog.py",
        ROOT / "src/data/channel_lookup.py",
        ROOT / "src/data/research_source_links.py",
        ROOT / "src/data/contact_card.py",
        GRAPH / "src/researchNotes/AccountContactCard.jsx",
        GRAPH / "src/researchNotes/ChannelLookupResults.jsx",
        GRAPH / "src/researchNotes/SavedEvidenceMatches.jsx",
        ROOT / "src/data/unified_evidence.py",
        GRAPH / "src/researchNotes/UnifiedSearchResults.jsx",
        ROOT / "src/data/evidence_text.py",
        GRAPH / "src/researchNotes/ShadowSearchResults.jsx",
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
        "Next: open a Review dossier, inspect the active tag's candidates and "
        "source paths, then add/remove/retract tags normally. Freeze an extension "
        "only for a separate evaluation; these candidates are not confidence scores."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
