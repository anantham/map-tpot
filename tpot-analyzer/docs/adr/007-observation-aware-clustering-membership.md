# ADR 007: Observation-Aware Clustering and Membership Inference

- Status: Proposed
- Date: 2026-02-17
- Deciders: Human collaborator + computational peer
- Group: Graph math, API, UI/UX
- Related ADRs: 001-spectral-clustering-visualization, 006-shared-tagging-and-tpot-membership

## Issue

Map TPOT currently clusters and scores membership from an incomplete follow graph where missing edges are often treated as true non-edges. This can overstate confidence for well-observed accounts and understate relevance for partially observed ones.

## Context

Observed behavior and constraints:

1. Spectral clustering currently uses a symmetrized adjacency matrix and normalized Laplacian.
2. Hierarchy expansion relies on heuristic strategy scoring plus budget-driven interaction.
3. Tagging and anchor-conditioned membership are defined in ADR 006 but not yet implemented as a calibrated probability system with uncertainty.
4. Data completeness varies substantially across accounts; absent edges are often unknown, not negative evidence.
5. Runtime interaction must remain responsive for local exploration workflows.

## Decision

Adopt a staged architecture with feature flags:

1. Add observation-aware adjacency weighting (MAR approximation) as an opt-in path:
   - `obs_weighting: off|ipw`
   - `obs_p_min` and `obs_completeness_floor` for safe clipping.
2. Keep current hierarchy engine as default (`hierarchy_engine: v1`) while introducing a new engine (`v2`) behind flags.
3. Add membership engine flag (`membership_engine: off|grf`) and implement Gaussian random field membership scoring with calibration in later phases.
4. Require verification scripts and acceptance thresholds before switching defaults.

## Assumptions

1. Missing graph data is persistent and uneven across nodes.
2. MAR-style weighting is a practical first approximation; MNAR risk is monitored via censoring diagnostics.
3. Human labels (positive and contrast anchors) are available and improve over time.
4. Existing API/UI contracts must remain backward compatible during rollout.

## Constraints

1. Interactive latency requirements prohibit minutes-scale inference in online paths.
2. Existing cluster and explorer behavior must remain stable under default flags.
3. Logging must expose data coverage and uncertainty to avoid silent overconfidence.

## Positions Considered

### Option A: Keep current spectral + heuristic pipeline

- Pros: no migration risk.
- Cons: no principled missingness handling; weak uncertainty semantics.

### Option B: Full probabilistic hierarchy (nested DC-SBM) for online serving

- Pros: strongest generative grounding.
- Cons: runtime too expensive for interactive usage.

### Option C (Selected): Hybrid architecture

- Observation-aware regularized spectral hierarchy for fast navigation.
- GRF-based membership probability + uncertainty for account-level inference.
- Nested DC-SBM reserved for offline validation and stress testing.

## Consequences

### Positive

1. Better behavior under partial observability with explicit confidence controls.
2. Clear migration path from heuristics to calibrated membership probabilities.
3. Safer rollout using feature flags and fallback to v1.

### Negative / Risks

1. Added complexity in adjacency construction and diagnostics.
2. Potential variance amplification if IPW weights are not clipped carefully.
3. Need disciplined calibration and threshold monitoring to avoid false certainty.

## Rollout Plan

1. Phase 0: flags + ADR + baseline verification.
2. Phase 1: observation-weighted adjacency behind `obs_weighting=ipw`.
3. Phase 2: hierarchy v2 behind `hierarchy_engine=v2`.
4. Phase 3: GRF membership engine behind `membership_engine=grf`.
5. Phase 4: UI confidence and evidence surfaces.
6. Phase 5: censoring evaluation harness and acceptance gate.

## Verification Requirements

- `scripts/verify_phase0_baseline.py`
- `scripts/verify_observation_weighting.py`
- Phase-specific scripts for hierarchy/membership/evaluation before default switch.

## Open Questions

1. What anchor policy is canonical for negatives (`NOT_IN` only vs. heuristic negatives)?
2. What confidence thresholds trigger "insufficient evidence" labels in UI?
3. At what metrics do we allow `obs_weighting=ipw` to become default?

## Related Artifacts

1. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/src/graph/observation_model.py`
2. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/src/api/cluster_routes.py`
3. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/src/graph/seeds.py`
4. `/Users/aditya/Documents/Ongoing Local/Project 2 - Map TPOT/tpot-analyzer/config/graph_settings.json`
