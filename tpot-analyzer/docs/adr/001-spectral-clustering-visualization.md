# ADR-001: Spectral Clustering for Hierarchical Graph Visualization

**Status**: Proposed  
**Date**: 2024-12-05  
**Authors**: Aditya, Claude  
**Reviewers**: -

## Context

The TPOT Analyzer currently visualizes social graph data using a force-directed layout (react-force-graph-2d) with all nodes rendered simultaneously. At 70K+ nodes, this is:

1. **Computationally expensive** — force simulation is O(n²) per tick
2. **Visually overwhelming** — users cannot comprehend thousands of nodes
3. **Semantically flat** — no hierarchy or abstraction levels

Users want to:
- See their position in the broader TPOT community
- Understand community structure at multiple levels of abstraction
- Discover adjacent accounts and communities
- Navigate smoothly from high-level overview to individual accounts

## Decision

We will implement **hierarchical spectral clustering** with **semantic zoom** as the primary visualization mode.

### Core Architecture

1. **Spectral embedding** computed on full graph (70K nodes)
   - Normalized Laplacian eigenvectors (top 30-50 dimensions)
   - Provides continuous coordinate space where graph distance ≈ embedding distance

2. **Hierarchical clustering** on spectral embedding
   - Ward's method agglomerative clustering
   - Produces dendrogram that can be cut at any granularity

3. **Soft cluster membership** via distance-to-centroid in spectral space
   - Each node has probability distribution over clusters
   - Enables weighted inter-cluster edge computation

4. **Semantic zoom** as primary interaction
   - Zoom level determines cluster granularity (N visible items)
   - Visual budget maintained: always ~20-40 items on screen
   - No geometric zoom — node sizes fixed for readability

5. **Hybrid signal approach**
   - Spectral clustering + Louvain community detection as two signals
   - Weight sliders allow user to blend signals
   - Architecture supports adding more signals later

## Alternatives Considered

### Alternative 1: Louvain-only clustering

**Pros**: Already implemented, fast, deterministic  
**Cons**: Hard assignments only, single resolution, not responsive to weights

### Alternative 2: Ego-relative spectral clustering

**Pros**: Personalized view, smaller computation  
**Cons**: Must recompute per user, clusters not comparable across users

### Alternative 3: Node2Vec embeddings

**Pros**: Captures higher-order structure, flexible  
**Cons**: Training overhead, opaque dimensions, still need clustering step

### Alternative 4: Stochastic Block Model (MMSB)

**Pros**: Principled probabilistic model, native soft membership  
**Cons**: Expensive inference, doesn't scale to 70K nodes easily

**Decision**: Spectral clustering provides the best balance of:
- Principled mathematics (minimizes normalized cut)
- Soft membership (via embedding distances)
- Hierarchical structure (via agglomerative clustering)
- Computational tractability (eigendecomposition is one-time cost)

## Detailed Decisions

### D1: Full graph vs ego-relative embedding

**Decision**: Full graph  
**Rationale**: 
- Compute once, use for all users
- Clusters are "objective" — users see same community structure
- Ego coloring provides personalization without recomputation

### D2: Louvain integration

**Decision**: Hybrid approach — both signals with weight sliders  
**Rationale**:
- Louvain captures modularity-based communities
- Spectral captures geometric structure
- Different signals may reveal different aspects of community
- User control allows exploration

### D3: Precision vs speed for eigendecomposition

**Decision**: High precision with instrumentation  
**Rationale**:
- One-time precomputation, can afford to be slow
- Stability matters — clusters shouldn't change on re-run
- Instrumentation tracks approximation costs for future optimization

### D4: Edge directionality

**Decision**: Distinct curved lines for A→B and B→A  
**Rationale**:
- Following is asymmetric and meaningful
- A following B ≠ B following A
- Curved edges avoid overlap
- Gradient coloring (dark→light) shows direction

### D5: Zoom model

**Decision**: Semantic zoom only (no geometric zoom)  
**Rationale**:
- Fixed visual budget maintains readability
- Semantic zoom is the primary navigation mechanism
- Panning (click-drag) handles spatial navigation
- Simpler interaction model

### D6: Cluster → individual transition

**Decision**: Clusters with <4 members show as individuals  
**Rationale**:
- Clusters of 1-3 aren't meaningful abstractions
- Avoids "cluster of 1" visual oddity
- Threshold is configurable if needed

### D7: Cluster labeling

**Decision**: Auto-label with top 3 most-followed handles, user-editable  
**Rationale**:
- Immediate useful labels without manual work
- Most-followed = most recognizable representatives
- User can override with semantic names ("Jhana Bros")
- Labels persist in SQLite

### D8: Interaction model

**Decision**: 
- Single click = show member list (info panel)
- Double click = drill down (expand cluster in place)
- Right click = context menu (rename, etc.)

**Rationale**:
- Matches common UI patterns
- Single click is non-destructive (just shows info)
- Double click for navigation matches file explorer convention

### D9: State persistence and shareability

**Decision**: URL reflects zoom level, focus cluster, ego  
**Rationale**:
- Enables sharing specific views
- Browser back/forward work naturally
- Bookmarkable states

### D10: Coexistence with current GraphExplorer

**Decision**: Build as separate component, coexist initially  
**Rationale**:
- Lower risk — don't break existing functionality
- Can compare approaches
- Gradual migration path

## Technical Specifications

See: `docs/specs/spectral-clustering-spec.md`

## Test Plan

See: `docs/test-plans/spectral-clustering-tests.md`

## Consequences

### Positive

- Users can navigate large graphs intuitively
- Community structure becomes visible at multiple scales
- Soft membership captures nuanced positions (boundary accounts)
- Architecture supports adding more clustering signals
- Shareable views enable collaboration

### Negative

- Increased precomputation time (eigendecomposition on 70K nodes)
- Additional storage for embeddings and hierarchy
- More complex codebase
- Two visualization modes to maintain (temporarily)

### Risks

1. **Spectral embedding quality** — may not produce meaningful clusters for this graph structure
   - Mitigation: Instrumentation to evaluate, fallback to Louvain-only

2. **Performance at runtime** — soft membership computation may be slow
   - Mitigation: Precompute membership matrix, cache aggressively

3. **User confusion** — semantic zoom is non-standard
   - Mitigation: Clear UI affordances, onboarding tooltip

## Implementation Plan

See: `docs/specs/spectral-clustering-spec.md#implementation-plan`

## References

- Von Luxburg, U. (2007). A tutorial on spectral clustering. Statistics and computing.
- Blondel, V. D., et al. (2008). Fast unfolding of communities in large networks. (Louvain method)
- Current codebase: `src/graph/metrics.py`, `src/api/server.py`, `graph-explorer/src/GraphExplorer.jsx`
