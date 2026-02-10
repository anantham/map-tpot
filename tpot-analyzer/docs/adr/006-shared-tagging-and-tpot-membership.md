# ADR 006: Shared Tagging and Anchor-Conditioned TPOT Membership

- Status: Proposed
- Date: 2026-02-10
- Deciders: Human collaborator + computational peer
- Group: Data, API, UI/UX
- Related ADRs: 001-data-pipeline-architecture, 004-precomputed-graph-snapshots, 005-blob-storage-import

## Issue

The project needs a principled way to answer:

1. "Given selected TPOT exemplars, what is the likelihood this account belongs to that TPOT structure?"
2. "How do we continuously improve that estimate through human labeling from both graph exploration and in-feed browsing?"

Current implementation supports local account tagging and cluster labeling, but does not yet provide a shared labeling backend or a formal TPOT membership model.

## Context

Observed current state:

1. Account-level tag CRUD already exists in backend routes (`src/api/routes/accounts.py`) and UI (`graph-explorer/src/AccountTagPanel.jsx`).
2. Tag persistence is currently local SQLite (`src/data/account_tags.py`) scoped by `ego`, without shared workspace identity.
3. Cluster expansion scoring includes tag-aware logic, but hierarchy builder is not yet passing account tags into strategy evaluation (`node_tags=None` in `src/graph/hierarchy/builder.py`).
4. Graph coverage is incomplete and uneven; missing edges cannot be treated as negatives.
5. Product direction requires two complementary interaction surfaces:
   - Graph explorer for zoom, split, inspect, and label.
   - Chrome extension for low-friction account tagging while browsing feed context.

## Decision

Adopt a two-surface, shared-label architecture with anchor-conditioned membership scoring.

### 1) Separate but connected product surfaces

1. Keep "community navigation" and "membership learning" as distinct concerns.
2. Use both surfaces to write into one canonical label store.
3. Use those labels to train/update TPOT membership scoring.

### 2) Promote account tagging from local SQLite to shared storage

1. Introduce a shared tag store (Postgres/Supabase) with explicit multi-tenant scope.
2. Required tag dimensions:
   - `workspace_id`
   - `ego`
   - `account_id`
   - `tag_key` + `tag_display`
   - `polarity` (`in`/`not_in`)
   - `confidence`
   - `source` (`graph_ui`, `chrome_extension`, `import`)
   - `actor_id`
   - `created_at`, `updated_at`
3. Keep current API shape as compatibility layer where practical; add workspace-aware endpoints for canonical writes.

### 3) Formalize TPOT membership as anchor-conditioned probability

Define membership as:

`p_tpot(u | anchors) = sigmoid(w0 + w_graph * g_u + w_structure * s_u + w_text * t_u - w_missing * m_u)`

Where:
- `g_u`: graph proximity to selected TPOT anchors
- `s_u`: structural similarity in latent/spectral space
- `t_u`: text/profile/tag similarity (if available)
- `m_u`: missingness penalty from coverage/confidence

Modeling policy:
1. Require both positive anchors (in TPOT) and contrast anchors (not in TPOT) for stable boundaries.
2. Return both probability and confidence/uncertainty.
3. Treat absent edges as unknown, not evidence of non-membership.

### 4) Close the loop with active learning

1. Rank uncertain accounts for human labeling (high entropy / boundary proximity).
2. Re-train or re-calibrate scoring after accepted labels.
3. Feed accepted account tags into cluster split scoring by providing `node_tags` to hierarchy expansion.

### 5) Observability and verification

1. Every scoring run should log data coverage, label counts, and calibration metrics.
2. Add verification scripts for:
   - Label sync correctness (UI + extension -> shared store)
   - Membership score stability and uncertainty behavior
   - Cluster tag-signal integration effects

## Assumptions

1. Incomplete graph data is expected and persistent.
2. Label quality improves over time through iterative human review.
3. Users need interpretable output ("why this score?"), not just a scalar probability.
4. A shared DB is acceptable for collaboration workflows.

## Constraints

1. Backward compatibility with current local flows should be maintained during migration.
2. Label operations need low latency for extension UX.
3. Privacy and tenancy boundaries must be explicit before enabling shared labels.
4. Existing docs/workflows emphasize hypothesis-driven validation and human gates before architecture commits.

## Positions Considered

### Option A: Keep local SQLite labels only

- Pros: Lowest engineering effort.
- Cons: No collaboration, no extension sync across devices, no durable shared active learning.

### Option B: Extension writes directly to shared DB

- Pros: Fast initial extension path.
- Cons: Duplicated auth/data logic, weak governance, bypasses backend validation and logging.

### Option C (Selected): Shared backend API + shared DB + dual clients

- Pros: Single source of truth, consistent validation, traceable provenance, reusable for graph UI and extension.
- Cons: Requires auth/workspace design and migration effort.

## Consequences

### Positive

1. Unified labels from exploration and feed browsing.
2. Principled membership probability with explicit uncertainty.
3. Better cluster semantics through tag-informed split strategies.
4. Foundation for collaborative TPOT mapping.

### Negative / Risks

1. Additional complexity: auth, tenancy, conflict resolution.
2. Increased operational burden vs local SQLite.
3. Potential noisy labels unless moderation/consensus rules are set.

## Implementation Outline (Human-Gated)

1. Phase 0: Confirm product semantics (workspace ownership, visibility, conflict policy).
2. Phase 1: Shared label schema + backend endpoints + migration bridge from local tags.
3. Phase 2: Chrome extension writes to canonical API; graph UI reads/writes same source.
4. Phase 3: Anchor-conditioned TPOT scoring endpoint with uncertainty + explanation.
5. Phase 4: Active-learning queue and tag-aware hierarchy expansion integration.
6. Phase 5: Verification scripts + acceptance criteria for rollout.

## Open Questions (Blocking for Implementation)

1. Auth and tenancy: what identity provider and workspace model should be canonical?
2. Visibility: should labels be private-by-default, workspace-shared-by-default, or mixed per tag?
3. Conflict policy: when two users disagree on an account/tag, do we use last-write-wins, vote weighting, or explicit adjudication?
4. TPOT truth source: is TPOT membership a binary label, a continuous confidence score, or both?
5. Anchor UX: minimum required positive and negative anchors before scoring is shown?
6. Extension trust model: can extension writes be immediate, or must they be staged/reviewed?
7. Privacy boundary: what label metadata is safe to expose in shared views (actor, timestamp, notes)?
8. Rollout strategy: should shared mode be opt-in behind a feature flag while local SQLite remains default?

## Related Artifacts

1. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/src/api/routes/accounts.py`
2. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/src/data/account_tags.py`
3. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/src/graph/hierarchy/builder.py`
4. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/graph-explorer/src/AccountTagPanel.jsx`
5. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/docs/WORKLOG.md`
