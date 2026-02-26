# Community-Colored ClusterView — Design Document

**Date**: 2026-02-26
**ADR**: 012 (Community-Seeded Cluster Navigation)
**Scope**: Phases 1-3 of ADR 012 — from propagation results to colored ClusterView

## Goal

Make the ClusterView show the 14 named TPOT communities as a continuous color field
across the entire graph. Every cluster gets a community-derived tint — vivid for
clusters deep in a community's territory, fading to gray for the unaffiliated periphery.
The user can dial community influence on the dendrogram structure itself via alpha presets.

## Key Design Decisions

1. **Dominant community color + impurity ring**: Each cluster colored by its strongest
   community. A thin outer ring shows the second-strongest if significant (>0.1 weight).

2. **Continuous color field**: Color intensity encodes proximity to communities, not
   binary membership. "None" competes as gray — the gray-to-color gradient IS the
   information about TPOT-adjacency.

3. **Community-aware spectral embedding (Approach D)**: Modify the affinity matrix
   with community signal so the dendrogram naturally splits along community boundaries.

4. **Precomputed alpha presets**: 2-3 spectral embeddings at α=0 (pure structure),
   α=0.15 (light bias), α=0.3 (stronger bias). Frontend slider snaps between them.

5. **Two membership matrices**:
   - `M_render` (95K × 15, dense/soft): Raw propagation for color rendering.
   - `M_bias` (95K × 14, sparse/confident): Convergence- and uncertainty-weighted
     for spectral bias. Unconverged classes get 0.3× weight.

## Architecture

```
Layer 1: Offline Build (scripts)
  propagate_community_labels.py --save
  → data/community_propagation.npz (active pointer)
  → data/community_propagation_runs/<timestamp>.npz (archive)

  build_spectral.py --alpha 0.15 --propagation data/community_propagation.npz
  → data/graph_snapshot.spectral.a15.npz
  (repeat for each alpha preset)

Layer 2: Backend API (cluster_routes.py)
  Startup: load propagation + all spectral presets
  GET /api/clusters?alpha=0.15 → picks spectral preset, computes community colors
  Response: existing fields + community color/breakdown per cluster

Layer 3: Frontend (ClusterView + ClusterCanvas)
  Alpha slider (snaps to available presets)
  Community legend panel (14 swatches)
  Continuous color rendering + impurity ring
  Sidebar: community breakdown on click
```

## Math: Community-Aware Embedding

### Blended Affinity Matrix

```
W' = (1-α) * A_topo + α * A_sem
```

Where:
- `A_topo`: existing binary adjacency (319K edges, sparse CSR)
- `A_sem`: sparsified semantic adjacency from community memberships

### Building A_sem (CRITICAL: must stay sparse)

```python
# 1. Confidence-weighted membership (don't let unconverged/uncertain nodes dominate)
confidence_per_class = np.where(converged_mask, 1.0, 0.3)
confidence_per_node = 1.0 - uncertainty
M_bias = M_render[:, :14] * confidence_per_class * confidence_per_node[:, None]

# 2. DO NOT materialize M_bias @ M_bias.T (would be 95K × 95K dense = 72GB)
# Instead: build sparse top-k neighbors directly
# For each node i, compute similarity to all nodes, keep top-k
# Use batch processing or approximate nearest neighbors (ANN)

# Option A: Batch sparse construction
from sklearn.neighbors import NearestNeighbors
nn = NearestNeighbors(n_neighbors=20, metric='cosine', algorithm='brute')
nn.fit(M_bias)
distances, indices = nn.kneighbors(M_bias)
# Build sparse matrix from indices/distances

# Option B: For each row, compute M_bias[i] @ M_bias.T as a sparse op
# (M_bias is 95K × 14, so M_bias[i] is length-14 — dot with all rows is fast)

# Result: A_sem is sparse CSR, ~20 nonzeros per row = ~1.9M entries
```

### Normalized Laplacian (unchanged)

After blending, compute normalized Laplacian and eigenvectors exactly as
current `spectral.py` does. The input is still a sparse matrix.

## API Response Extensions

### Per-cluster community fields

