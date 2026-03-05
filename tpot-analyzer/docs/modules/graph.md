# Graph Module — Embedding, Clustering & Hierarchy

<!--
Last verified: 2026-03-05
Code hash: bb8bf98
Verified by: agent
-->

## Purpose

The `src/graph/` package is the analytical core of the system. It turns a social graph
(accounts + follow edges) into structured cluster views that a human can navigate, annotate,
and use to understand TPOT community structure.

There are four independent layers:

| Layer | Modules | Purpose |
|-------|---------|---------|
| **Construction** | `builder.py`, `seeds.py` | Build NetworkX graphs from data sources |
| **Embedding & clustering** | `spectral.py`, `clusters.py`, `metrics.py` | Spectral embedding → dendrogram → cluster views |
| **Scoring & inference** | `scoring.py`, `tpot_relevance.py`, `membership_grf.py`, `observation_model.py` | Relevance, membership, and observation-aware weighting |
| **Hierarchy navigation** | `hierarchy/` subpackage | Expand/collapse cluster views within a visual budget |

## Design Rationale

### Why spectral embedding + dendrogram instead of direct clustering?

A dendrogram computed from spectral embeddings lets cluster views be cut at any granularity
without re-running expensive math. The UI can ask "show me 10 clusters" or "show me 40
clusters" and the server just cuts the precomputed tree at a different height. Soft
memberships (distance-based softmax on embeddings) give fractional membership for every
node, enabling continuous edge weights between clusters rather than hard assignment.

### Why hierarchical expand/collapse instead of a flat cluster list?

TPOT is a multi-scale structure — there are broad communities (rationalist-adjacent,
EA/longtermism, tech culture) that contain finer sub-communities. A flat cluster list forces
a choice of granularity. Hierarchical expand/collapse lets the analyst drill into structure
at the scale that's relevant, with a budget cap (default 25 clusters) preventing the canvas
from becoming unreadable.

### Why multiple expansion strategies?

Different clusters have different internal structure. Some are tightly-connected social
cliques (Louvain works well). Some are semantically labelled via tags (TAG_SPLIT works
well). Some have a small number of bridge accounts connecting two groups (BRIDGE_EXTRACTION
works well). Automatically choosing the strategy that reveals the most meaningful structure
— rather than always hierarchical — is the point of `expansion_strategy.py`.

### ADR references

- [ADR-001: Spectral Clustering Visualization](../adr/001-spectral-clustering-visualization.md)
- [ADR-006: Shared Tagging and Anchor-Conditioned TPOT Membership](../adr/006-shared-tagging-and-anchor-conditioned-tpot-membership.md)
- [ADR-007: Observation-Aware Clustering and Membership Inference](../adr/007-observation-aware-clustering-membership-inference.md)

---

## Module Reference

### `builder.py` (302 LOC) — Graph construction

Builds NetworkX graphs from archive data (Supabase REST or local cache) plus shadow
enrichment data. Handles mutual-only filtering and shadow account deduplication.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `build_graph(fetcher, use_cache, ...)` | `GraphBuildResult` | Fetch data + build graph; primary entry point |
| `build_graph_from_frames(accounts, profiles, ...)` | `GraphBuildResult` | Build from pre-loaded DataFrames |

```python
@dataclass
class GraphBuildResult:
    directed: nx.DiGraph
    undirected: Optional[nx.Graph]   # None if mutual_only=False
```

**Design notes:**
- Shadow account deduplication: `shadow:username` nodes remapped to numeric archive node IDs where overlap exists
- `mutual_only=True` builds an undirected graph of only bidirectional edges — used for most analysis
- Profiling via `@profile_operation` / `@profile_phase` decorators throughout

---

### `seeds.py` (286 LOC) — Seed account management

Manages seed lists (presets + user-defined), graph settings, and handle validation.
Persists to `config/graph_settings.json`.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `get_seed_state()` | `Dict` | All seed lists with active marker |
| `save_seed_list(name, seeds, set_active)` | `Dict` | Persist user seed list |
| `set_active_seed_list(name)` | `Dict` | Mark list as active |
| `load_seed_candidates(additional, preset)` | `Set[str]` | Combined active + extra handles |
| `get_graph_settings()` | `Dict` | Full merged config |
| `update_graph_settings(new_settings)` | `Dict` | Validate and persist settings |

**Settings controlled here:**

