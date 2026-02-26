# Community-Colored ClusterView Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make ClusterView show 14 named TPOT communities as a continuous color field with community-aware spectral presets.

**Architecture:** Two membership matrices (M_render for colors, M_bias for spectral). Sparse top-k semantic adjacency blended with topology. Precomputed alpha presets (0, 0.15, 0.3). Backend aggregates per-cluster community composition. Frontend renders dominant color + impurity ring.

**Tech Stack:** Python (scipy, sklearn, numpy), Flask API, React + Canvas 2D

**Design doc:** `docs/plans/2026-02-26-community-clusteriew-design.md`

---

## Task 1: Stabilize Propagation Output

Make propagation results deterministically addressable with convergence metadata.

**Files:**
- Modify: `scripts/propagate_community_labels.py:635-659` (save_results)
- Test: manual run with `--save`

**Step 1: Update save_results to create stable active path + convergence arrays**

Replace save_results (line 635) with:
- Timestamped archive in `data/community_propagation_runs/`
- Active pointer at `data/community_propagation.npz`
- Add `converged` and `cg_iterations` arrays to saved data

**Step 2: Run with --save and verify output**

Verify both files created. Verify `converged` and `cg_iterations` arrays present in .npz.

**Step 3: Commit**

---

## Task 2: Community Color Aggregation Module

Pure-Python module: propagation data in, per-cluster community composition out.

**Files:**
- Create: `src/communities/cluster_colors.py`
- Create: `tests/test_cluster_colors.py`

**Step 1: Write failing tests**

Test cases:
- `test_loads_from_path`: Load fake .npz, verify PropagationData fields
- `test_returns_none_for_missing_file`: Missing path returns None
- `test_strong_community_cluster`: 4 nodes strongly in Alpha -> dominant=Alpha, intensity>0.5
- `test_peripheral_cluster`: 3 nodes mostly "none" -> low intensity
- `test_mixed_cluster_has_secondary`: Mix of Alpha+Beta -> secondary exists
- `test_unknown_member_ids_skipped`: Unknown IDs gracefully skipped
- `test_empty_members_returns_gray`: Empty list -> null color, 0 intensity

**Step 2: Implement cluster_colors.py**

Key types:
- `PropagationData`: loaded .npz with `node_id_to_idx` lookup
- `CommunityInfo`: dominant/secondary color+intensity+breakdown
- `load_propagation(path)` -> Optional[PropagationData]
- `compute_cluster_community(prop, member_ids)` -> CommunityInfo

Logic: average membership vectors across cluster members, extract argmax for dominant/secondary (excluding "none" column for color, but "none" weight affects intensity).

**Step 3: Run tests, verify pass**

**Step 4: Commit**

---

## Task 3: Community-Aware Spectral Embedding

Sparse A_sem via sklearn NearestNeighbors, blended with A_topo.

**Files:**
- Create: `src/graph/community_affinity.py`
- Create: `tests/test_community_affinity.py`

**Step 1: Write failing tests**

Test cases for `build_semantic_adjacency`:
- `test_basic_shape`: Output is square sparse, same dim as M_bias
- `test_sparsity`: Each row has at most top_k nonzeros
- `test_symmetric`: Result is symmetric
- `test_no_self_loops`: Diagonal is zero
- `test_zero_membership_produces_empty`: All-zero rows have no edges

Test cases for `blend_affinity`:
- `test_alpha_zero_returns_topo`: alpha=0 returns A_topo unchanged
- `test_alpha_one_returns_sem`: alpha=1 returns A_sem
- `test_result_is_sparse`: Output is sparse CSR

Test case for `build_m_bias`:
- `test_downweights_unconverged`: Unconverged classes get reduced weight

**Step 2: Implement community_affinity.py**

Three functions:
- `build_m_bias(memberships, converged, uncertainty)` -> M_bias (n, K)
  Confidence-weights: unconverged classes at 0.3x, multiply by (1-uncertainty)
- `build_semantic_adjacency(M_bias, top_k=20)` -> sparse CSR
  NearestNeighbors on active nodes only, cosine metric, symmetrize via max(A, A.T)
- `blend_affinity(A_topo, A_sem, alpha)` -> sparse CSR
  W' = (1-alpha)*A_topo + alpha*A_sem

CRITICAL: Never materialize M_bias @ M_bias.T densely. Use sklearn NN instead.

**Step 3: Run tests, verify pass**

**Step 4: Commit**

---

## Task 4: Wire Alpha into build_spectral.py

Add `--alpha` and `--propagation` CLI flags.

**Files:**
- Modify: `scripts/build_spectral.py:66-108`

**Step 1: Add CLI args after line 77**

