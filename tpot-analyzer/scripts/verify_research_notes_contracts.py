"""Static source contracts for the Research Notes human verifier."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph-explorer"

FRONTEND_CASES = (
    'src/researchNotes/SharedFollowingPanel.test.jsx',
    'src/researchNotes/RecoveryChannelComparison.test.jsx',
    'src/researchNotes/SeedRecoveryPanel.test.jsx',
    'src/researchNotes/FollowingRoster.test.jsx',
    'src/researchNotes/FollowingRosterApi.test.js',
    'src/researchNotes/FollowingEvidenceCoverage.test.jsx',
    'src/ResearchNotesInbox.following.test.jsx',
    'src/researchNotes/parseResearchNotes.test.js',
    'src/researchNotes/researchNotesApi.test.js',
    'src/researchNotes/RawDossier.test.jsx',
    'src/researchNotes/AccountContactCard.test.jsx',
    'src/researchNotes/PersonCardMatches.test.jsx',
    'src/researchNotes/ShadowNeighborhood.test.jsx',
    'src/researchNotes/ShadowSearch.test.jsx',
    'src/researchNotes/ShadowSearchRanking.test.jsx',
    'src/researchNotes/SavedApiPost.test.jsx',
    'src/researchNotes/SavedApiPaths.test.jsx',
    'src/researchNotes/CachedWebsiteEvidence.test.jsx',
    'src/researchNotes/JoinedEvidence.test.jsx',
    'src/researchNotes/RelationshipEvidence.test.jsx',
    'src/researchNotes/SavedEvidenceSearch.test.jsx',
    'src/researchNotes/StoredPostText.test.jsx',
    'src/researchNotes/UnifiedSearch.test.jsx',
    'src/researchNotes/UnifiedAlternatives.test.jsx',
    'src/researchNotes/UnifiedHistorical.test.jsx',
    'src/researchNotes/PageContactClues.test.jsx',
    'src/researchNotes/EncodedPageEmails.test.jsx',
    'src/researchNotes/SavedChannelMentions.test.jsx',
    'src/researchNotes/ChannelLookup.test.jsx',
    'src/researchNotes/SavedFollowSearch.test.jsx',
    'src/researchNotes/PostSearch.test.jsx',
    'src/researchNotes/PostInteractionSearch.test.jsx',
    'src/researchNotes/PostTagDiscovery.test.jsx',
    'src/researchNotes/WorkingTagImpact.test.jsx',
    'src/accountsApi.test.js',
    'src/accountTagsApi.test.js',
    'src/data.membership.test.js',
    'src/AccountTagPanel.test.jsx',
    'src/communityGoldApi.test.js',
    'src/ResearchNotesInbox.test.jsx',
    'src/ResearchNotesInbox.search.test.jsx',
    'src/ResearchNotesInbox.tagging.test.jsx',
    'src/ResearchNotesInbox.persistence.test.jsx',
    'src/ResearchNotesInbox.disclosure.test.jsx',
    'src/App.researchNotes.test.jsx',
)

BACKEND_CASES = (
    'tests/test_graph_imports.py',
    'tests/test_shared_following_review.py',
    'tests/test_cofollow_recovery.py',
    'tests/test_historical_handle_recovery.py',
    'tests/test_seed_recovery_references.py',
    'tests/test_following_evidence_coverage.py',
    'tests/test_research_notes_routes.py',
    'tests/test_research_notes_cache_policy.py',
    'tests/test_joined_dossier_routes.py',
    'tests/test_contact_card_routes.py',
    'tests/test_contact_card.py',
    'tests/test_person_card_candidates.py',
    'tests/test_person_card_profile_candidates.py',
    'tests/test_person_card_bio_candidates.py',
    'tests/test_contact_matches.py',
    'tests/test_website_context.py',
    'tests/test_website_context_cloudflare.py',
    'tests/test_public_page_claims.py',
    'tests/test_cached_websites.py',
    'tests/test_cached_website_routes.py',
    'tests/test_cached_website_graph.py',
    'tests/test_cached_website_batch.py',
    'tests/test_publisher_link_graph.py',
    'tests/test_profile_bio_links.py',
    'tests/test_bio_url_mentions.py',
    'tests/test_shadow_bio_links.py',
    'tests/test_bio_links.py',
    'tests/test_saved_provider_profiles.py',
    'tests/test_provider_evidence_batch.py',
    'tests/test_cached_website_graph_routes.py',
    'tests/test_cached_website_refresh.py',
    'tests/test_relationship_dossier.py',
    'tests/test_map_relationship_pilot.py',
    'tests/test_saved_evidence.py',
    'tests/test_saved_work_repair.py',
    'tests/test_saved_work_sources.py',
    'tests/test_research_source_links.py',
    'tests/test_qualified_research_sources.py',
    'tests/test_research_witness_sources.py',
    'tests/test_saved_evidence_text.py',
    'tests/test_stored_post_text.py',
    'tests/test_unified_evidence.py',
    'tests/test_unified_alternatives.py',
    'tests/test_unified_historical.py',
    'tests/test_page_contact_clues.py',
    'tests/test_page_contact_clues_encoded.py',
    'tests/test_saved_contacts.py',
    'tests/test_contact_catalog.py',
    'tests/test_channel_lookup.py',
    'tests/test_channel_lookup_bio.py',
    'tests/test_profile_contact_clues.py',
    'tests/test_saved_follow_paths.py',
    'tests/test_shadow_follow_import.py',
    'tests/test_shadow_aliases.py',
    'tests/test_shadow_row_batches.py',
    'tests/test_shadow_alias_routes.py',
    'tests/test_shadow_search.py',
    'tests/test_shadow_word_ranking.py',
    'tests/test_shadow_profile_counts.py',
    'tests/test_saved_api_posts.py',
    'tests/test_saved_api_timeline.py',
    'tests/test_saved_thread_posts.py',
    'tests/test_saved_api_paths.py',
    'tests/test_map_data_sources.py',
    'tests/test_map_interactions.py',
    'tests/test_published_profiles.py',
    'tests/test_published_profile_access.py',
    'tests/test_post_search.py',
    'tests/test_post_interactions.py',
    'tests/test_post_interaction_routes.py',
    'tests/test_post_tag_frontier.py',
    'tests/test_post_tag_content.py',
    'tests/test_archive_refresh.py',
    'tests/test_public_archive_dossier.py',
    'tests/test_account_tags_store.py',
    'tests/test_accounts_search_teleport_tags.py',
    'tests/test_cluster_tag_summary.py',
    'tests/test_cluster_membership_endpoint.py',
    'tests/test_curator_auth.py',
    'tests/test_community_gold_integrity_routes.py',
    'tests/test_community_gold_routes.py',
)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def contract_checks() -> list[Check]:
    route = (ROOT / "src/api/routes/research_notes.py").read_text()
    reader = (ROOT / "src/data/archive_dossier.py").read_text()
    dossier = (GRAPH / "src/researchNotes/RawDossier.jsx").read_text()
    hook = (GRAPH / "src/researchNotes/useResearchNotesInbox.js").read_text()
    inbox = (GRAPH / "src/ResearchNotesInbox.jsx").read_text()
    drawer = (GRAPH / "src/researchNotes/AccountJudgmentDrawer.jsx").read_text()
    queue = (GRAPH / "src/researchNotes/ResearchNotesQueuePanel.jsx").read_text()
    account_tags = (GRAPH / "src/AccountTagPanel.jsx").read_text()
    accounts_api = (GRAPH / "src/accountsApi.js").read_text()
    tag_route = (ROOT / "src/api/routes/account_tags.py").read_text()
    tag_source = (ROOT / "src/api/curation_source.py").read_text()
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
            and "AccountTagPanel" in drawer
            and "account={identity.account}" in drawer
            and "Current tags for" in account_tags,
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
            and '"fetchedAt"' in reader
            and "not snapshot-bound" in dossier
            and "provenance.snapshotBound === false" in dossier
            and "Captured" in dossier,
            "source, snapshot status, and capture times are rendered",
        ),
        Check(
            "No intensional definition is required",
            "studyConfig" not in hook
            and "targetQuestion" not in inbox
            and "Provisional boundary probes" not in drawer
            and "AccountTagPanel" in drawer,
            "the working category is defined extensionally by tagged accounts",
        ),
        Check(
            "Model state is provenance-honest",
            "Model suggestions do nothing until you accept them" in drawer
            and "frozen study snapshots" in drawer
            and "not disagreement-ranked" in queue,
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
            and "Tagging stays locked until retry resolves a stable archive account ID." in drawer
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
            and "require_curation_source(request)" in tag_route
            and "is required for curator mutations" in tag_source
            and "source not in ALLOWED_CURATION_SOURCES" in tag_source
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
