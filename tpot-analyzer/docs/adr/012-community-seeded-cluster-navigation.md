# ADR 012: Community-Seeded Cluster Navigation with Soft Membership Propagation

- Status: Proposed
- Date: 2026-02-26
- Deciders: Human collaborator + computational peer
- Group: Graph math, API, UI/UX
- Related ADRs: 001-spectral-clustering-visualization, 006-shared-tagging-and-tpot-membership,
  007-observation-aware-clustering-membership, 011-content-aware-fingerprinting-and-community-visualization

---

## Issue

ClusterView and Communities are two disconnected systems operating on the same graph.
ClusterView provides hierarchical spectral navigation (algorithmic, unlabeled).
Communities provides 14 human-curated semantic groups (623 accounts, named, colored).
The remaining ~7400 accounts ("shadow nodes") have no community assignment.

Users want a unified view: start with the 14 named communities as top-level nodes, zoom
in to see sub-communities within each, zoom out to see shadow nodes organized by their
relationship to the named communities. Community colors and labels should flow through
every zoom level.

The naive approach — harmonic label propagation from 14 seeds — has known failure modes:
seed errors propagate, directionality is lost in symmetrization, large communities
dominate, and forcing every node into 14 labels creates false certainty. This ADR
addresses each of these risks with specific mitigations.

---

## Context

### What we have

1. **Follow graph**: ~8000 accounts, ~400K directed edges, stored in parquet snapshots.
2. **Spectral embedding**: 30-dim from normalized Laplacian eigenvectors (`graph_snapshot.spectral.npz`).
3. **Ward dendrogram**: hierarchical clustering over the spectral embedding.
4. **Louvain communities**: hard partition, precomputed (`graph_snapshot.louvain.json`).
5. **14 curated communities**: stored in `archive_tweets.db` with NMF-derived soft weights
   (0-1 per account per community), human-editable names/colors/descriptions.
6. **GRF solver**: `membership_grf.py` implements harmonic-label propagation with
   regularization and uncertainty output. Currently binary (positive/negative anchors).
7. **Observation model**: ADR 007 defines IPW-weighted adjacency for incomplete graphs.

### What's missing

1. Multi-label extension of GRF (currently binary, needs 15-class: 14 communities + "none").
2. Directed propagation (GRF symmetrizes adjacency, losing follow direction).
3. Class balancing to prevent large-community dominance.
4. Explicit "unknown/abstain" class with uncertainty gating.
5. Community-aware dendrogram (current hierarchy ignores community labels entirely).
6. Frontend integration (ClusterView has no concept of community membership).

### Key tension

The 14 communities are a curator's interpretation — subjective, evolving, potentially
wrong. The spectral hierarchy is algorithmic — objective, stable, but meaningless without
labels. The integration must treat communities as **informative priors, not ground truth**,
and must surface uncertainty honestly when propagation is unreliable.

---

## Decision

Adopt a **three-layer architecture** that keeps communities and spectral structure as
separate signals, fused at display time with explicit uncertainty:

### Layer 1: Multi-Label Soft Propagation (Backend, Offline)

Extend the existing GRF solver from binary to K+1 classes (14 communities + "none").

**Mathematical formulation:**

Partition nodes into labeled set L (623) and unlabeled set U (~7400). For each
community c, define boundary conditions from NMF weights:

```
f_L^c(i) = mu_i^c          (known NMF membership, 0-1)
f_L^none(i) = 1 - sum_c mu_i^c   (residual = "none" probability)
```

Solve the harmonic system for all K+1 classes simultaneously:

```
f_U = -L_UU^{-1} * L_UL * f_L
```

where L is the graph Laplacian (see directionality decision below).

**Post-processing pipeline:**

1. **Class balancing**: Weight boundary conditions inversely by community size.
   `f_L_balanced^c(i) = mu_i^c / sqrt(|C_c|)`, then re-normalize rows to sum to 1.
   This prevents "Qualia Research Folks" (73 members) from dominating "AI Art" (4 members).

2. **Temperature scaling**: Apply `softmax(f / T)` row-wise with T > 1 (default T=2)
   to flatten winner-take-all dynamics. Tunable per session.