`--alpha FLOAT` (default 0.0) and `--propagation PATH`.

**Step 2: Add blending logic after build_adjacency (line 90)**

When alpha > 0:
1. Load propagation via `load_propagation(args.propagation)`
2. Align node ordering (propagation node_ids to adjacency node_ids)
3. Build M_bias via `build_m_bias()`
4. Build A_sem via `build_semantic_adjacency(M_bias, top_k=20)`
5. Symmetrize A_topo, blend via `blend_affinity()`
6. Adjust output prefix: append `.a{int(alpha*100)}`

**Step 3: Build presets (alpha=0.15, 0.3) and verify files created**

**Step 4: Commit**

---

## Task 5: Backend API — Community Fields

Load propagation at startup, add community color fields to cluster response.

**Files:**
- Modify: `src/api/cluster_routes.py:354-431` (init), `:1048-1097` (serialize)

**Step 1: Load propagation in init_cluster_routes (after line 415)**

Load `data/community_propagation.npz` into global `_propagation_data`. Log success/warning.

**Step 2: Extend serialize_cluster (line 1054)**

Add per-cluster fields via `compute_cluster_community()`:
- `communityColor`, `communityName`, `communityId`, `communityIntensity`
- `secondaryCommunityColor`, `secondaryCommunityIntensity`
- `communityBreakdown` (array of {name, color, weight})

When `_propagation_data` is None, all fields are null/empty (backwards compatible).

**Step 3: Add communities list to meta response**

**Step 4: Run existing cluster tests, verify no regression**

**Step 5: Commit**

---

## Task 6: Frontend — Community Color Rendering

**Files:**
- Modify: `graph-explorer/src/ClusterCanvas.jsx:1107-1131`

**Step 1: Add hexToRgb + communityColor utilities (top of file)**

`hexToRgb(hex)` -> {r, g, b} or null
`communityColor(baseHex, intensity)` -> interpolates gray(140,140,140) to community color

**Step 2: Add community color branch in gradient if/else chain**

Insert before default branch (before `palette.nodeDefaultInner`):
```
} else if (node.communityColor && node.communityIntensity > 0.01) {
  // community gradient using communityColor utility
}
```

**Step 3: Add impurity ring after main fill**

After `ctx.fill()`, when `secondaryCommunityColor` exists and intensity > 0.1:
Draw 2px outer ring stroke in secondary color.

**Step 4: Run frontend tests, verify no regression**

**Step 5: Commit**

---

## Task 7: Frontend — Alpha Slider + Community Legend

**Files:**
- Modify: `graph-explorer/src/ClusterView.jsx`
- Modify: `graph-explorer/src/data.js` (add alpha to fetch params)

**Step 1: Add alpha to fetchClusterView query string in data.js**

**Step 2: Add alpha state + slider in ClusterView.jsx**

Slider snaps to presets from `meta.alphaPresets`. Label: "Community bias".

**Step 3: Add community legend panel**

Colored circle + name for each community from `meta.communities`.

**Step 4: Add alpha to URL state persistence**

Parse on mount, sync on change.

**Step 5: Run frontend tests**

**Step 6: Commit**

---

## Task 8: Community Breakdown in Sidebar

**Files:**
- Modify: `graph-explorer/src/ClusterDetailsSidebar.jsx`

**Step 1: Add stacked bar + labels from communityBreakdown**

Horizontal stacked bar (colored segments proportional to weight).
Below bar: top 4 communities with color dot + name + percentage.

**Step 2: Run tests**

**Step 3: Commit**

---

## Task 9: Alpha Preset Switching in Backend

**Files:**
- Modify: `src/api/cluster_routes.py`

**Step 1: Load all spectral presets at startup**

Try loading `graph_snapshot.a15.spectral.npz`, `graph_snapshot.a30.spectral.npz` alongside default. Store in `_spectral_presets` dict keyed by alpha float.

**Step 2: Parse alpha param, select preset**

GET /api/clusters?alpha=0.15 -> use matching spectral result for hierarchy.

**Step 3: Add alphaPresets + activeAlpha to meta**

**Step 4: Run tests**

**Step 5: Commit**

---

## Task 10: End-to-End Verification

**Step 1: Run propagation with --save**

**Step 2: Build spectral presets (alpha=0.15, 0.3)**

**Step 3: Start backend + frontend**

**Step 4: Verify in browser**

- Community colors visible (vivid to gray gradient across clusters)
- Impurity rings on mixed clusters
- Legend shows 14 communities
- Alpha slider switches presets
- Sidebar shows breakdown on click
- URL persists alpha

**Step 5: Run all tests (backend + frontend)**

**Step 6: Final commit**
