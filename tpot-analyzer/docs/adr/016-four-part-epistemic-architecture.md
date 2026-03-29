# ADR 016: Four-Part Epistemic Architecture

**Status:** Accepted (session 11, 2026-03-28)
**Context:** The system was graph-first — follows as primary signal, content as refinement. VISION.md (line 61) describes content-aware fingerprints as the primary layer. Session 11 brainstorming with Codex confirmed the gap.

---

## Decision

Restructure from three-layer graph system to four-part epistemic architecture:

```
1. Event Substrate    → raw interactions with timestamps and content
2. Account Fingerprints → epistemic style as primary representation
3. Derived Views      → task-specific projections (graph, NMF, semantic edges)
4. Task Heads         → community assignment, confidence, bridge detection, etc.
```

The graph remains the operational backbone (fingerprint coverage is sparse), but stops being the ontology. Different tasks read different views, not one collapsed adjacency matrix.

## Rationale

### The problem with graph-first

Graph structure separates social clusters but cannot distinguish epistemic styles. Two accounts can be graph-identical (same follow patterns) but one is a truth-seeking researcher (L1) and the other channels tribal vibes (L3). The vision calls these different relationships to language — the simulacrum distribution IS the fingerprint.

Experiments confirmed this:
- EXP-001: NMF at higher k fragments social clusters, doesn't find ideological facets
- EXP-005: NMF and tweet labeling agree only 42% — they capture different dimensions
- EXP-002: Bio embeddings partially separate communities but can't replace graph

### The concentric data model

Not all accounts have equal evidence depth:

| Ring | Accounts | Evidence | Fingerprint quality |
|------|----------|----------|-------------------|
| Core | ~330 | Full archive (tweets, likes, follows) | Full (once bulk-labeled) |
| Enriched | ~60 | API tweets + LLM labels | Partial |
| Profiled | ~9,400 | Bio + follower counts | Bio-only |
| Graph-only | ~298,000 | Follow edges, propagated scores | None — pure inference |

The architecture must gracefully degrade across rings. Core accounts calibrate. Graph accounts get hypotheses. API spend validates hypotheses for specific accounts.

### What "event substrate" means

Current tables store pair aggregates (account_engagement_agg: source, target, like_count). The raw events are in other tables (likes: 17.5M with tweet text, tweets: 5.5M with timestamps). Not all events have timestamps — follows and likes lack formation time. So the temporal "shockwave" layer can initially trust authored tweets, replies, and retweets more than follows or likes.

### What "fingerprint" means

Per-account distribution of:
- **Simulacrum**: L1/L2/L3/L4 proportions (how they relate to truth)
- **Posture**: original-insight, playful-exploration, critique, signal-boost, etc.
- **Theme**: alignment-research, absurdist-humor, model-interiority, etc.
- **Domain**: AI, philosophy, social, art, etc.
- **Cadence**: tweet frequency, reply ratio, RT ratio
- **Graph features**: followers, reciprocity, community scores

Each with raw counts (to detect small-sample artifacts) and coverage metadata (sample_method, window, freshness). Stored in `account_fingerprint` table.

### What "derived views" means

Different tasks need different projections:
- **Community assignment**: TypedGraph.combine() → multiplex adjacency + fingerprint similarity
- **Bridge detection**: per-type cross-community edge counts from TypedGraph
- **Sub-community detection**: theme/posture clustering within communities
- **Active learning**: fingerprint entropy + graph position uncertainty
- **Shockwave tracking**: temporal event sequences (future)

### What "task heads" means

Each task knows what evidence it needs and what's missing:
```
confidence.cheapest_upgrade = "fetch 30 tweets ($0.15) → enables fingerprint"
confidence.expected_gain = "resolves 60% of remaining uncertainty"
```

## Consequences

### Near-term (implemented in session 11)
- TypedGraph: 5 edge types (follow, reply, like, RT, cofollowed) as separate matrices
- Fingerprint rollup: simulacrum + posture + theme + domain + cadence + coverage metadata
- Bulk archive-only labeling: populating fingerprints for core ring (running)
- Context budget system: modular signal toggling for LLM prompt size control

### Medium-term
- Wire quote_graph (549K) + mention_graph (3.8M) into TypedGraph
- Per-community edge weights in propagation
- Fingerprint-based similarity for community refinement
- Stance tagging on quote/reply tweets (semantic edges)
- Use account_followers (1.6M) for reciprocity without API

### Long-term
- Full event substrate with temporal indexing
- Shockwave detection: idea adoption tracking across accounts
- Per-user ontology: different users see different community boundaries
- Multi-view NMF: shared W matrix, separate H per signal type
- Signed propagation: disagreement edges push apart

### What doesn't change
- Harmonic propagation solver (gets a combined matrix, doesn't need typed awareness)
- Export pipeline (reads community_account + propagation NPZ)
- Public site frontend (reads data.json)
- LLM labeling prompt structure (system + user prompt)

## Assumptions
- API budget stays limited → hypothesis-driven fetching, not bulk ingestion
- Archive core remains the calibration center
- Graph remains operational backbone until fingerprint coverage catches up
- Not jumping to heterogeneous-GNN stack

## Related
- VISION.md — the original intent this ADR realigns with
- EXP-001 through EXP-007 — empirical evidence informing this decision
- ADR 008 — content-aware fingerprinting (proposed, now partially implemented)
- ADR 011 — community visualization (downstream of this architecture)
