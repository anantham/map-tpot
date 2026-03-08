# ADR-013: Probabilistic Cluster Color Contract and Uncertainty Rendering

**Status:** Accepted
**Date:** 2026-03-06
**Supersedes:** Color math sections of ADR-011 and ADR-012
**Implementation Status:** Backend/API/frontend chroma pipeline is partially deployed; verification script and content-aware fingerprint pipeline are still pending.
**Scope:** Cluster View semantic rendering contract, plus the cross-tab rule that GraphExplorer does not reuse semantic community fill. Does not change clustering algorithm, propagation math, fingerprint vector, or label store.

---

## Context

Cluster View renders community structure as node fill colors. The prior implementation effectively used a single scalar: dominant community selected by `argmax(mean(memberships[:K]))`, with dominant strength taken from `max(mean(memberships[:K]))`, then passed through a `sqrt` curve to a gray→hex lerp.

That formula has two critical flaws:

1. **It ignores the "none" class.** A cluster where 70% of members have no community signal and 30% are weakly EA will render with vivid EA color. The user sees false certainty.

2. **It discards ambiguity.** A cluster split 51/49 between EA and Rationalist looks identical to a 99/1 cluster. The user cannot tell whether a color is a fact or a coin flip.

The broader problem: **the color encodes one thing but the data contains five things that jointly determine how much to trust it.**

This ADR is intentionally a rendering contract. It constrains how cluster color is derived from posterior summaries; it does not require any particular upstream membership engine.

---

## Decision

### Five canonical quantities

Each cluster exposes five independently interpretable quantities from the backend:

```
signal_strength  = 1 - p_C[none]
                   Fraction of aggregate posterior mass not assigned to "none."
                   Range [0, 1]. A cluster of pure unknown / out-of-scope nodes scores 0.

purity           = top1_weight / sum(avg[:K])
                   How concentrated the signal is in the dominant community.
                   Range [0, 1]. 1 = all signal points to one community.

ambiguity        = top1_weight - top2_weight
                   Margin between dominant and runner-up community.
                   High = clear winner. Low = contested.

coverage         = matched_members / total_members
                   Fraction of cluster members that have soft membership scores.
                   Low coverage = many members outside the propagation graph.

confidence       = mean(1 - uncertainty[matched_members])
                   Per-member propagation quality. Uncertain members drag this down.

top1_weight, top2_weight
                   Largest and second-largest community weights within avg[:K].
```

### Chroma formula

```
concentration = 1 - H_norm(p)
                where p = avg[:K] / sum(avg[:K])
                and H_norm = normalized entropy of p

chroma = sqrt(signal_strength × confidence × coverage) × concentration
```

A cluster is **vivid** only when all four factors are high:
- Most members have community signal (signal_strength)
- That signal is confident, not noisy (confidence)
- Most members were scored at all (coverage)
- The signal points mostly at one community (concentration)

Any single factor near zero collapses chroma toward gray. This is the correct behavior: gray means "we don't know," not "this cluster failed."

### Current implementation note

Current code computes `p_C` as the unweighted mean posterior over matched members, then modulates the rendered chroma by `signal_strength`, `confidence`, and `coverage`. This matches the current backend implementation and keeps the ADR honest about the present system state.

A future upstream model may switch to reliability-weighted posterior aggregation. That would be compatible with this ADR as long as the API continues to honor the same rendering semantics.

### Color space

Fill colors use **OKLCH** (perceptual lightness–chroma–hue):

```
H = hexToOklchHue(community.hex_color)   # hue from stored community color; fixed
L = 0.68                                  # fixed lightness across all communities
C = chroma × MAX_CHROMA                  # MAX_CHROMA = 0.26 (vivid but in-gamut)
```

Using OKLCH instead of hex→RGB lerp ensures equal perceived brightness across all community hues and prevents the "blue looks darker than yellow" distortion of the old formula.

### Visual overlays

Two overlays signal data quality without modifying fill:

**Coverage hatch** (diagonal white lines): rendered when `coverage < 0.4`. Meaning: "Many members in this cluster have no propagation score. Color is based on less than 40% of members."

