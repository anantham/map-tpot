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
| `abstain_max_threshold` | 0.15 | If the top community weight < this, the account abstains. Honored in **classic mode** only — independent mode uses a hardcoded Lift baseline of 1.0 (i.e., "abstain if no community shows above-null association"), because the units differ (sum-to-1 probability vs raw Lift). |
| `abstain_uncertainty_threshold` | 0.6 | If combined uncertainty (entropy of the community distribution, normalized to [0,1]) > this, the account abstains. Honored in **classic mode** only — independent mode uses seed-neighbor count instead. |
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

## Amendment — 2026-07-28: score and rerun-range semantics

ADR 021 supersedes the membership-probability and calibrated-confidence
interpretation of this record. Independent-mode PPR/Lift values are
uncalibrated affinities relative to a global-PageRank null model. The
five-factor “confidence index” is a heuristic evidence/support score; it is not
posterior confidence, evidence coverage, or a probability of correct
membership.

The historical `n_bootstrap` procedure repeatedly omits 20% of seeds and takes
the 2.5th and 97.5th percentiles across reruns. It is a seed-holdout
sensitivity range, not ordinary bootstrap resampling and not a 95% confidence
interval with a coverage guarantee. Public surfaces must label it accordingly
or omit it.

The 2026-07-26 frozen solver audit also falsified the documented iteration
plumbing and dangling-mass conservation contracts. The frozen bundle remains a
control artifact, not evidence that the runtime satisfies every algorithmic
claim above. Repair and version the solver before publishing a replacement.

## Amendment — 2026-07-30: independent display bands fail closed

### Issue

The historical `account_band` classifier applied

```
H_bad(x) = -Σ x_i log(x_i) / log(K)
```

directly to independent-mode PPR Lift values. Lift is non-negative but
unbounded and does not sum to one. Therefore `H_bad` is not Shannon entropy:
it changes when the same affinities are expressed at a different scale and can
be negative or greater than one. The specialist rule then ran after the bridge
rule and overwrote it, although the independent-propagation design described a
specialist as one high signal and a bridge as two or more high signals.

The stored `account_band` table is also not bound to an NPZ digest, propagation
mode, taxonomy, or run ID. Its single creation timestamp
(`2026-04-09T03:12:20Z`) corresponds to an archived propagation run, while the
active independent artifact is newer. Public export combined those stale band
rows with the newer Lift matrix.

### Decision

Independent-mode display-band classification is undefined and fails closed:

- `classify_bands` refuses to create `account_band` rows from an independent
  artifact;
- public-site export refuses every unbound `account_band` table, including
  one paired with a valid but potentially unrelated classic artifact, and
  continues only with the safer classified-row fallback;
- `rank_frontier` refuses every unbound `account_band` table at its reusable
  loader boundary, in addition to rejecting zero-valued independent
  uncertainty and synthetic `none` Lift;
- `analyze_frontier_confidence` refuses to relabel compositional Lift spread
  as confidence or apply probability thresholds to independent scores;
- automatic `active_learning` selection and frontier-ranked following fetches
  refuse the unversioned `frontier_ranking` table at both CLI and reusable
  selection-function boundaries; explicit curator-selected handles remain
  available and do not inherit its score/community metadata;
- topic-search ingestion stores raw tweets/profiles but no longer writes an
  artificial ranking score; its verifier exports an inspectable handles file
  for explicit selection;
- the historical band-driven username resolver refuses standalone
  `account_band` selection before database/network work because it has no
  compatible artifact to validate;
- classic-mode display-band generation remains available only as a local
  historical diagnostic, not calibrated membership or uncertainty; current
  export/ranking consumers reject its rows until exact artifact binding
  exists;
- the hosted/exported specialist, bridge, frontier, and faint labels are
  quarantined legacy metadata until regenerated under an evaluated contract.

This amendment does not introduce an artifact-provenance schema. Because the
current table cannot prove exact digest/run/taxonomy/threshold/method binding,
all of its rows are rejected at consumer boundaries. A future classic band
export may be restored only after that receipt exists and is verified at read
time.

The shared entropy primitive now first normalizes each non-negative row,
`p_i = x_i / Σx`, and then computes `-Σ p_i log(p_i) / log(K)`. It is bounded
and invariant to a positive rescaling of the row. A zero row returns zero by
computational convention and must be caught by a separate evidence/abstention
gate; it must never be interpreted as high certainty.

This mathematical repair does **not** define independent display bands.
Compositional entropy measures relative spread, not evidence amount,
membership probability, posterior uncertainty, or correctness. The solver's
entropy over its full output, the old band entropy over community-only columns,
and other confidence/concentration heuristics are distinct consumers and must
not silently share semantics.

### Evidence and falsifiers

On active artifact SHA-256 prefix `1d12f3371205260d` (298,347 accounts, 16
community Lift columns), the historical calculation ranged from `-1190.18` to
`1.97559`; 30,434 rows fell outside `[0,1]`. All 6,964 stored specialists had
negative entropy, and 16,065 stored rows were negative overall. Correct
row-normalized entropy ranged from `0` to `0.975667` and was unchanged by a
7x scale transformation.

Deleting only the historical entropy predicate changed zero current band
assignments, so that predicate contributed no information to the active
classifier. Substituting corrected entropy while retaining the unvalidated
`0.70` threshold changed 1,793 assignments: 659 specialist-to-bridge and 1,134
specialist-to-frontier. That is a taxonomy decision, not a safe numerical
patch.

Independent display bands may be restored only if a registered method:

1. defines mutually coherent specialist/bridge semantics and zero-row
   handling;
2. binds every output to the exact NPZ digest, mode, taxonomy, thresholds, and
   method version;
3. beats Lift plus seed-neighbor baselines on frozen development judgments and
   an untouched holdout using retrieval and calibration metrics;
4. remains stable under score rescaling, seed perturbation, topology snapshots,
   and reasonable threshold changes.

If corrected entropy provides no stable holdout gain, it should remain absent
from banding rather than being retained for mathematical ornament.
