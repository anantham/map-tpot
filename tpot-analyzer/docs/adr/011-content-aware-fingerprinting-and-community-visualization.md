# ADR 010: Content-Aware Account Fingerprinting and Community Visualization

- Status: Proposed
- Date: 2026-02-25
- Deciders: Human collaborator + computational peer
- Group: Graph math, data pipeline, UI/UX
- Related ADRs: 006-shared-tagging-and-tpot-membership, 007-observation-aware-clustering-membership,
  008-tweet-classification-account-fingerprinting, 009-labeling-dashboard-and-llm-eval-harness

---

## Issue

Once tweet-level classification is running (Phase 4 / ADR 008–009), we need a concrete
architecture for:

1. **Aggregating per-tweet scores → per-account fingerprint vectors** that replace the
   current graph-only node features.
2. **Rebuilding clustering** on those richer features so community boundaries reflect
   epistemic style rather than just who-follows-who.
3. **Visualizing communities** as overlapping soft membership zones (not hard clusters),
   with per-user customizable labels.

This ADR captures the decisions for Phases 5 and 6 of the roadmap.

---

## Context

### The fingerprinting opportunity

We will have (when Phase 4 completes):
- Per-tweet simulacrum distributions: `{l1, l2, l3, l4}` for all posted tweets
- Per-tweet lucidity scores: `[0.0–1.0]` for all posted tweets
- Same for liked tweets (passive aesthetic signal — 98% have full text, ~965K rows)
- Existing graph features: mutual ratio, degree, betweenness

The liked tweet signal is particularly important: **what people like reveals aesthetic
preference unfiltered by performance anxiety.** Two accounts can post very differently
but like the same high-lucidity L3 content — that's a community signal invisible to
graph structure or posted tweet analysis.

### The "any user can define communities" requirement

From the project vision: different users should be able to draw different community
boundaries over the same underlying structure. One analyst's "woo post-rat" is another's
"meditation adjacent rationalist." The system should not hardcode any labeling.

This is already partially solved:
- `AccountTagStore` supports per-ego tagging with polarity + confidence ✓
- `AccountMembershipPanel.jsx` shows GRF membership probability ✓
- GRF engine solves for membership given positive/negative anchor accounts ✓

What's missing: the GRF currently solves for binary TPOT/not-TPOT. It needs to extend
to multi-label soft scoring where each label is a user-defined community.

### The Venn diagram vision

The user wants to see overlapping communities — the "woo post-rats," "Buddhist folks,"
"EA," "e/acc," "alignment people," "anime pfp folks" — as overlapping regions, not
discrete boxes. An account can be "woo" at 0.7 and "EA" at 0.4 simultaneously.

This is a different visualization paradigm from the current hard-cluster force graph.

---

## Decision

### Layer 1: Account Fingerprint Vector

```python
account_fingerprint = np.concatenate([
    # Simulacrum distribution over POSTED tweets (normalized)
    [posted_l1_mean, posted_l2_mean, posted_l3_mean, posted_l4_mean],
    # Lucidity over posted tweets
    [posted_lucidity_mean, posted_lucidity_std],
    # Simulacrum distribution over LIKED tweets
    [liked_l1_mean, liked_l2_mean, liked_l3_mean, liked_l4_mean],
    # Lucidity over liked tweets
    [liked_lucidity_mean],
    # Graph features (existing, normalized)
    [mutual_ratio, log_degree_norm, betweenness_norm],
    # Optional: functional type distribution (aggression, dialectics, personal, etc.)
    # Added in later iteration when functional classification is stable
])
```

**Dimensionality:** ~16 features per account for the pilot. Grows with functional axis.

**Storage:** `account_fingerprints` table in `data/archive_tweets.db`:
```sql
CREATE TABLE account_fingerprints (
    account_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    vector_json TEXT NOT NULL,  -- JSON array of floats
    tweet_count INTEGER,
    liked_count INTEGER,
    computed_at TEXT NOT NULL,
    prompt_version TEXT NOT NULL  -- tracks which taxonomy version was used
);
```

**Script:** `scripts/build_fingerprints.py` — reads from `model_prediction_set`, aggregates,
writes to `account_fingerprints`. Re-runnable; new prompt versions produce new rows.

### Layer 2: Clustering on Content Fingerprints

Reuse the existing spectral pipeline with fingerprint vectors as node features:

1. Build cosine similarity matrix over account fingerprints (replaces adjacency-weighted graph)
2. Spectral embedding → mini-batch K-means micro-clusters (~50–100 for 334 accounts)
3. Ward linkage on micro-cluster centroids → dendrogram
4. Existing hierarchy + expansion engine unchanged — it operates on the dendrogram

**Graph edges still used** — but as a separate signal layer:
- Content similarity matrix defines embedding position
- Mutual follow edges define which accounts can "reach" each other in expansion

**Validation gate before switching defaults:**
- Compute ARI and VI comparing new clusters to held-out account labels (human tags)
- Content-aware clustering must score ≥ 0.05 ARI improvement over graph-only baseline
- If gate fails: investigate which features are adding noise; do not switch default