| Setting | Default | Valid range |
|---------|---------|-------------|
| `alpha` (PageRank damping) | 0.85 | [0.5, 0.995] |
| `discovery_weights` | neighbor=0.4, pr=0.3, community=0.2, path=0.1 | normalized to sum=1 |
| `max_distance` | 3 | [1, 6] |
| `hierarchy_engine` | `"v1"` | `{"v1", "v2"}` |
| `membership_engine` | `"off"` | `{"off", "grf"}` |
| `obs_weighting` | `"off"` | `{"off", "ipw"}` |

---

### `spectral.py` (284 LOC) — Spectral embedding

Normalized Laplacian eigenvectors → spectral embedding → Ward linkage dendrogram.
Dual paths for small (<12k nodes) and large graphs.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `compute_normalized_laplacian(adjacency)` | `csr_matrix` | L_sym = I − D^{−1/2} A D^{−1/2} |
| `compute_spectral_embedding(adjacency, node_ids, config)` | `SpectralResult` | Full pipeline: eigenvectors → linkage |
| `save_spectral_result(result, base_path)` | — | Persist to `.spectral.npz` + `.spectral_meta.json` |
| `load_spectral_result(base_path)` | `SpectralResult` | Load from disk |

```python
@dataclass
class SpectralConfig:
    n_dims: int = 30
    eigensolver_tol: float = 1e-6
    linkage_method: str = "ward"
    stability_runs: int = 0     # 0 = skip ARI check

@dataclass
class SpectralResult:
    embedding: np.ndarray           # (n_nodes, n_dims)
    eigenvalues: np.ndarray
    linkage_matrix: np.ndarray      # scipy linkage format
    node_ids: List[str]
    micro_labels: Optional[np.ndarray]    # set in approximate mode
    micro_centroids: Optional[np.ndarray] # set in approximate mode
```

**Mode selection:**

| Graph size | Mode | Algorithm |
|-----------|------|-----------|
| < 12,000 nodes | Direct | ARPACK eigsh → row-normalize → Ward linkage |
| ≥ 12,000 nodes | Approximate | ARPACK eigsh → BIRCH micro-clusters → k-means reduction → Ward on centroids |

**Why approximate mode?** Ward linkage is O(n²) in memory. At 12k+ nodes a full linkage
matrix exhausts memory. BIRCH reduces n_nodes → n_micro_clusters (typically 200–500),
then Ward runs on centroids. The micro-cluster labels are stored in `SpectralResult` and
used throughout the hierarchy pipeline to map back to original nodes.

---

### `clusters.py` (427 LOC) — Cluster views

Cuts the dendrogram at a granularity, computes soft memberships and cluster edges, and
assembles a `ClusterViewData` for the API response.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `cut_hierarchy_at_granularity(linkage_matrix, n_clusters)` | `np.ndarray` | Dendrogram cut |
| `compute_soft_memberships(embedding, cluster_labels, temperature)` | `np.ndarray` | Distance-based softmax over cluster centroids |
| `compute_cluster_edges(adjacency, cluster_labels, soft_memberships)` | `List[ClusterEdge]` | `soft.T @ A @ soft` |
| `build_cluster_view(embedding, linkage_matrix, ...)` | `ClusterViewData` | Full pipeline |

```python
@dataclass
class ClusterInfo:
    id: str
    member_ids: List[str]
    size: int
    label: str
    label_source: str           # "auto" | "user"
    representative_handles: List[str]
    contains_ego: bool

@dataclass
class ClusterEdge:
    source_id: str
    target_id: str
    weight: float               # from soft membership matrix product
    raw_count: int              # actual edges crossing cluster boundary
```

**`ClusterLabelStore`** — SQLite-backed user labels, keyed by
`(w_spectral, w_louvain, granularity, cluster_id)`. Labels survive across server restarts
and granularity changes.

---

### `metrics.py` (359 LOC) — Graph centrality

Computes PageRank, betweenness, engagement, Gini coefficient, and Shannon entropy.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `compute_personalized_pagerank(graph, seeds, alpha, ...)` | `Dict[str, float]` | Seeded PageRank; max_iter auto-scales with alpha |
| `compute_betweenness(graph, normalized, sample_size)` | `Dict[str, float]` | Approximate for n > 500 |
| `compute_engagement_scores(graph)` | `Dict[str, float]` | `(likes + tweets) / max(followers, 1)` |
| `compute_louvain_communities(graph, resolution)` | `Dict[str, int]` | Louvain community detection |
| `compute_composite_score(pr, bt, eng, weights)` | `Dict[str, float]` | Weighted combination |
| `compute_gini_coefficient(scores)` | `float` | Distribution inequality [0, 1] |
| `analyze_score_distribution(scores, label)` | `Dict` | mean, median, Gini, entropy, percentile concentrations |