**Ambiguity ring** (secondary community color): rendered when `ambiguity < 0.25` AND `top2_weight > 0.12`. Meaning: "Two communities are close to tied here." Ring opacity scales with how narrow the margin is.

### Fill vs stroke separation (ADR-013 constraint on GraphExplorer)

Semantic community fill color exists **only** in Cluster View. In GraphExplorer:
- Fill = local provenance state (seed, archive, shadow, orphan, bridge)
- Stroke/halo = transient interaction state (selected, neighbor, hovered)
- Community information appears in sidebar/tooltip only, never as primary fill

This prevents the same color from meaning two different things depending on which tab the user is looking at.

---

## API contract

The cluster endpoint now returns per cluster:

```json
{
  "communityColor":        "#4a90e2",
  "communityName":         "EA, AI Safety & Forecasting",
  "communityId":           "...",
  "communityChroma":       0.61,
  "signalStrength":        0.74,
  "purity":                0.68,
  "ambiguity":             0.31,
  "coverage":              0.88,
  "confidence":            0.79,
  "secondaryCommunityColor":  "#9c27b0",
  "secondaryCommunityWeight": 0.14,
  "communityBreakdown":    [...]
}
```

`communityChroma` is the canonical rendering signal. `communityIntensity` (old field, = dominant_weight) is removed. Frontend must use `communityChroma`.

Notes:
- `signalStrength` is equivalent to `1 - noneWeight`, so `noneWeight` is derivable even though it is not serialized explicitly in the current phase.
- `concentration` is currently a backend-internal derived value used to compute `communityChroma`; the API does not expose it separately yet.
- Frontend must treat `communityChroma` as the authoritative fill-strength field and must not attempt to reconstruct chroma from the other metrics.

---

## Verification and rollout status

Implemented now:
- `src/communities/cluster_colors.py` computes `signal_strength`, `purity`, `ambiguity`, `coverage`, `confidence`, and `chroma`.
- `src/api/cluster_routes.py` serializes `communityChroma` and the supporting semantic metrics.
- `graph-explorer/src/ClusterCanvas.jsx` renders OKLCH fill, coverage hatch, and ambiguity ring from those fields.
- `graph-explorer/src/GraphExplorer.jsx` continues to use provenance/local-state fill instead of semantic community fill.

Pending:
- A dedicated verification artifact (`scripts/verify_cluster_color_contract.py`) does not exist yet.
- The content-aware fingerprint pipeline described in ADR-011 is still planned and is not required for this ADR to remain valid.

Human gate:
- This ADR was accepted after explicit human review of the tab boundary model and the color contract on 2026-03-06.

---

## Consequences

### Positive
- Color is now falsifiable: a vivid cluster makes a specific claim about signal, confidence, coverage, and purity that can be checked.
- As the fingerprint pipeline matures and coverage rises, the map becomes more vivid automatically — the color encodes work remaining.
- Ambiguity ring surfaces genuinely contested clusters that were invisible before.
- OKLCH ensures perceptual consistency across communities.

### Negative
- All existing clusters will render somewhat more desaturated than before, because `chroma` < `sqrt(dominant_weight)` in most cases. This is correct — the old formula was over-confident.
- `hexToOklchHue` derivation from stored hex color is a workaround. The long-term fix is storing `hue_oklch` in the `community` table and assigning hues deliberately in perceptual space. That is deferred to a future migration.

### Phase dependency
Coverage may remain low, and clusters may appear hatched, until the planned ADR-011 fingerprint pipeline is implemented and propagation is rerun on richer embeddings. That is the correct visual state for the current data quality level.

---

## Rejected alternatives

**Keep dominant_weight → sqrt → RGB lerp as long-term contract.** Rejected because it systematically overstates confidence when the "none" class dominates, which is the common case before fingerprints are built.

**Encode all five quantities as separate visual channels.** Rejected — too much cognitive load. Chroma encodes the joint quality signal; ambiguity ring and coverage hatch provide the two most actionable exceptions.

**Use HSL instead of OKLCH.** Rejected — HSL does not preserve perceived brightness across hues. Two communities at the same HSL saturation/lightness but different hues will appear to have different emphasis, which introduces unintended hierarchy.