### Layer 3: Per-User Multi-Label Community Scoring

Extend the existing GRF engine from binary TPOT scoring to multi-label scoring:

```
User defines community "woo":
  → tags 10 positive exemplar accounts, 5 negative
  → GRF solves: P(woo | account) for all 334 accounts
  → Returns probability vector over accounts

Repeat for each user-defined community:
  "EA" → P(ea | account)
  "e/acc" → P(eacc | account)
  ...

Final community membership matrix:
  accounts × communities (each cell: probability 0–1)
```

The key extension: currently GRF takes `(ego, anchors)` and returns one binary score per
account. The extension adds a `tag` dimension — run GRF separately for each tag. Results
are cached per `(ego, tag, prompt_version)`.

**New API endpoints needed:**
```
GET /api/communities/{ego}/scores
  → {account_id: {community1: 0.7, community2: 0.4, ...}, ...}

GET /api/communities/{ego}/labels
  → list of user-defined community names

POST /api/communities/{ego}/labels/{tag}/recompute
  → triggers GRF solve for this tag, caches result
```

### Layer 4: Community Overlap Visualization

**MVP (Phase 6):** 2D scatterplot colored by dominant community, opacity = certainty.

```
x-axis: PC1 of account fingerprint (largest variance direction)
y-axis: PC2 of account fingerprint
color: dominant community (highest probability)
opacity: max community score (how confident)
size: tweet count (proxy for data coverage)
hover: account name, community scores, top tags
```

This makes TPOT's high-L3/high-lucidity cluster visible as a dense region, with
journalists and TPOT-adjacent accounts visible as a looser nearby cloud.

**Full Venn (later):** Requires stable communities. Use soft membership scores to draw
overlapping ellipses or voronoi regions. Not a standard visualization — likely custom
D3 or a force-directed layout with per-community "gravity wells."

**UI changes to graph-explorer:**
- New `CommunityMapView.jsx` component (2D scatter, distinct from force graph)
- `ClusterDetailsSidebar.jsx` updated: show community scores for selected account
- Settings: dropdown to switch active ego / community label set
- Current force-graph view preserved as "Graph View" tab; scatter as "Community View" tab

---

## Positions Considered

### Fingerprinting

**A. Use only posted tweets (ignore likes)**
- Simpler; fewer moving parts
- Loses the passive aesthetic signal — the most honest preference data we have
- Rejected: the liked tweet corpus is 98% complete and is free to score

**B. Merge posted + liked into one distribution**
- Simple representation
- Loses the distinction: performance mode vs. consumption mode are different
- Rejected: keep separate vectors, concat for clustering

**C. Use pre-trained embeddings (sentence-transformers) instead of LLM classification**
- Cheaper; no per-tweet API cost
- Captures topic similarity but not epistemic style (which is what TPOT cares about)
- Would not distinguish TPOT from TPOT-adjacent (the core failure mode)
- Rejected as primary; may be useful as an additional feature later

### Clustering

**A. Replace graph structure entirely with fingerprint similarity**
- Clean separation: content defines embedding, graph defines nothing
- Loses real signal: mutual follows DO indicate TPOT membership
- Rejected: use both, weighted

**B. Content similarity matrix + graph edges as separate signal (chosen)**
- Combines content-aware position with graph-aware connectivity
- Consistent with ADR 007 observation-aware architecture

**C. Learn a combined embedding via GNN**
- Most powerful; captures graph structure and content jointly
- Requires labeled training data we don't have yet
- Deferred to Phase 8 / research track

### Visualization

**A. Force-directed graph with community colors (current)**
- Already exists; familiar
- Doesn't show soft membership (hard clusters only)
- Keep as "Graph View" tab; don't replace

**B. 2D PCA/UMAP scatterplot (chosen for MVP)**
- Shows actual embedding geometry
- Opacity = certainty makes soft membership legible
- Fast to implement on top of existing fingerprint vectors

**C. Interactive Venn diagram**
- Most intuitive representation for overlapping communities
- Non-trivial to implement correctly for >3 communities
- Deferred: build after communities are stable and we know how many there are

---

## Assumptions

1. The account fingerprint has enough signal to cluster by epistemic style, not just topic.
   **This is the core bet.** Validate with the pilot before full implementation.
2. 334 accounts is enough for meaningful clustering (low N, but dense mutual links).
3. The liked tweet corpus (965K rows, 98% with full text) can be classified with the same
   pipeline as posted tweets at comparable accuracy.
4. GRF multi-label extension is a modest incremental change to the existing engine.

---

## Consequences

- **Phase 7 (generalization) is gated on this.** Content fingerprints are required to
  compare new accounts against known cluster centroids.
- **The force graph is not replaced** — it's complemented by the scatter view. Users who
  prefer graph navigation keep it.
- **ADR 011** will cover the lucidity axis integration into fingerprints (currently
  specified but not yet in the schema).
- **Prompt version tracking is critical.** Fingerprints computed from different prompt
  versions are not comparable. All downstream artifacts must carry `prompt_version`.
