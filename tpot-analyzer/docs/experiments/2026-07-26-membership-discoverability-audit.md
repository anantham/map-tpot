# Frozen Membership and Discoverability Assumption Audit

**Date:** 2026-07-26

**Status:** Measurement complete; three strict verifier lanes implemented

**Scope:** Frozen control diagnostics, not a production-model replacement

## Evidence identities

- Frozen scientific bundle:
  `frozen-tpot-control-20260726`, 15 files, 27,272,597 bytes.
- Frozen graph: 95,057 nodes and 319,771 directed stored edges.
- Frozen propagation:
  `community_propagation_train.npz`, 14 communities plus `none`.
- Baseline Community Archive snapshot:
  `20260725T045122Z-4123f74b1a43`,
  SHA-256
  `f40645e181976558f2e107528e9eebf90d82038881fdb886d759e973c3fd3667`.
- Candidate Community Archive snapshot:
  `20260726T045149Z-37a97fa3e057`,
  SHA-256
  `99e93da98bb9fbdbddaa46a9e7f00da7ae501144294c123155e4d56447a8e9bd`.
- Explorer reachability seed panel:
  the exact 18 unique handles in `docs/seed_presets.json["adi_tpot"]`.
- Fixed perturbation RNG seed: `20260726`.

The frozen manifest is verified before scientific inputs are read. Snapshot
comparison verifies both snapshot manifests and file hashes by default.

## Exit and evidence contract

All four CLIs use the same distinction:

- `0`: the measurement completed, including when a hypothesis was falsified;
- `1`: input identity, methodology, serialization, or runtime failure;
- `2`: the measurement completed but a requested strict scientific gate failed.

Optional JSON results use exclusive creation. Serialization completes before
the destination path is created, so neither reruns nor serialization errors
can overwrite or reserve evidence accidentally.

## Pre-commit construct-validity amendments

An independent read-only review was performed after the first real runs and
before commit. It did not change any observed metric or pass/fail outcome. It
made four interpretation/contract corrections:

1. H-S1 was narrowed from causal attribution to CG to the uncertainty
   post-processing fingerprint the probe actually identifies.
2. The original composite probability hypothesis was split into soft-target
   predictive agreement and hard dominant-class confidence calibration.
   Uniform was added alongside the already measured in-sample empirical prior.
3. H-M2 was relabeled as retrospective calibration-set behavior because the
   propagation-heldout accounts were reused to select τ.
4. The discoverability CLI was made total for a missing degree stratum and now
   renders `unavailable` rather than failing during report formatting.

## Hypothesis registry

| ID | Hypothesis | Predeclared falsifier | Observation | Verdict |
|----|------------|-----------------------|-------------|---------|
| H-A1 | The candidate Community Archive corpus advanced | Row delta ≤ 0 or newest tweet did not advance | +3,425 rows, +14 accounts, newest tweet +87,038 seconds | Supported |
| H-A2 | Archive linkage kept pace with new rows | Linked-row delta trails row delta or missing-ID rows grow | +0 linked; +3,425 missing upload IDs | Falsified |
| H-S1 | Frozen uncertainty has the historical entropy-plus-degree post-processing fingerprint | Maximum reconstructed error > `1e-6` | Maximum `3.6783e-08`; zero cells above tolerance | Supported |
| H-S2 | `PropagationConfig.max_iter` and `tolerance` govern class PPR | Any nonempty class exceeds `max_iter=1` under requested tolerance `1e9` | Three classes each reported 90 iterations | Falsified |
| H-S3 | Directed PPR conserves unit mass with a dangling node | `abs(sum(PPR)-1) > 1e-9` after convergence | Sink graph mass `0.21375`; reciprocal control `1.0` | Falsified |
| H-N1 | The About page describes NMF membership semantics implemented by the producer | Producer leaves factor weights independent rather than row-normalizing them | `cluster_soft.py` computes `W_norm = W / W.sum(...)`, while About says memberships need not sum to one | Falsified |
| H-M1a | Frozen rows agree with soft target vectors better than constant baselines | Model must beat empirical-prior and uniform Brier and soft-label log loss | Brier `.586815` vs prior `.505926` and uniform `.517078`; log loss `3.737831` vs prior `2.620363` and uniform `2.708050` | Falsified |
| H-M1b | Top-community confidence is calibrated to hard dominant-class correctness | Five-bin ECE must be ≤ 0.05 | ECE `.094255` | Falsified |
| H-M2 | Recalled propagation-heldout calibration positives are usually core | At least half of recalled calibration accounts must cross τ themselves | 0 core, 53 halo-only, 2 missed | Falsified retrospectively |
| H-M3 | Relevance is invariant to information-equivalent taxonomy granularity | Equal factor split keeps core Jaccard ≥ .95 and core-count change ≤ 5% | Core 175→71, Jaccard `.405714`; selected Jaccard `.576469` | Falsified |
| H-M4 | Final selection survives bounded random stored-edge loss | Minimum selected Jaccard below `.95/.90/.85` at 1%/5%/10% deletion | `.990984/.961264/.922418` | Supported conditionally |
| H-D1 | The frozen graph exhibits the preregistered capture-star pattern | Centers >10%, center-touching shadow edges <90%, or degree-one nodes <50% | 1.731% centers, 100% touching, 80.336% degree-one | Supported |
| H-D2 | Edge semantics materially change reachable topology | Both component and seed-reach changes remain below 5 percentage points | Weak giant 99.991%, mutual 6.425%; seed reach forward 39.944%, reverse 66.780%, mutual 6.425% | Supported |
| H-D5 | Published selection is exactly core plus halo and strongly degree-associated | Selection differs from reconstruction or high-vs-degree-one gap <10 points | Exact 175 + 8,809 = 8,984; selection-rate gap 80.176 points | Supported |

