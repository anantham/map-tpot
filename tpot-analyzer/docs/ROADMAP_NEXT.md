# Roadmap: Four-Part Epistemic Architecture

*Replaces the old phase-based roadmap. See ADR 016 for rationale.*
*Last updated: 2026-03-28 (Session 11)*

---

## The Stack

```
Events → Fingerprints → Derived Views → Task Heads
```

Rich core as calibration. Graph frontier as hypothesis generator. API as targeted validation.

---

## Phase 1: Fingerprint Foundation (NOW — in progress)

**Goal:** Every core account (330) gets an epistemic fingerprint.

| Task | Status | Notes |
|------|--------|-------|
| Fingerprint rollup script | DONE | `scripts/rollup_fingerprints.py` with coverage metadata |
| Bulk archive-only labeling | RUNNING | 86 accounts queued, ~20h at free-tier LLM speed |
| Re-run rollup after bulk labeling | BLOCKED on above | Will produce ~330 fingerprints |
| Wire quote_graph (549K) into TypedGraph | TODO | 10 lines in typed_graph.py |
| Wire mention_graph (3.8M) into TypedGraph | TODO | 10 lines in typed_graph.py |
| Use account_followers (1.6M) for reciprocity | TODO | Eliminates need for check_follow API |
| Re-propagate with full TypedGraph | TODO | After wiring all edge types |
| Re-export + deploy | TODO | After propagation |

## Phase 2: Fingerprint-Informed Community Assignment

**Goal:** Use fingerprints to refine community placement, not just graph.

| Task | Notes |
|------|-------|
| Fingerprint similarity metric | Cosine similarity of simulacrum+posture+theme vectors |
| Fingerprint as CI factor | Accounts with fingerprints get higher confidence |
| Source agreement metric | NMF community == tweet community → confidence boost (EXP-005) |
| Tighten seed criteria | >= 20 bits, >= 5 neighbors, >= 20 tweets, fingerprint exists |
| Per-community edge weights | Calibrate using labeled accounts — which edge types matter where? |
| NMF v2 promotion | Formal alignment done. Decide: promote or keep v1 + overlay? |

## Phase 3: Semantic Edges + Stance Tagging

**Goal:** Preserve the nature of engagement, not just its existence.

| Task | Notes |
|------|-------|
| Add `stance` field to labeling prompt | agree / disagree / extend / critique / neutral |
| Store in semantic_edges table | Per quote/reply, not per follow |
| Signed propagation (future) | Disagreement = negative weight |
| Quote-tweet analysis | 549K pairs with content — richest engagement signal |

## Phase 4: Shockwave Detection (Research)

**Goal:** Track how ideas propagate through the network over time.

| Task | Notes |
|------|-------|
| Temporal event indexing | Tweets have timestamps. Follows/likes don't. |
| Idea adoption tracking | When did each account first tweet about topic X? |
| Propagation delay measurement | Time between epicenter tweet and peripheral adoption |
| Community-level propagation profiles | Which communities are upstream vs downstream? |

## Phase 5: Per-User Ontology (Vision)

**Goal:** Different users see different community boundaries.

| Task | Notes |
|------|-------|
| User-defined seeds | Bring your own labeled accounts |
| Per-user NMF/propagation | Different seeds → different communities |
| Fork-the-ontology UX | "I see 3 communities where you see 1" |

---

## Signals Inventory

| Signal | Rows | In TypedGraph | In NMF | In Labeling | In Fingerprint |
|--------|------|--------------|--------|-------------|---------------|
| Follow edges | 804K | YES | YES | YES | Graph features |
| Reply edges | 12K | YES | Available | YES | - |
| Like edges | 24K | YES | YES (0.4x) | YES | - |
| RT edges | 7K | YES | YES (0.6x) | YES | - |
| Co-followed | 33K | YES | - | Optional | - |
| Quote graph | 549K | **TODO** | **TODO** | **TODO** | - |
| Mention graph | 3.8M | **TODO** | - | YES (per-tweet) | - |
| Account followers | 1.6M | **TODO** | - | - | Reciprocity |
| Tweets (archive) | 5.5M | - | - | YES (archive-first) | Source |
| Likes (archive) | 17.5M | - | Via TF-IDF | - | Content profile |
| Bio embeddings | 15K | - | - | YES (in prompt) | Bio vector |
| Simulacrum | 2K tweets | - | - | Computed per tweet | **PRIMARY** |
| Posture/Theme/Domain | 20K tags | - | - | Computed per tweet | **PRIMARY** |

---

## Evidence Rings

```
Core (330)     → full fingerprint, calibration set
Enriched (60)  → partial fingerprint, validated by API
Profiled (9K)  → bio-only, graph-inferred
Graph (298K)   → pure hypothesis from propagation
```

Each task should know which ring an account is in and what the cheapest upgrade path is.