**PageRank convergence:** `max_iter` auto-scales — 500 for α≥0.99, 300 for α≥0.95, 200 for α≥0.90, 100 otherwise. Warns if α > 0.95.

---

### `scoring.py` (389 LOC) — Candidate relevance scoring

Scores individual candidate accounts for relevance to a seed set using four signals.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `score_candidate(graph, candidate, seeds, pagerank_scores, weights, ...)` | `Dict` | Full per-signal breakdown |
| `compute_composite_score(scores, weights)` | `float` | Weighted average, capped at 1.0 |

**Default weights:** `neighbor_overlap=0.4, pagerank=0.3, community=0.2, path_distance=0.1`

**Signals:**

| Signal | Formula | What it measures |
|--------|---------|-----------------|
| Neighbor overlap | `|seed_following ∩ candidate_followers| / |seed_following|` | How many seeds already follow accounts that follow this candidate |
| PageRank | `pr_score / p95_score` (clamped to 1.0) | Graph-structural prominence |
| Community affinity | fraction of seeds in same community | Cluster co-membership |
| Path distance | linear decay from 1.0 (d=1) to 0.1 (d=max_distance) | Topological proximity |

---

### `tpot_relevance.py` (160 LOC) — TPOT relevance lens

Four-factor relevance score combining community signal strength, focus, convergence
confidence, and degree normalization. Used to reweight the adjacency for TPOT-focused
embedding.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `compute_relevance(memberships, uncertainty, converged, degrees, median_deg)` | `np.ndarray` | Per-node score r_i ∈ [0, 1] |
| `build_core_halo_mask(r_scores, adjacency, threshold)` | `np.ndarray` | Boolean mask: core (r≥threshold) + 1-hop halo |
| `reweight_adjacency(adjacency, r_scores)` | `csr_matrix` | Continuous reweighting: `D_r^{1/2} W D_r^{1/2}` |

**Formula:**
```
r_i = (1 − p_none_i) × (1 − H_norm_i) × c_i × g(deg_i)

where:
  p_none_i    = memberships[i, -1]          # "no community" signal
  H_norm_i    = entropy(memberships[i]) / log(K)  # focus/concentration
  c_i         = (1 − uncertainty_i) × max(converged[dominant_class_i], 0.3)
  g(deg_i)    = min(1, log(1+deg_i) / log(1+median_deg))  # degree gate
```

Reweighting is continuous (no hard pruning) to preserve downstream PageRank and spectral
computation. The core/halo mask includes 1-hop neighbours to avoid isolated core islands.

---

### `membership_grf.py` (186 LOC) — GRF membership inference

Harmonic label propagation on the graph Laplacian. Given positive/negative anchor nodes
(from account tags), computes smooth membership probabilities for all unlabelled nodes.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `compute_grf_membership(adjacency, positive_anchors, negative_anchors, config)` | `GRFMembershipResult` | Solve harmonic labels via conjugate gradient |

```python
@dataclass
class GRFMembershipConfig:
    prior: float = 0.5
    regularization: float = 1e-3
    tolerance: float = 1e-6
    max_iter: int = 800
    entropy_weight: float = 0.7
    degree_weight: float = 0.3

@dataclass
class GRFMembershipResult:
    probabilities: np.ndarray    # (n_nodes,) — membership score ∈ [0, 1]
    converged: bool
    cg_iterations: int
    total_uncertainty: float
    # per-node uncertainty = entropy_weight * binary_entropy + degree_weight * degree_uncertainty
```

**How it works:** Partitions nodes into anchors (fixed at 0 or 1) and free nodes.
Solves `L_uu × x_u = −L_ul @ anchor_values` via conjugate gradient with optional
Tikhonov regularization. Anchors come from `AccountTagStore.list_anchor_polarities()`.

---

### `observation_model.py` (201 LOC) — Observation-aware weighting (IPW)

Handles partial observability: not every account's follow list has been fully scraped.
Inverse Probability Weighting upweights well-observed edges and downweights sparse ones.

**Public API:**

