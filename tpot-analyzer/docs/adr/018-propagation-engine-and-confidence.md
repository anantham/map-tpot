# ADR 018: Label Propagation Engine and Confidence Scoring

**Status:** Accepted (2026-05-17)
**Context:** `src/propagation/` (engine.py, typed_graph.py, io.py, diagnostics.py — ~1,200 LOC of load-bearing inference code) is referenced by ADRs 016 and 017 as "the propagation step" but the algorithm itself, its configuration knobs, and the confidence scoring that gates which accounts make it to the public site were never formally documented. This ADR captures the math, the tunable parameters, and the rationale for the magic numbers in `src/communities/confidence.py` so future contributors can reason about the inference pipeline without re-deriving it from the code.

---

## Decision

Community membership for the ~298K accounts in the graph is computed by **Directed Personalized PageRank (PPR) with Lift normalization**, run independently per community. The membership scores are then gated by a separate continuous **confidence index** that aggregates five evidence factors. Both stages are deterministic given their inputs.

### Stage 1 — Propagation: Directed PPR + Lift

Given:
- A weighted directed adjacency matrix `A` (n × n), built by `TypedGraph` from the follow / engagement / reply / quote signals (`src/propagation/typed_graph.py`).
- A boundary matrix `B` (n_labeled × K+1) of human-curated community memberships, where K is the number of communities and the +1 column is "none" (`load_community_labels()` in `engine.py:110`).

For each class `c` in 0..K, we solve:

```
PPR_c  = (1 - α) · P^T · PPR_c  +  α · v_c
Lift_c = PPR_c / Global_PR
```

where:
- `P = D_out^-1 · A^T` is the row-stochastic transition matrix on the *reversed* graph (because A_ij means "i follows j" and we want probability to flow from j → i: probability accumulates at accounts whose followers are seeded).
- `v_c` is the teleport vector — uniform restart distribution biased toward labeled members of community `c`.
- `Global_PR` is the same PPR with a uniform teleport (no community bias), used as a null model so that mega-followed accounts (e.g. @balajis) don't appear "in every community" simply because they have many followers.
- `α` is the teleport probability (`config.alpha`, default 0.15).

Power iteration runs up to `config.max_iter` (default 200) or until L1 change < `config.tolerance` (default 1e-6). Implemented in `compute_ppr()` (`engine.py:45`).

#### Why directed PPR, not symmetric Laplacian

The graph is a follow graph: edges are directional. Symmetric Laplacian-based label propagation (e.g. harmonic function solver) treats the graph as undirected and loses the asymmetry. A high-status account followed by everyone is *not* the same as an account that follows everyone. Directed PPR preserves the direction; Lift normalization removes the hub bias. This combination handles the "mega-account absorbs all probability mass" problem that broke the original symmetric solver.

#### Why per-class rather than joint

Each community is solved independently because:
- The `mode="classic"` path normalizes memberships to sum to 1 after solve (winner-take-all averaging).
- The `mode="independent"` path keeps raw Lift scores — this is what enables **bridge detection** (an account can score high in multiple communities at once), which ADR 017 identifies as the most interesting signal.
- Solving jointly would force a sum-to-1 constraint at solve time and lose the bridge signal.

### Stage 2 — Confidence Index (five-factor sum)

Membership scores alone don't tell us whether to trust them. A score of 0.7 for an account with one tweet and no labeled neighbors is meaningless; the same score for an account with 1000 tweets, classified neighbors, and bits agreement is a high-confidence assignment.

`src/communities/confidence.py:compute_confidence()` returns a score in `[0, 1]` formed by summing five factors with fixed weights:

| Weight | Factor | What it measures | Where it's computed |
|---:|---|---|---|
| **0.25** | Data richness | Tweet count, likes data, follow data, engagement aggregates | `_data_richness()` |
| **0.30** | Labeling depth | Tweets labeled, total bits accumulated, has-rollup flag | `_labeling_depth()` |
| **0.20** | Concentration | Inverse Shannon entropy over community distribution | `_concentration()` |
| **0.15** | Network context | Fraction of `following` edges that hit classified accounts | `_network_context()` |
| **0.10** | Source agreement | Do NMF and bits agree on top community? | `_source_agreement()` |
| **1.00** | **Total** | | |

The weights are **load-bearing**: they decide which accounts cross the threshold for inclusion in the public-site export, and they shape the "level" classification (`bits_stable`, `propagated`, `unclassified`, etc.) returned alongside the score.

#### Weight rationale

