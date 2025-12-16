import numpy as np
from scipy.cluster.hierarchy import linkage

from src.graph.hierarchy import build_hierarchical_view


def test_member_ids_match_size_and_serialize():
    # Simple synthetic dataset: 6 nodes, 3 micro-clusters
    embedding = np.array(
        [
            [0.0, 0.0],
            [0.1, 0.1],
            [1.0, 1.0],
            [1.1, 1.1],
            [2.0, 2.0],
            [2.1, 2.1],
        ]
    )
    # Assign micro labels manually to ensure grouping
    micro_labels = np.array([0, 0, 1, 1, 2, 2])
    micro_centroids = np.array([[0.05, 0.05], [1.05, 1.05], [2.05, 2.05]])
    Z = linkage(micro_centroids, method="ward")
    node_ids = np.array([f"n{i}" for i in range(len(embedding))])
    adj = np.zeros((len(embedding), len(embedding)))
    node_meta = {nid: {"username": nid} for nid in node_ids}

    view = build_hierarchical_view(
        linkage_matrix=Z,
        micro_labels=micro_labels,
        micro_centroids=micro_centroids,
        node_ids=node_ids,
        adjacency=adj,
        node_metadata=node_meta,
        base_granularity=3,
        expanded_ids=set(),
        budget=10,
    )

    clusters = view.clusters
    # All clusters should carry member_node_ids with length == size
    for c in clusters:
        assert len(c.member_node_ids) == c.size
        # Member IDs should be strings of node ids
        assert all(isinstance(mid, str) for mid in c.member_node_ids)
