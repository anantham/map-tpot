"""Static source contracts for the Research Notes human verifier."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "graph-explorer"


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