- **Labeling depth highest (0.30):** human/AI labeling is the most expensive and most trusted signal. If 50+ tweets have been labeled, that's strong evidence regardless of graph position.
- **Data richness second (0.25):** without raw data we can't compute much of anything. This is a prerequisite, not just evidence.
- **Concentration (0.20):** a peaked community distribution is more confident than a flat one, but a *very* peaked single-community account might just be a single-tweet-topic account, so this can't dominate.
- **Network context (0.15):** classified neighbors are evidence, but follow graphs have noise (people follow lots of accounts they don't engage with), so this is a moderate signal.
- **Source agreement (0.10):** lowest weight because NMF and bits are correlated — agreement is mostly a tie-breaker, not strong independent evidence.

#### Why a weighted sum, not a learned model

A learned model would need labels to train against, and the whole point of the confidence index is to gate which accounts *become* labels. The five-factor sum is a deliberately simple, inspectable proxy. Tweaking the weights changes which accounts appear in the public-site — there's no ML training loop to retune.

---

## Configuration parameters

All in `PropagationConfig` (`src/propagation/types.py:9`):

| Field | Default | Why |
|---|---:|---|
| `temperature` | 2.0 | Softmax temperature for output distribution. >1 flattens (reduces winner-take-all); <1 sharpens. 2.0 is conservative. |
| `alpha` | 0.15 | PPR teleport probability. Higher = shorter walks (local niches); lower = longer walks (macro-clusters). 0.15 is standard in the PPR literature. |
| `mode` | `"classic"` | `"classic"` = zero-sum memberships (rows sum to 1). `"independent"` = per-community Lift scores, no sum constraint — enables bridge detection. The deploy pipeline runs `"independent"`. |
| `regularization` | 1e-3 | Tikhonov regularization for the legacy harmonic solver. Stabilizes sparse regions. |
| `prior` | 0.0 | Bias for unlabeled nodes toward uniform membership. 0 = no bias. |
| `tolerance` | 1e-6 | CG / power-iteration convergence threshold (L1 norm). |
| `max_iter` | 800 | Hard cap on solver iterations. Real runs converge in <200. |
| `min_degree_for_assignment` | 2 | Nodes with combined in+out degree below this get auto-assigned "none". Degree-1 nodes (52K+ leaves) would just copy their single neighbor's label, which isn't evidence. |
| `abstain_max_threshold` | 0.15 | If the top community weight < this, the account abstains (no assignment). |
| `abstain_uncertainty_threshold` | 0.6 | If combined uncertainty > this, the account abstains. |
| `class_balance` | True | Inverse-sqrt class balancing. Without it, a 73-member community would absorb ~18× more shadows than a 4-member one purely from boundary-surface bias. |

Diagnostic snapshots at α=0.15, 0.45, 0.85 are checked in at `docs/diagnostics/alpha_*.txt` for reference when retuning.

---

## How the pieces fit together

```
┌─────────────────────────────────────────────────────────────────────┐
│  CURATION                                                            │
│  community_account table  ←  curator UI (graph-explorer)            │
│  (human + NMF seed assignments)                                      │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PROPAGATION  (scripts/propagate_community_labels.py)                │
│                                                                      │
│  1. TypedGraph builder (src/propagation/typed_graph.py)             │
│     follow + engagement + reply + quote → weighted adjacency         │
│                                                                      │
│  2. Load labels (engine.py:load_community_labels)                   │
│     community_account → boundary matrix B (n_labeled × K+1)         │
│                                                                      │
│  3. Compute Global PR (compute_ppr, uniform teleport)               │
│     → null model for hub correction                                  │
│                                                                      │
│  4. For each community c: PPR_c then Lift_c = PPR_c / Global_PR     │
│                                                                      │
│  5. Apply config: abstain thresholds, min_degree, class_balance     │
│                                                                      │
│  6. Write back to community_account (with source='propagated')       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CONFIDENCE GATING (src/communities/confidence.py)                   │
│  Per account: 5-factor weighted sum → score ∈ [0,1] + level         │
│  Score threshold gates inclusion in public-site export              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EXPORT (scripts/export_public_site.py + Makefile:33)                │
│  data.json + search.json → Vercel Blob → maptpot.vercel.app         │
└─────────────────────────────────────────────────────────────────────┘
```

Bootstrap mode (`n_bootstrap > 0`, used in `make deploy-public-site`) runs propagation N times with different 20% holdout splits and reports per-account stability (1 - std/mean of membership) and 95% confidence intervals. Stability < ~0.7 indicates an unstable assignment that's sensitive to which seeds are included.

---

## Consequences

### What this locks in
- α=0.15 as the default teleport — changing this without re-running the diagnostic snapshots will produce a different community map.
- The 5×weight schedule in `confidence.py` — changing any single weight shifts which accounts appear on the public site. The weights are reviewed in this ADR; any change should land with this ADR updated.
- The TypedGraph signal mix (follow + engagement + reply + quote) — adding a new signal (e.g. likes graph) requires extending `typed_graph.py` and re-running propagation.

### What this leaves open
- The five weights are intuited, not learned. A future ADR could replace them with held-out-eval-tuned weights once the gold-label set in ADR 014 is large enough.
- Bridge detection (mode=independent) is enabled but not exposed in the public-site export schema. ADR 017 calls for it; ADR 015 has the data-pipeline architecture; the export step is the missing link.
- Bootstrap stability is computed but not currently surfaced in card UI. Could be added as a "stability bar" on community-page cards.

### What this does NOT change
- Curator UI (graph-explorer) writes to `community_account` directly; propagation reads from it.
- The auth/security gates on curator endpoints (added separately).
- The Vercel deploy pipeline (`make deploy-public-site` orchestrates this).

---

## Assumptions

- The follow + engagement + reply + quote signal combination in `TypedGraph` reflects community membership better than any single signal. This is asserted by ADR 015 (data pipeline) and not re-litigated here.
- Mega-followed accounts are not in every community despite high PPR scores under uniform teleport — the Lift normalization correctly isolates community-specific affinity. (Sanity check: @balajis appears in `Tech-Intellectuals` only, not in all 16.)
- Confidence threshold around 0.4–0.5 separates "include in public site" from "withhold pending more data". Exact threshold lives in `scripts/export_public_site.py`, not in this ADR — that's an export policy, not a propagation property.

---

## Related

- ADR 013 — probabilistic cluster color contract (downstream consumer of memberships)
- ADR 014 — account-community gold labels and held-out evaluation (the data that would let us learn the confidence weights)
- ADR 015 — data pipeline architecture (where propagation sits)
- ADR 016 — four-part epistemic architecture (propagation is the "spread" stage)
- ADR 017 — multi-view descriptor (uses graph view = propagation output as primary detection signal)
