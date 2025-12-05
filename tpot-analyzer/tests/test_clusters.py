import numpy as np
from scipy.cluster.hierarchy import linkage

from src.graph.clusters import (
    MIN_CLUSTER_SIZE,
    ClusterLabelStore,
    build_cluster_view,
    compute_soft_memberships,
    cut_hierarchy_at_granularity,
    _compute_cluster_edges_with_fusion,
)


def test_cut_hierarchy_assigns_all_nodes():
    points = np.random.randn(8, 2)
    Z = linkage(points, method="ward")
    labels = cut_hierarchy_at_granularity(Z, n_clusters=3)
    assert len(labels) == 8
    assert len(np.unique(labels)) == 3


def test_soft_memberships_row_normalized():
    embedding = np.random.randn(6, 3)
    labels = np.array([1, 1, 2, 2, 3, 3])
    memberships = compute_soft_memberships(embedding, labels)
    row_sums = memberships.sum(axis=1)
    assert np.allclose(row_sums, 1.0)


def test_cluster_edges_with_louvain_fusion():
    # Simple graph: 0->1, 0->2
    adj = np.array(
        [
            [0, 1, 1],
            [0, 0, 0],
            [0, 0, 0],
        ],
        dtype=float,
    )
    cluster_labels = np.array([1, 2, 3])
    soft = np.eye(3)
    louvain_labels = np.array([0, 0, 1])

    edges = _compute_cluster_edges_with_fusion(
        adjacency=adj,
        cluster_labels=cluster_labels,
        soft_memberships=soft,
        louvain_labels=louvain_labels,
        louvain_weight=0.5,
        min_weight=0.0,
    )
    # edge 0->1 boosted (same Louvain), 0->2 dampened
    w01 = next(e.weight for e in edges if e.target_id == "cluster_2")
    w02 = next(e.weight for e in edges if e.target_id == "cluster_3")
    assert w01 > w02


def test_small_clusters_become_individuals(tmp_path):
    embedding = np.random.randn(6, 4)
    Z = linkage(embedding, method="ward")
    node_ids = np.array([f"n{i}" for i in range(6)])
    adj = np.zeros((6, 6))
    node_meta = {nid: {"username": nid, "num_followers": i} for i, nid in enumerate(node_ids)}
    store = ClusterLabelStore(tmp_path / "labels.db")

    view = build_cluster_view(
        embedding=embedding,
        linkage_matrix=Z,
        node_ids=node_ids,
        adjacency=adj,
        node_metadata=node_meta,
        granularity=6,  # likely many small clusters
        label_store=store,
        signal_weights={"spectral": 0.9, "louvain": 0.1},
    )

    for cluster in view.clusters:
        assert cluster.size >= MIN_CLUSTER_SIZE
