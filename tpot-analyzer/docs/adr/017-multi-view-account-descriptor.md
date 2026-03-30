# ADR 017: Multi-View Account Descriptor

**Status:** Proposed (session 12, 2026-03-29)
**Context:** EXP-008 showed follow-graph NMF and tweet-content clusters are nearly independent (AMI=0.08). A single-view prior (NMF alone) misses half the picture. ADR 016 called for "task-specific heads over multiple views" — this ADR specifies what those views are and how they combine.

---

## Decision

Each account is represented as a **multi-view descriptor** — a collection of independent signals that are combined only at decision time by task-specific heads.

### The Views

| View | Source | Dimensionality | Coverage |
|------|--------|---------------|----------|
| **Graph** | NMF community_account weights | 16 (one per community) | 932 seeds, propagated to 298K |
| **Semantic** | Tweet cluster histogram at k=8 | 8 (one per cluster) | 309 core accounts (growing) |
| **Taste** | Like cluster histogram at k=8 | 8 (one per cluster) | Future — needs liked tweets embedded |
| **Interaction** | Typed graph features (reciprocity, engagement partners, quote/reply patterns) | ~10 features | 298K (from TypedGraph) |
| **Profile** | Bio embedding | 768 | 15K (already computed) |

### Combination Strategy

**Per-view soft voting** (not concatenation + MLP):
- Each view independently predicts a community distribution
- A simple learned weight per view combines them
- ~4 weights per community = ~64 parameters total
- Calibratable with 330 gold labels without overfitting

Why not concatenation:
- 330 training examples, 800+ dimensions → severe overfitting
- Per-view voting is interpretable: "graph says X, content says Y"
- Graceful degradation: if a view is missing (graph-only accounts have no semantic view), remaining views still work

### Account Rings and View Availability

| Ring | Graph | Semantic | Taste | Interaction | Profile |
|------|-------|----------|-------|-------------|---------|
| Core (330) | Yes | Yes (after embedding) | Future | Yes | Most |
| Enriched (60) | Yes | Yes (API tweets) | Partial | Yes | Most |
| Profiled (9K) | Propagated | No | No | Some | Yes |
| Graph-only (298K) | Propagated | No | No | Minimal | No |

The ensemble prior naturally degrades: core accounts get 4+ views, graph-only accounts get 1 view. Confidence reflects this — more views = higher confidence.

## Rationale

### Evidence (EXP-008)

Follow graph and tweet content are orthogonal (AMI=0.08):
- Quiet-Creatives: content-coherent (purity 0.96 at k=2)
- Core-TPOT, highbies: content-diverse (scatter across all clusters)
- AI-Safety (by follows) members who tweet about contemplative practice = bridges invisible to single-view

### The NMF question

With 330+ labeled seeds approaching, NMF's role shifts from "discovers communities" to "one structural view among several." The ensemble prior subsumes NMF — it uses NMF as the graph view while adding content, taste, and interaction views.

NMF is retained because:
- It covers all 298K accounts (content views only cover ~300)
- It's fast to recompute
- Graph structure IS informative — just not sufficient alone

## Consequences

### Near-term (implementable now)
- Build `account_descriptor` as a JIT-computed view, not a stored table
- Graph view: query `community_account` weights
- Semantic view: query `account_cluster_histogram` at chosen k
- Interaction view: query TypedGraph for reciprocity, typed_degree, engagement partners
- Profile view: query bio embedding from `bio_embeddings` table
- Simple voting combiner: calibrated on 330 core accounts

### Medium-term
- Taste view: embed liked tweets in same basis as authored tweets, compute histograms
- Active learning head: predict value of buying more data using current descriptor confidence
- Confidence = number of views available + agreement across views

### What changes in the pipeline
- Seed insertion: weight = graph_view_weight * semantic_agreement_factor
- Propagation: still uses combined TypedGraph adjacency (unchanged)
- Export: confidence reflects multi-view agreement, not just graph position
- Active learning: prioritizes accounts where views disagree (high information value)

### What doesn't change
- Harmonic propagation solver
- TypedGraph combination
- LLM labeling prompt structure
- Public site frontend

## Assumptions
- 309 accounts with semantic view is enough to validate the approach
- Per-view voting won't overfit with 330 training examples
- Tweet cluster stability across re-runs (need to verify)

## Related
- ADR 016 — four-part epistemic architecture (this ADR implements the "task heads" layer)
- EXP-005 — NMF vs tweet labeling (42% agreement, first hint)
- EXP-008 — multi-scale clustering (AMI=0.08, formal confirmation)
- EXP-001 — higher-k NMF can't find sub-communities (content clustering can)