3. **Uncertainty computation**: For each unlabeled node, compute:
   - Entropy uncertainty: `H(f_i) = -sum_c f_i^c * log(f_i^c)`
   - Degree uncertainty: `1 / sqrt(degree_i + 1)` (low-degree = less evidence)
   - Combined: `u_i = w_entropy * H_i + w_degree * D_i` (existing GRF pattern)

4. **Abstain gate**: Nodes where `max(f_i) < 0.15` OR `u_i > 0.6` are classified
   as "genuinely unknown" — distinct from "weakly belongs to community X."

**Output**: `community_soft_memberships` table:
```sql
CREATE TABLE community_soft_memberships (
    account_id TEXT NOT NULL,
    community_id TEXT NOT NULL,         -- FK to community table, or '__none__'
    weight REAL NOT NULL,               -- 0.0-1.0 after balancing + temperature
    uncertainty REAL NOT NULL,           -- combined uncertainty
    abstain INTEGER NOT NULL DEFAULT 0,  -- 1 if below confidence threshold
    propagation_run TEXT NOT NULL,       -- version hash for cache invalidation
    computed_at TEXT NOT NULL,
    PRIMARY KEY (account_id, community_id, propagation_run)
);
```

**Re-propagation cost**: <1 second via conjugate gradient on sparse 7400x7400 system.
Triggered automatically when community assignments change in the curation UI.

### Layer 2: Community-Aware Spectral Embedding (Backend, Offline)

Inject community structure into the affinity matrix before eigendecomposition:

```
W' = (1 - alpha) * W_graph + alpha * (M * M^T)
```

where M is the 8000x15 soft membership matrix (from Layer 1), and alpha controls
community influence (default 0.15 — topology dominates, communities refine).

**Low-rank trick**: Never materialize the 8000x8000 M*M^T matrix. During Lanczos
iteration, compute `(M * M^T) * v = M * (M^T * v)` implicitly. Cost: O(n * K) per
matrix-vector product, where K=15.

The resulting spectral embedding and Ward dendrogram naturally respect community
boundaries without hard constraints. Communities that are topologically coherent
(most of them, since NMF was derived from graph signals) will produce clean
dendrogram sub-trees aligned with community labels.

**Validation gate** (before switching to community-aware embedding as default):
- Compute ARI between dendrogram cut at k=14 and known community labels.
- Community-aware embedding must score >= 0.05 ARI improvement over baseline.
- If gate fails: investigate alpha tuning or community label quality.

### Layer 3: Unified ClusterView Navigation (Frontend)

**Default initial state**: 14 community super-nodes + shadow group(s).

At each zoom level, nodes carry both their dendrogram identity (from spectral
hierarchy) and their community coloring (from soft membership). The dendrogram
controls structure; communities control appearance.

**Zoom semantics:**

| Level | What's Visible | Source of Structure | Source of Color |
|-------|---------------|--------------------|-----------------|
| Macro (default) | 14 community nodes + shadow blob(s) | Community assignments | Community colors |
| Meso (expand one) | 3-5 sub-clusters within that community | Spectral sub-tree cut | Parent community color, varying saturation by sub-cluster |
| Micro (expand further) | Individual account nodes | Leaf nodes | Blended color from full soft membership vector |

**Shadow node handling at macro level:**

Shadow nodes (those with `abstain=1` or `max(weight) < threshold`) are grouped by
spectral proximity into 3-8 satellite clusters using k-means on their spectral
coordinates. These appear as gray/muted nodes around the periphery, labeled
"Adjacent to [nearest community]" or left unlabeled.

Shadow nodes with non-trivial soft membership (`max(weight) >= threshold`,
`abstain=0`) are fractionally assigned: they appear as a smaller dot near
their dominant community, with opacity proportional to confidence.

**Expand behavior:**

When expanding a community node, use spectral sub-clustering (not member rings):
1. Extract the dendrogram sub-tree containing that community's members.
2. Cut at a level that produces 3-5 sub-clusters.
3. Include nearby shadow nodes that have significant soft membership in this community.
4. Sub-clusters inherit the parent community's color at reduced saturation.