| Function | Returns | Description |
|----------|---------|-------------|
| `compute_observation_completeness(edges_df, node_ids, ...)` | `np.ndarray` | c_u ∈ [floor, 1] per node |
| `build_binary_adjacency_from_edges(edges_df, node_ids, ...)` | `csr_matrix` | Unweighted adjacency |
| `build_ipw_adjacency_from_edges(edges_df, node_ids, completeness, ...)` | `Tuple[csr_matrix, Dict]` | IPW-weighted adjacency + diagnostics |

**IPW formula:**
```
w_uv = 1 / p_uv
p_uv = clip( (c_u × c_v) / mean(c), p_min=0.01, 1.0 )
```

**Assumption:** Edges are missing at random (MAR) given node-level completeness. This
assumption may not hold if dormant or protected accounts are systematically unobserved in
ways that correlate with community membership.

---

### `signal_pipeline.py` (499 LOC) — Signal validation pipeline

Wraps signal computations with validation (NaN, range, distribution, edge cases),
explainability logging, and event recording.

**Classes:**
- `SignalPipeline` — orchestrates validators and event recording
- `NaNValidator`, `RangeValidator`, `DistributionValidator`, `EdgeCaseValidator` — composable guards
- `ExplainabilityLogger` — generates human-readable score rationale

**Public API:**
- `get_pipeline() -> SignalPipeline` — singleton instance

---

## Hierarchy Subpackage — `src/graph/hierarchy/`

The hierarchy package manages the expand/collapse view of the cluster tree. It is
the heaviest part of the graph module by LOC.

```
hierarchy/
├── models.py          (54 LOC)  — HierarchicalCluster, HierarchicalEdge, HierarchicalViewData
├── builder.py        (708 LOC)  — Main expand/collapse pipeline
├── traversal.py       (99 LOC)  — Dendrogram tree navigation utilities
├── layout.py         (112 LOC)  — PCA positions + connectivity edges
├── focus.py           (86 LOC)  — Teleport: reveal a specific leaf within budget
├── expansion_strategy.py (1013 LOC) — Rule-based strategy selection (8 strategies)
├── expansion_scoring.py  (466 LOC) — Structure-aware scoring of expansion candidates
├── expansion_cache.py    (467 LOC) — LRU + TTL cache; async precompute
└── __init__.py
```

**Total: 3,005 LOC**

> `expansion_strategy.py` (1,013 LOC) and `builder.py` (708 LOC) exceed the ~300 LOC
> threshold. `expansion_strategy.py` is a single-domain strategy selection engine
> (passes single-domain test). `builder.py` mixes orchestration and several helper
> computations — it is a candidate for decomposition into `orchestrator.py` + `view_builder.py`.

### Data models

```python
@dataclass
class HierarchicalCluster:
    id: str                         # "d_{dendrogram_node_idx}"
    parent_id: Optional[str]
    children_ids: Tuple[str, ...]
    member_node_ids: List[str]
    size: int
    label: str
    is_leaf: bool
    expansion_strategy: Optional[str]

@dataclass
class HierarchicalEdge:
    source_id: str
    target_id: str
    raw_count: int
    connectivity: float             # raw_count / sqrt(size_A × size_B)

@dataclass
class HierarchicalViewData:
    clusters: List[HierarchicalCluster]
    edges: List[HierarchicalEdge]
    expanded_ids: Set[str]
    collapsed_ids: Set[str]
    budget: int
    budget_remaining: int
```

### `hierarchy/builder.py` — View construction

```python
build_hierarchical_view(
    linkage_matrix, micro_labels, micro_centroids,
    node_ids, adjacency, node_metadata,
    base_granularity=15,
    expanded_ids=None, collapsed_ids=None,
    focus_leaf_id=None,
    ego_node_id=None,
    budget=25,
    label_store=None,
    louvain_communities=None,
    expand_depth=0.5,
) -> HierarchicalViewData
```

`expand_depth` controls expansion aggressiveness: 0.0 expands minimally (size^0.7),
1.0 expands aggressively (size^0.4). `focus_leaf_id` triggers teleport — the view
guarantees the requested cluster is visible by expanding its smallest ancestor.

### `hierarchy/expansion_strategy.py` — Strategy selection

Eight expansion strategies, each suited to different cluster structure:

