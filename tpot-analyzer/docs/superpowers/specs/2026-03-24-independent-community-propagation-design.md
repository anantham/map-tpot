# Independent Community Propagation — Design Spec

> **Status:** Proposed (2026-03-24, Session 10)
> **Problem:** Current multi-class harmonic propagation uses zero-sum memberships (sum to 1), which forces winner-take-all assignments. Bridge accounts that legitimately span 2-3 communities get collapsed to their strongest single community. 95% of accounts abstain, 100% of non-abstained are "specialists."

## The Problem

Current system: one K-class harmonic propagation where membership probabilities sum to 1.

- @repligate has bits: LLM-Whisperers:84, Qualia:69, AI-Safety:34
- But propagation forces their neighbors into ONE of these
- Result: 0 bridge accounts detected, 100% specialist assignments
- The bits system (multi-community by design) and the propagation system (zero-sum) contradict each other

## Proposed Change

**K independent binary propagations**, one per community.

For each community c ∈ {1..K}:
1. **Seed clamping**: For each labeled account, clamp to `min(1.0, abs(bits_c) / BITS_REFERENCE)` — same formula as insert_seeds.py
2. **Binary harmonic propagation**: Solve the standard harmonic system but with only 2 classes (in-community vs not). Each unlabeled node gets a score in [0, 1] for community c.
3. **Result**: Each node has K independent scores, NOT summing to 1.

### Account Types (naturally emerge)

| Type | Pattern | Example |
|------|---------|---------|
| **Specialist** | 1 high score (>0.5), rest low | AI-Safety researcher |
| **Bridge** | 2-3 scores >0.3 | @repligate (LLM + Qualia) |
| **Frontier** | Several scores 0.1-0.3 | Peripheral TPOT, worth investigating |
| **None** | All scores <0.1 | Mainstream tech, not TPOT |

### Confidence Metric

For each account, confidence = `max(scores) - median(scores)`. High gap = clear signal. Low gap = ambiguous.

Alternatively: `sum(scores > 0.2)` = number of community memberships. Specialists have 1, bridges have 2-3, frontier have 0-1.

## Tradeoffs

| Aspect | Current (multi-class) | Proposed (independent) |
|--------|----------------------|----------------------|
| Memberships sum to 1 | Yes (zero-sum) | No (independent) |
| Bridge detection | Impossible | Natural |
| Compute cost | 1 solve | K solves (~16x) |
| Interpretation | "probability of being in community X" | "strength of community X signal reaching this node" |
| Calibration | Probabilities are calibrated (sum=1) | Scores are relative, need separate calibration |
| None detection | Explicit "none" class | All scores low = none |

## Implementation Plan

1. Refactor `propagate_community_labels.py`:
   - Keep existing multi-class as `--mode classic` (backward compatible)
   - Add `--mode independent` (new default)
   - For independent mode: loop over K communities, solve K binary systems
   - Output shape: same (n_nodes, K) but values don't sum to 1

2. Update export (`export_public_site.py`):
   - Account classification: specialist (1 high), bridge (2-3 high), frontier (several medium), faint (all low)
   - Thresholds need tuning from data

3. Update abstain gate:
   - Instead of max < 0.15: abstain if ALL community scores < threshold
   - Bridges won't be killed by the gate anymore

4. Temperature:
   - May not be needed — independent propagation doesn't have the winner-take-all problem
   - Remove or reduce to T=1.0

5. Tracking:
   - `propagation_metrics` table: per-run stats (specialists, bridges, frontier, faint, none)
   - Compare independent vs classic on same seed set

## Compute Budget

Current: 1 conjugate gradient solve, ~1 sec.
Proposed: K=16 solves, each on the same graph but different seed vectors. Each solve is simpler (binary, not multi-class). Estimate: ~5-10 sec total. Acceptable.

## Open Questions

1. Should we normalize scores post-hoc? (e.g., divide by max across communities for each node)
2. How to handle the None community in independent mode? It's artificial — do we even need it if "all scores low" = none?
3. Should bridge accounts be weighted differently in the export? (e.g., colorful card with multiple community colors vs single-community card)
4. Temperature: remove entirely, or use per-community temperature based on seed density?