**Collapse behavior:**

Collapsing merges sub-clusters back to the community super-node. All soft
membership information is preserved — only the display granularity changes.

---

## Risk Mitigations

### R1: Seed error propagation

**Risk**: Incorrect community assignments in the 14 seeds propagate to shadows,
creating self-confirming clusters that look coherent but are wrong.

**Mitigations:**
1. Regularization in GRF (existing): `L_UU + reg * I` biases toward prior, damping
   extreme propagation. Reg=1e-3 currently; may increase for conservative propagation.
2. Uncertainty surface: nodes with high entropy or low degree get visual uncertainty
   indicators in the UI (desaturated color, dashed border, "low confidence" tooltip).
3. Fast re-propagation: changing a seed re-solves in <1 sec. The curator can experiment
   freely — reassign an account, see how the shadow landscape shifts.
4. Active learning queue: rank high-uncertainty shadow nodes for human review. The
   curator labels the most ambiguous cases, which tightens boundaries.

### R2: Directionality loss

**Risk**: Symmetrizing the follow graph (`max(A, A^T)`) treats "I follow you" the
same as "you follow me", inflating hub influence and blurring asymmetric communities.

**Mitigation (phased):**

Phase 1 (now): Use symmetrized adjacency as-is. Document the limitation. For TPOT's
follow graph, reciprocity is high (~60-70% of edges are mutual), so the distortion
is bounded.

Phase 2 (future): Switch to directed random-walk Laplacian for propagation:
```
L_rw = I - D_out^{-1} * W
```
Information flows FROM who you follow TO you. This models "community membership
spreads through who you choose to listen to" rather than "who listens to you."

The GRF solver change is small (replace `_symmetrize_adjacency` with directed
normalization). The spectral embedding change is larger (directed Laplacian
eigenvectors are complex-valued; use the real part or switch to SVD-based embedding).

**Decision**: Phase 1 for initial implementation. Phase 2 after validating the
overall architecture works. The symmetrized version is a known-conservative
approximation, not a fundamental flaw.

### R3: Large community dominance

**Risk**: "Qualia Research Folks" (73 members, dense edges) absorbs neighboring
shadow nodes that should be "none" or weakly multi-community.

**Mitigations:**
1. Class-balanced boundary conditions (Layer 1, step 1): inverse-sqrt weighting.
2. Temperature scaling (Layer 1, step 2): T=2 flattens the distribution.
3. Explicit "none" class: the 15th label competes with all communities. Nodes
   far from all seeds naturally get high "none" probability.
4. Abstain gate: `max(weight) < 0.15` → hard "unknown", not weak community member.
5. Monitoring: log the community-size distribution of propagated labels. If any
   community absorbs >3x its seed size in shadows, flag for curator review.

### R4: False certainty (missing "none")

**Risk**: Every node gets forced into some community, including accounts that
genuinely don't belong to any TPOT sub-community.

**Mitigations:**
1. Explicit "none" class in the propagation (15th label, see Layer 1).
2. Abstain gate with two thresholds:
   - Confidence: `max(weight) < 0.15` → abstain
   - Margin: `max(weight) - second_max(weight) < 0.05` → ambiguous (display as multi-community)
3. UI: abstained nodes render as gray/translucent. They exist on the map but are
   explicitly marked as "uncategorized" — not invisible, not falsely assigned.
4. Tooltip for every node shows full membership vector + uncertainty score.

---

## Positions Considered

### Propagation method

**A. Harmonic function (GRF) — Selected**
- Pros: already implemented, fast (<1 sec), produces uncertainty, handles soft labels
- Cons: symmetrizes graph, no self-correction of seed errors
- Mitigations: class balancing, temperature, abstain gate, fast re-propagation

**B. Personalized PageRank (one per community)**
- Pros: respects direction natively, robust library support
- Cons: no "none" class without tricks, restart parameter conflates "uncertainty" with "prior"
- Verdict: good alternative for Phase 2 directed propagation