| Strategy | Best for |
|----------|---------|
| `INDIVIDUALS` | Very small clusters (≤ 8 members) |
| `SAMPLE_INDIVIDUALS` | Small clusters where showing all is too many |
| `HIERARCHICAL` | Default fallback — uses dendrogram children |
| `LOUVAIN` | Social clusters with strong internal community structure |
| `TAG_SPLIT` | Clusters where user-assigned tags partition members cleanly |
| `CORE_PERIPHERY` | Clusters with high-degree hubs surrounded by leaves |
| `MUTUAL_COMPONENTS` | Clusters that are actually two disconnected mutual-edge components |
| `BRIDGE_EXTRACTION` | Clusters with bridge accounts (high soft-membership entropy) connecting sub-groups |

Selection is rule-based on local structure metrics (tag entropy → TAG_SPLIT, high density + bridges → BRIDGE_EXTRACTION, else HIERARCHICAL). All viable strategies are also evaluated and scored by `expansion_scoring.py`, with the ranked list returned in `ExpansionDecision.alternatives`.

### `hierarchy/expansion_scoring.py` — Structure quality scoring

Scores each expansion strategy by how much meaningful structure it reveals. A good
expansion has balanced cluster sizes, minimal singletons, and strong intra-cluster edges.

**Score components (all [0, 1], equally weighted by default):**

| Component | Formula | Penalizes |
|-----------|---------|-----------|
| Size entropy | H(cluster sizes) / log(n_clusters) | Monolithic expansions |
| Collapse ratio | 1 − (largest_cluster / total) | Single dominant cluster |
| Fragmentation ratio | 1 − (singleton_count / total) | Over-splitting |
| Edge separation | intra_edges / (intra + inter) | Clusters with no internal cohesion |
| Tag coherence | cluster-tag alignment | Clusters that mix semantic groups |

### `hierarchy/expansion_cache.py` — LRU + TTL cache

Caches `CachedExpansion` objects (ranked strategies) per cluster ID. Async precompute
queues jobs for visible clusters to avoid blocking the UI on expand.

| Constant | Value |
|----------|-------|
| `MAX_CACHE_ENTRIES` | 100 |
| `CACHE_TTL_SECONDS` | 3600 (1 hour) |
| `PRECOMPUTE_BATCH_SIZE` | 5 |

### `hierarchy/traversal.py` — Tree navigation

Utilities for navigating scipy linkage matrices: `get_children`, `get_parent`,
`get_subtree_leaves`, `is_descendant`, `find_cluster_leaders`. Internal node indices
use the scipy convention: node `i` in a linkage of `n` leaves is leaf if `i < n`,
internal if `i >= n`.

### `hierarchy/focus.py` — Teleport

`reveal_leaf_in_visible_set(visible_nodes, linkage_matrix, leaf_idx, n_leaves, budget)`
expands the smallest ancestor of a requested leaf until the leaf becomes visible.
Stops and reports failure if budget is insufficient.

---

## Full Dependency Graph

```
builder.py
  └── networkx, pandas, src.data.shadow_store, src.performance_profiler

spectral.py
  └── scipy (sparse, linalg, cluster.hierarchy), sklearn, numpy

clusters.py
  └── networkx, numpy, scipy.sparse, sqlite3

metrics.py
  └── networkx, scipy, numpy

scoring.py
  └── networkx

tpot_relevance.py
  └── numpy, scipy.sparse

membership_grf.py
  └── scipy.sparse (cg), numpy

observation_model.py
  └── pandas, numpy, scipy.sparse

signal_pipeline.py
  └── src.graph.signal_events, threading

hierarchy/builder.py
  └── hierarchy/{traversal, layout, focus, expansion_cache}, numpy

hierarchy/expansion_strategy.py
  └── hierarchy/expansion_scoring, scipy.sparse, networkx

hierarchy/expansion_cache.py
  └── hierarchy/expansion_scoring, threading
```

---

## Known Tensions

1. **`expansion_strategy.py` (1,013 LOC)** — passes single-domain test but is large. Natural decomposition: `strategy_selector.py` (rule-based chooser) + `strategy_executors.py` (8 execute_* functions) + `local_metrics.py`.

2. **Louvain fusion applied in two places** — `clusters.py` and `hierarchy/layout.py` both apply Louvain upweighting with slightly different semantics (hard cluster edges vs soft connectivity). This should be consolidated.

3. **IPW assumption (MAR)** — The observation model assumes missingness is independent of community membership. Dormant or protected accounts may violate this. The assumption is documented in ADR-007 but not validated empirically.

4. **TPOT relevance weights are hard-coded** — the four factors in `compute_relevance()` are fixed. Compare to `discovery_weights` (user-configurable). If the lens is used for filtering, user control may be warranted.
