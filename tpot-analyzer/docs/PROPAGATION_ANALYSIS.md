# Propagation Analysis: Independent Mode (2026-03-24)

## Summary

Switched from zero-sum (classic) to independent community propagation.
Each community is propagated independently — scores don't sum to 1.
This enables bridge account detection.

## Classic vs Independent Mode Comparison

| Metric | Classic (T=2.0) | Independent (raw scores) |
|--------|----------------|--------------------------|
| Non-abstained | 10,108 (5.0%) | 24,295 (12.0%) |
| Specialist (1 comm) | 44 | 10,633 |
| Bridge (2-3 comms) | 0 | 423 (at t=0.05) |
| Multi (4+ comms) | 6,532 | 0 (at t=0.05) |
| Abstained | 191,615 (95.0%) | 177,428 (88.0%) |

## Threshold Sensitivity (Independent Mode)

Raw propagation scores, no per-column normalization. Threshold = minimum
score to count as community membership.

| Threshold | Total assigned | Specialists | Bridges | Multi |
|-----------|---------------|-------------|---------|-------|
| 0.001 | 24,293 | 273 | 4,748 | 19,272 |
| 0.005 | 24,289 | 705 | 9,919 | 13,665 |
| 0.010 | 24,238 | 4,369 | 17,694 | 2,175 |
| **0.020** | **21,341** | **12,804** | **8,531** | **6** |
| **0.050** | **11,056** | **10,633** | **423** | **0** |
| 0.100 | 1,137 | 1,137 | 0 | 0 |

**Chosen threshold: 0.05** (80% precision on held-out validation, 423 bridges)

## Held-Out Validation (ROC)

20% of seeds held out, propagate from 80%, measure rediscovery.

- True community scores: mean=0.049, median=0.042, P90=0.090
- Wrong community scores: mean=0.029, median=0.027, P90=0.048

| Threshold | TPR | FPR | Precision | F1 |
|-----------|-----|-----|-----------|-----|
| 0.01 | 99% | 84% | 53% | 0.69 |
| 0.03 | 73% | 43% | 62% | 0.67 |
| **0.05** | **41%** | **10%** | **80%** | **0.54** |
| 0.07 | 18% | 5% | 78% | 0.29 |

## Noise Filtering: Seed-Neighbor Counts

Independent mode computes seed-neighbor counts per community for each account.
This filters noise: @wirecutter (1 seed neighbor) vs @rtk254 (18 seed neighbors).

Top bridges (real):
- @rtk254: 18 neighbors (Regen:5, Sensemaking:4)
- @c4ss1usl1f3: 16 neighbors (Regen:7, Sensemaking:3)
- @fireandvision: 7 neighbors (AI Creatives:4, LLM Whisperers:3)

Bottom bridges (noise, 1 neighbor):
- @wirecutter, @socialistdogmom, @AccidentalCISO

**Rule: seed_neighbors >= 2 per community for bridge classification.**

## Key Design Decisions

1. **No per-column normalization** — raw propagation scores are naturally calibrated.
   More seed neighbors = higher score. No artificial inflation.

2. **Temperature irrelevant** — independent mode skips row normalization,
   so temperature has no effect. One less parameter.

3. **Abstain gate** — requires both raw score > 0 AND at least 1 seed neighbor.
   Mainstream accounts with 0 classified neighbors are excluded.

4. **Seed-neighbor counts stored** — `PropagationResult.seed_neighbor_counts`
   is an (n_nodes, K) array available for downstream use (export, confidence index).

## 5-Factor Confidence Index (Proposed)

For each account, combine:
1. **Propagation score** — raw per-community score from independent mode
2. **Graph degree** — total edges (evidence strength)
3. **Seed proximity** — seed-neighbor count for that community
4. **Source count** — holdout sources listing this account (0-4)
5. **Bootstrap stability** — assignment survives seed perturbation

## Graph State

- 201,723 nodes, 479,646 edges (463,692 follow + engagement weights)
- 338 labeled seeds (317 NMF + 21 LLM ensemble)
- 16 communities + None
- 12 historical propagation runs archived

## Files

- `data/community_propagation.npz` — active propagation result (independent mode)
- `data/community_propagation_runs/` — 13 archived runs for comparison
- `scripts/propagate_community_labels.py` — `--mode independent|classic`
- `docs/superpowers/specs/2026-03-24-independent-community-propagation-design.md` — original design spec