**C. Mixed Membership Stochastic Block Model (MMSB)**
- Pros: principled generative model, native soft+overlapping membership
- Cons: minutes to fit, complex tuning, overkill for 8000 nodes with 623 labels
- Verdict: reserve for offline validation (compare MMSB communities to propagated ones)

**D. Graph Neural Network (GCN)**
- Pros: can incorporate node features (bio, follower count) beyond graph structure
- Cons: 623 labels insufficient for training, overfitting risk
- Verdict: deferred to Phase 8 per ADR 011

### Dendrogram integration

**A. Modified affinity matrix (community-aware embedding) — Selected**
- Pros: clean, communities enter at the right abstraction level, standard eigendecomposition
- Cons: requires recomputing spectral embedding (one-time, ~10 sec)

**B. Constrained Ward linkage (must-link/cannot-link)**
- Pros: works on existing embedding, no recomputation
- Cons: custom merge loop, brittle hard constraints, tuning lambda is fiddly

**C. Post-hoc embedding nudge**
- Pros: instant, no recomputation
- Cons: not principled, can distort local geometry

**Decision**: A as primary, with C available as a fast preview mode for experimentation.

### Display integration

**A. Separate "Community mode" toggle**
- Pros: simple, no risk to existing ClusterView
- Cons: two disconnected views, no synergy

**B. Community colors as metadata overlay on spectral hierarchy — Selected**
- Pros: unified experience, community labels flow through all zoom levels
- Cons: more complex rendering, need to handle color blending for multi-community nodes

**C. Replace ClusterView entirely with community-first layout**
- Pros: simpler mental model
- Cons: loses the algorithmic hierarchy, which is valuable for discovering structure
  the curator hasn't labeled yet

---

## Assumptions

1. The 14 curated communities, while imperfect, are informative enough to seed
   propagation. The curator can iteratively improve them.
2. Reciprocity in the TPOT follow graph is high enough that symmetrization is
   an acceptable first approximation.
3. The GRF solver's existing regularization and uncertainty machinery transfers
   cleanly from binary to multi-class.
4. <1 second re-propagation is fast enough for interactive curation loops.
5. 623 labeled accounts provide sufficient boundary surface for propagation to
   ~7400 shadow nodes (ratio ~1:12, which is typical for semi-supervised methods).

---

## Constraints

1. Existing ClusterView API contract must remain backward-compatible.
   New data (soft memberships, community colors) is additive.
2. Re-propagation must not block the UI. Run async, cache results, serve stale
   while recomputing.
3. The "none" class must be a first-class citizen, not an afterthought.
   Nodes genuinely outside all 14 communities should be visually distinct
   from nodes with uncertain membership.
4. Community assignments in the curation UI (`community_account` table) remain
   the source of truth. Propagated memberships are derived and disposable.

---

## Consequences

### Positive

1. ClusterView gains semantic meaning at every zoom level (community names + colors).
2. Shadow nodes get interpretable soft placement relative to known communities.
3. Uncertainty is surfaced honestly — curator sees where propagation is confident
   and where it's guessing.
4. Fast re-propagation enables iterative curation: tweak seeds, see results, repeat.
5. The architecture extends naturally to per-user community definitions (ADR 011 Layer 3).

### Negative / Risks

1. Added complexity in the propagation pipeline (multi-class GRF, balancing, gating).
2. Two sources of cluster structure (dendrogram + communities) can conflict — need
   clear visual language for when they agree vs disagree.
3. Alpha/temperature/threshold tuning requires experimentation. Initial defaults
   may produce poor results for some community shapes.
4. Risk of curator over-trust: if propagated memberships look authoritative in the UI,
   curator may stop questioning them. Uncertainty display must be prominent, not hidden.

### Follow-up ADRs

- Directed propagation (Phase 2 of R2) may warrant its own ADR if the directed
  Laplacian changes the spectral embedding significantly.
- Active learning queue integration (ranking high-uncertainty shadows for labeling)
  connects to ADR 009's curation loop.

---

## Rollout Plan

### Phase 0: Validation Prototype (no UI changes)