```json
{
  "communityColor": "#4a90e2",
  "communityName": "highbies",
  "communityIntensity": 0.72,
  "secondaryCommunityColor": "#2ecc71",
  "secondaryCommunityIntensity": 0.18,
  "communityBreakdown": [
    {"name": "highbies", "color": "#4a90e2", "weight": 0.72},
    {"name": "Builders", "color": "#2ecc71", "weight": 0.18}
  ]
}
```

Computed by averaging M_render vectors across all memberIds in the cluster,
then extracting dominant and secondary communities.

### Meta extensions

```json
"meta": {
  "communities": [
    {"id": "uuid", "name": "highbies", "color": "#4a90e2", "memberCount": 71}
  ],
  "alphaPresets": [0, 0.15, 0.3],
  "activeAlpha": 0.15
}
```

## Frontend Rendering

### Color priority (highest to lowest)

1. Ego cluster → purple
2. Dragged → cyan
3. Highlighted → orange
4. Pending/entering → blue/green
5. **Community color** → hue from communityColor, saturation from communityIntensity
6. Default → gray

### Community coloring implementation

```javascript
// Interpolate between gray and community color based on intensity
function communityGradient(ctx, x, y, radius, hexColor, intensity) {
  const rgb = hexToRgb(hexColor);
  const gray = { r: 140, g: 140, b: 140 };
  const r = Math.round(gray.r + (rgb.r - gray.r) * intensity);
  const g = Math.round(gray.g + (rgb.g - gray.g) * intensity);
  const b = Math.round(gray.b + (rgb.b - gray.b) * intensity);

  const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
  gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.95)`);
  gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0.65)`);
  return gradient;
}
```

### Impurity ring

If `secondaryCommunityIntensity > 0.1`, draw a 2px outer ring stroke in
the secondary community color at proportional opacity.

### Community legend panel

Sidebar panel showing all 14 communities as colored swatches with names.
Click to highlight clusters where that community dominates.

## Data Pipeline & Storage

### Propagation output (stable addressing)

```
data/
  community_propagation.npz              ← active (symlink or copy)
  community_propagation_runs/
    2026-02-26T10-57.npz                 ← timestamped archives
```

Contents of .npz:
- node_ids (95K,): account IDs
- community_names (14,): names
- community_colors (14,): hex strings
- memberships (95K, 15): soft memberships (14 communities + none)
- uncertainty (95K,): per-node uncertainty
- converged_mask (15,): per-class convergence flag
- abstain_mask (95K,): per-node abstain flag
- config: serialized PropagationConfig

### Spectral presets

```
data/
  graph_snapshot.spectral.npz            ← α=0 (current, unchanged)
  graph_snapshot.spectral.a15.npz        ← α=0.15
  graph_snapshot.spectral.a30.npz        ← α=0.30
  graph_snapshot.spectral_meta.json      ← lists available presets
```

## Files Affected

| File | Change | Complexity |
|------|--------|------------|
| scripts/propagate_community_labels.py | Stable output path, save convergence flags | Low |
| scripts/build_spectral.py | --alpha, --propagation flags, M_bias, A_sem | Medium |
| src/graph/spectral.py | Accept blended affinity (minor input change) | Low |
| src/api/cluster_routes.py | Load propagation+presets, extend serialize, alpha param | Medium |
| graph-explorer/src/ClusterView.jsx | Alpha slider, community legend, pass fields | Medium |
| graph-explorer/src/ClusterCanvas.jsx | Community gradient, impurity ring | Medium |
| graph-explorer/src/ClusterDetailsSidebar.jsx | Community breakdown bar | Low |

## Fallback Plan

If community-aware spectral (α>0) is unstable or produces worse dendrograms,
ship the color field overlay on α=0 (current structure). The M_render coloring
is independent of which spectral preset is active. Colors still work even if
the structure doesn't change.

## Future: Content-Graph Fusion

The labeling pipeline (simulacrum l1-l4, train/dev/test splits, uncertainty
queue) could eventually produce tweet-level content signals. A bridge model
from tweet content → community posterior (14+none), fused with graph
propagation, would improve M_render quality. This requires:

- Extending prediction schema from simulacrum to community labels
- Account-level holdout (not just tweet-level hash split)
- Run-pinned evaluation snapshots (not "latest by model+prompt")
- Content model as auxiliary features, graph propagation stays primary

See ADR 012 Phase 4 (Curation Loop) for the feedback mechanism.
