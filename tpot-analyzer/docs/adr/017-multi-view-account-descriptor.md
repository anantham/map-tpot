# ADR 017: Multi-View Account Descriptor

**Status:** Revised (session 12, 2026-03-30)
**Context:** EXP-008 showed follow-graph NMF and tweet-content clusters are nearly independent (AMI=0.08). EXP-009 showed that view *disagreement* is a feature of TPOT membership, not noise — 82% of holdout TPOT members are bridges (graph community ≠ semantic community). ADR 016 called for "task-specific heads over multiple views" — this ADR specifies what those views are and their distinct roles.

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

### View Roles (revised after EXP-009)

Views do NOT all answer the same question. Each view has a distinct job:

| View | Question it answers | Mechanism |
|------|-------------------|-----------|
| **Graph** | "Is this account near TPOT?" | KNN on NMF weights — 100% recall at threshold 0.3 |
| **Semantic** | "What kind of TPOT member?" | Tweet cluster histogram — intellectual profile |
| **Taste** | "What do they endorse?" | Like cluster histogram (future) |
| **Interaction** | "How do they engage?" | Typed graph features — reciprocity, quote/reply patterns |
| **Profile** | "How do they describe themselves?" | Bio embedding |

**Critical finding (EXP-009):** View disagreement is NOT low confidence. 82% of holdout TPOT members have their graph community disagree with their semantic community. TPOT is a *cross-cutting meta-community* — its members follow one social tribe but intellectually range across several. Penalizing disagreement hurts detection.

### Combination Strategy (revised)

**NOT per-view voting for community assignment.** Instead:

1. **Detection** (is this account TPOT?): Graph view alone. Propagation from seeds through TypedGraph. This works — 100% recall on holdout at threshold 0.3.

2. **Characterization** (what kind of TPOT?): Semantic + taste + interaction views. These describe the account's intellectual profile, not their tribe. An account can be graph=AI-Safety but semantic=Contemplative — that's a real description, not an error.

3. **Bridge detection** (multi-community members): View disagreement. When graph ≠ semantic, the account spans communities. This is the most interesting signal for the TPOT map — bridges are the people who connect tribes.

4. **Confidence calibration**: Graph confidence (how many seeds nearby) × evidence depth (how many views available). NOT view agreement.

### Account Rings and View Availability

| Ring | Graph | Semantic | Taste | Interaction | Profile |
|------|-------|----------|-------|-------------|---------|
| Core (330) | Yes | Yes (after embedding) | Future | Yes | Most |
| Enriched (60) | Yes | Yes (API tweets) | Partial | Yes | Most |
| Profiled (9K) | Propagated | No | No | Some | Yes |
| Graph-only (298K) | Propagated | No | No | Minimal | No |

The representation naturally degrades: core accounts get a rich multi-view profile, graph-only accounts get a hypothesis. Confidence reflects evidence depth, not view agreement.

## Rationale

### Evidence

**EXP-008:** Follow graph and tweet content are orthogonal (AMI=0.08). Quiet-Creatives are content-coherent (purity 0.96 at k=2). Core-TPOT, highbies are content-diverse. They capture different dimensions.

**EXP-009:** 82% of holdout TPOT members are bridges (graph community ≠ semantic community). View disagreement is a feature of TPOT membership. Boosting agreement and penalizing disagreement HURTS detection — it pushes real TPOT members down the ranking. Examples: @visakanv (graph=Internet-Intellectuals, semantic=Contemplative), @repligate (graph=LLM-Whisperers, semantic=Core-TPOT), @patio11 (graph=Tech-Intellectuals, semantic=Collective-Intelligence).

### The NMF question

NMF remains the primary detection mechanism — it covers all 298K accounts and graph proximity to seeds works at 100% recall. But NMF's community *label* is incomplete for most TPOT members. The semantic view enriches the label, not replaces it. An account is not "AI-Safety" — they are "AI-Safety by social position, Contemplative by intellectual interest, with bridge connections to Qualia-Research."

## Consequences

### Near-term (implementable now)
- Build `account_descriptor` as a JIT-computed view, not a stored table
- Graph view: query `community_account` weights → detection + primary community
- Semantic view: query `account_cluster_histogram` at k=8 → intellectual profile
- Bridge flag: graph_community ≠ semantic_community → multi-community member
- Interaction view: query TypedGraph for reciprocity, typed_degree → engagement style

### Medium-term
- Taste view: embed liked tweets in same basis as authored tweets
- Richer cards: show "AI-Safety by social position, Contemplative by intellectual interest"
- Active learning: prioritize accounts where we have graph signal but no semantic view (cheap upgrade: fetch tweets → embed → characterize)

### What changes in the pipeline
- Seed insertion: unchanged (graph-based, works at 100% recall)
- Propagation: unchanged (TypedGraph adjacency)
- Export: cards gain multi-dimensional description (social tribe + intellectual profile + bridge status)
- Confidence: graph confidence × evidence depth, NOT view agreement
- Active learning: prioritizes accounts where semantic view would add characterization value

### What doesn't change
- Harmonic propagation solver
- TypedGraph combination
- LLM labeling prompt structure
- Public site frontend

## Assumptions
- Graph proximity to seeds is the correct detection mechanism for TPOT membership
- Semantic view adds characterization value even if it doesn't improve detection
- Bridge detection (view disagreement) is genuinely interesting, not just noise
- Tweet cluster stability across re-runs (need to verify — EXP-010 candidate)

## Related
- ADR 016 — four-part epistemic architecture (this ADR implements the "task heads" layer)
- EXP-005 — NMF vs tweet labeling (42% agreement, first hint of orthogonality)
- EXP-008 — multi-scale clustering (AMI=0.08, confirmed orthogonality)
- EXP-009 — view agreement test (82% of TPOT are bridges, disagreement is the signal)
- EXP-001 — higher-k NMF can't find sub-communities (content clustering can)