1. Extend `membership_grf.py` to support multi-class (K+1) propagation.
2. Run on current 14 communities + follow graph.
3. Output: `community_soft_memberships` table + diagnostic report.
4. Diagnostic checks:
   - Distribution of "none" class (expect 40-60% of shadows).
   - Largest community absorption ratio (flag if >3x seed size).
   - Mean uncertainty by community (identify weak communities).
   - Comparison: propagated labels vs Louvain communities (ARI).
5. **Human gate**: Review diagnostic report before proceeding.
6. Verification: `scripts/verify_community_propagation.py`

### Phase 1: Community-Aware Embedding

1. Modify `scripts/build_spectral.py` to accept optional soft membership matrix.
2. Implement `W' = (1-alpha) * W + alpha * (M * M^T)` with low-rank trick.
3. Recompute spectral embedding + dendrogram.
4. Validation gate: ARI improvement >= 0.05 over baseline at k=14 cut.
5. **Human gate**: Compare old vs new dendrogram visually.
6. Verification: `scripts/verify_community_embedding.py`

### Phase 2: API Extension

1. New endpoint: `GET /api/clusters/community_memberships` — returns soft membership
   vectors for all accounts, with uncertainty and abstain flags.
2. Extend `GET /api/clusters` response with optional `community_coloring` field:
   per-cluster dominant community, color, confidence.
3. New endpoint: `POST /api/clusters/repropagate` — triggers re-propagation after
   community edits, returns job status.
4. Cache layer: propagation results cached by community-assignment hash.

### Phase 3: Frontend Integration

1. ClusterView default state: 14 community super-nodes + shadow satellites.
2. Community colors flow through all zoom levels.
3. Expand: spectral sub-clustering within community.
4. Uncertainty display: desaturation, tooltips, "low confidence" badges.
5. Settings: alpha slider, temperature slider, abstain threshold.

### Phase 4: Iterative Curation Loop

1. "Repropagate" button in Communities UI after edits.
2. High-uncertainty shadow nodes surfaced as "suggested for review."
3. Propagation diff: show what changed after a community edit.

---

## Open Questions (To Resolve Before Implementation)

1. **Class balancing formula**: inverse-sqrt vs inverse-linear vs learned weights?
   Start with inverse-sqrt, tune empirically.

2. **Temperature default**: T=2 is a guess. Need to experiment on actual data.
   Too high → everything looks uniform. Too low → winner-take-all.

3. **Abstain thresholds**: `max < 0.15` and `uncertainty > 0.6` are reasonable
   defaults but may need per-community tuning (strict for large communities,
   lenient for small ones).

4. **Shadow grouping at macro level**: How many satellite clusters? Fixed k=5?
   Or adaptive based on silhouette score? Or use Louvain on the shadow subgraph?

5. **Color blending for multi-community nodes**: Weighted average of community
   colors? Or show dominant community with a secondary-color ring? The former
   produces muddy colors; the latter is more legible but loses the "soft" feel.

6. **Interaction between community edits and dendrogram**: When communities change,
   do we recompute the full spectral embedding (expensive but principled) or only
   re-propagate soft labels (fast but dendrogram stays stale)? Suggest: re-propagate
   immediately, batch-recompute embedding nightly or on manual trigger.

7. **Directed propagation timeline**: Is the symmetrization distortion bad enough
   to prioritize Phase 2 of R2? Need empirical evidence — compare propagation
   results on symmetrized vs directed-random-walk Laplacian.

---

## Related Artifacts

1. `src/graph/membership_grf.py` — existing GRF solver (binary, to be extended)
2. `src/communities/store.py` — community CRUD and NMF membership storage
3. `src/api/routes/communities.py` — community REST endpoints
4. `src/api/cluster_routes.py` — cluster view API
5. `scripts/build_spectral.py` — spectral embedding pipeline
6. `graph-explorer/src/ClusterView.jsx` — frontend cluster navigation
7. `graph-explorer/src/Communities.jsx` — frontend community curation
8. `config/graph_settings.json` — feature flags for observation model
9. ADR 007 — observation-aware clustering (GRF membership engine = Phase 3)
10. ADR 011 — content-aware fingerprinting (multi-label GRF = Layer 3)