“Supported” for H-D1, H-D2, and H-D5 means the bias/mechanism was detected. It
does not mean capture bias or degree dependence is desirable.

## Methods

### Snapshot comparison

The comparator loads only manifests after identity verification and reports
numeric deltas without inferring missing archive linkage. It treats a mutable
upstream URL as a sequence of immutable local observations.

### Solver contract

The historical uncertainty post-processing fingerprint reconstructs:

1. the symmetrized, zero-diagonal degree;
2. normalized entropy over the saved membership row;
3. inverse-square-root degree uncertainty;
4. `0.7 × entropy + 0.3 × degree uncertainty`;
5. zero uncertainty for labeled rows.

The iteration probe uses a six-node directed cycle and a temporary two-community
seed database. The mass probe compares a two-node sink graph with a reciprocal
two-node control.

### NMF documentation correspondence

The separate NMF clustering script horizontally combines normalized TF-IDF
following and retweet blocks plus optional likes, runs non-negative matrix
factorization, and then explicitly normalizes every account row of `W` to sum
to one. Those values are compositional shares conditional on the selected
factors. They are not the independent overlapping probabilities described by
the About page's “80% plus 60%” example. This static correspondence audit did
not rerun NMF or test random restarts.

### Frozen membership

The 55 accounts are checked for complete graph resolution and zero propagation
label leakage. They were nevertheless reused by the historical calibration
script to choose τ. Core/halo behavior is therefore a retrospective
calibration-set diagnostic, not untouched threshold generalization. Stable
descending ties are mandatory. Brier and soft-label log loss use the full
community-plus-`none` truth vector. ECE separately uses five equal-width bins
over conditional top-community confidence against hard dominant-class
correctness.

The empirical prior is the mean truth vector of the evaluation holdout, so it
is descriptive and optimistically in-sample rather than deployable. The
uniform baseline also beats the model on both proper scores; the predictive
agreement verdict therefore does not depend on that optimistic prior.

The taxonomy intervention duplicates every community into equal halves while
keeping total information, `none`, uncertainty, adjacency, and τ unchanged.

The edge-loss intervention deletes stored CSR entries independently from a
fresh adjacency copy. Propagated memberships remain fixed; only degree,
relevance, core, and halo are recomputed. It therefore tests selection-layer
robustness, not end-to-end propagation robustness.

### Discoverability

The harness constructs three binary views from the same directed edge rows:
directed, any-direction, and reciprocal-only. It measures weak/strong/component
sizes, union reachability from the fixed 18 seeds, capture-center incidence,
degree-one prevalence, exact core/halo reconstruction, and degree-stratified
selection rates.

## Interpretation

The frozen memberships retain ranking information, but these diagnostics do not
support their current soft-probability interpretation. The historical
calibration set mostly validates one-hop reachability: 53/55 positives are
recovered as halo, while none crosses τ as core. This cannot estimate
generalization to a second untouched threshold-validation set.

The graph is useful as a deterministic control but is a capture-centered,
direction-sensitive observation. Its near-total weak connectivity does not
imply reciprocal or directed discoverability.

The stable edge-deletion result is narrower than it first appears because
memberships were held fixed and most selected nodes are halo. A full rerun of
propagation under observation-aware masking remains necessary.

## Explicitly not tested

- Full 15-class legacy CG replay against a high-precision reference solve.
- End-to-end propagation under edge deletion or degree-biased censoring.
- Independent random restarts for NMF factor stability.
- Calibration on verified negative accounts.
- Threshold behavior on a second set untouched by both propagation and τ
  selection.
- Future-time or multi-center account/edge retrieval.
- Current follower-state accuracy.
- Raw Community Archive follower/following object inventory and pagination.
- TwitterAPI.io completeness, response shape, or credit cost; no calls were made.

## Reproduction

```bash
make compare-community-archive \
  BASELINE_SNAPSHOT=data/community_archive/snapshots/20260725T045122Z-4123f74b1a43 \
  CANDIDATE_SNAPSHOT=data/community_archive/snapshots/20260726T045149Z-37a97fa3e057
make verify-propagation-contract
make evaluate-frozen-membership
make verify-network-discoverability
make verify-research-assumptions
```

Add the relevant strict flag directly to each Python module when a falsified
scientific contract should return exit code `2`.

## Decision boundary

Do not silently repair or replace the frozen control. Before generating a new
production bundle, choose and document whether “membership” means:

1. compositional share conditional on the selected taxonomy; or
2. independent, overlapping per-group affinity with separate evidence
   confidence and abstention.

That architectural choice determines the model, calibration target, UI wording,
and valid threshold metrics.
