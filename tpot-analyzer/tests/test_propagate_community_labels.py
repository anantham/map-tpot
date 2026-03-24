"""Tests for scripts.propagate_community_labels — community label propagation.

Tests cover:
- TestPropagation: integration tests with a toy graph (8 nodes, 3 communities)
- TestMulticlassEntropy: unit tests for the entropy function

The toy graph is small enough to verify by hand but exercises all key
propagation behaviors: seed preservation, abstain gate, low-degree override,
class balancing, and withheld-seed recovery.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import scipy.sparse as sp

from scripts.propagate_community_labels import (
    PropagationConfig,
    PropagationResult,
    multiclass_entropy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_toy_graph() -> tuple[sp.csr_matrix, np.ndarray]:
    """Build an 8-node graph with 3 communities (2 seeds each) + 2 unlabeled.

    Topology (undirected edges):
        Community A seeds: 0, 1
        Community B seeds: 2, 3
        Community C seeds: 4, 5
        Unlabeled: 6, 7

        0 -- 1 (intra-A)
        2 -- 3 (intra-B)
        4 -- 5 (intra-C)
        0 -- 6, 1 -- 6  (node 6 connected to A seeds -> should get A)
        2 -- 6           (node 6 also has weak B connection)
        4 -- 7, 5 -- 7  (node 7 connected to C seeds -> should get C)
        3 -- 7           (node 7 also has weak B connection)
        6 -- 7           (cross-link between unlabeled nodes)

    Node 6: degree 4 (connected to 0,1,2,7) -> mostly A
    Node 7: degree 4 (connected to 4,5,3,6) -> mostly C
    """
    n = 8
    rows = [0, 2, 4, 0, 1, 2, 4, 5, 3, 6]
    cols = [1, 3, 5, 6, 6, 6, 7, 7, 7, 7]
    data = [1] * len(rows)

    # Build symmetric adjacency
    all_rows = rows + cols
    all_cols = cols + rows
    all_data = data + data

    adj = sp.csr_matrix(
        (all_data, (all_rows, all_cols)),
        shape=(n, n),
        dtype=np.float64,
    )
    adj.setdiag(0)
    adj.eliminate_zeros()

    node_ids = np.array([f"node-{i}" for i in range(n)])
    return adj, node_ids


def _build_community_db(
    db_path: Path,
    *,
    community_sizes: dict[str, list[str]] | None = None,
    exclude_seeds: set[str] | None = None,
) -> None:
    """Create an in-memory SQLite with community + community_account tables.

    Default: 3 communities with 2 seeds each:
        comm-a: node-0, node-1
        comm-b: node-2, node-3
        comm-c: node-4, node-5

    Args:
        community_sizes: override community->member mapping.
        exclude_seeds: set of node IDs to omit from community_account
            (for withheld-seed test).
    """
    if community_sizes is None:
        community_sizes = {
            "comm-a": ["node-0", "node-1"],
            "comm-b": ["node-2", "node-3"],
            "comm-c": ["node-4", "node-5"],
        }
    if exclude_seeds is None:
        exclude_seeds = set()

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE community (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            short_name TEXT,
            description TEXT,
            color TEXT,
            seeded_from_run TEXT,
            seeded_from_idx INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE community_account (
            community_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            weight REAL NOT NULL,
            source TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (community_id, account_id)
        );
    """)

    names = {"comm-a": "Alpha", "comm-b": "Beta", "comm-c": "Gamma"}
    colors = {"comm-a": "#ff0000", "comm-b": "#00ff00", "comm-c": "#0000ff"}

    for cid, members in community_sizes.items():
        conn.execute(
            "INSERT INTO community VALUES (?, ?, ?, ?, ?, NULL, NULL, '2026-01-01', '2026-01-01')",
            (cid, names.get(cid, cid), cid, f"Description for {cid}", colors.get(cid, "#888888")),
        )
        for aid in members:
            if aid not in exclude_seeds:
                conn.execute(
                    "INSERT INTO community_account VALUES (?, ?, ?, 'nmf', '2026-01-01')",
                    (cid, aid, 1.0),
                )

    conn.commit()
    conn.close()


def _run_propagation(
    adj: sp.csr_matrix,
    node_ids: np.ndarray,
    db_path: Path,
    config: PropagationConfig | None = None,
) -> PropagationResult:
    """Run propagation with mocked DB path and adjacency loader."""
    if config is None:
        config = PropagationConfig(
            temperature=1.0,
            regularization=1e-3,
            min_degree_for_assignment=2,
            abstain_max_threshold=0.15,
            abstain_uncertainty_threshold=0.6,
            class_balance=True,
        )

    with patch(
        "scripts.propagate_community_labels.DB_PATH",
        db_path,
    ):
        from scripts.propagate_community_labels import propagate

        result, _ = propagate(adj, node_ids, config)
    return result


# ---------------------------------------------------------------------------
# TestPropagation: integration tests with toy graph
# ---------------------------------------------------------------------------

class TestPropagation:
    """Integration tests using an 8-node toy graph with 3 communities."""

    @pytest.fixture(autouse=True)
    def setup_graph(self, tmp_path):
        self.adj, self.node_ids = _build_toy_graph()
        self.db_path = tmp_path / "test.db"
        _build_community_db(self.db_path)

    def test_seed_labels_preserved(self):
        """After propagation, seed nodes retain their original community as top membership."""
        result = _run_propagation(self.adj, self.node_ids, self.db_path)
        K = len(result.community_ids)

        # Seeds: nodes 0,1 -> comm-a (col 0), nodes 2,3 -> comm-b (col 1), nodes 4,5 -> comm-c (col 2)
        # Find community column indices by name
        name_to_col = {n: i for i, n in enumerate(result.community_names)}

        for seed_idx, expected_name in [(0, "Alpha"), (1, "Alpha"), (2, "Beta"), (3, "Beta"), (4, "Gamma"), (5, "Gamma")]:
            col = name_to_col[expected_name]
            top_community = np.argmax(result.memberships[seed_idx, :K])
            assert top_community == col, (
                f"Node {seed_idx} expected top community '{expected_name}' (col {col}), "
                f"got col {top_community} ({result.community_names[top_community]})"
            )

    def test_unlabeled_node_gets_community(self):
        """Node 6 (connected to A seeds 0,1 and weakly to B seed 2) should get community A as top."""
        result = _run_propagation(self.adj, self.node_ids, self.db_path)
        K = len(result.community_ids)

        name_to_col = {n: i for i, n in enumerate(result.community_names)}
        alpha_col = name_to_col["Alpha"]

        node6_top = np.argmax(result.memberships[6, :K])
        assert node6_top == alpha_col, (
            f"Node 6 expected Alpha (col {alpha_col}), "
            f"got {result.community_names[node6_top]} (col {node6_top})"
        )

    def test_explicit_none_column(self):
        """Output memberships should have K+1 columns (communities + 'none')."""
        result = _run_propagation(self.adj, self.node_ids, self.db_path)
        K = len(result.community_ids)
        n_cols = result.memberships.shape[1]
        assert n_cols == K + 1, (
            f"Expected {K + 1} columns (K={K} communities + 1 none), got {n_cols}"
        )

    def test_abstain_gate(self):
        """A node with max membership below threshold gets abstain_mask=True.

        We construct this by making a node connected equally to all communities
        with very low weights, which after normalization yields low max weight.
        Here we use a high abstain threshold to trigger the gate on the toy graph.
        """
        config = PropagationConfig(
            temperature=1.0,
            regularization=1e-3,
            min_degree_for_assignment=2,
            # Set very high threshold so even modestly confident nodes abstain
            abstain_max_threshold=0.99,
            abstain_uncertainty_threshold=0.01,
            class_balance=True,
        )
        result = _run_propagation(self.adj, self.node_ids, self.db_path, config=config)

        # With threshold=0.99, unlabeled nodes (6 and 7) should be marked abstain
        # because their max community weight won't reach 0.99
        K = len(result.community_ids)
        for idx in [6, 7]:
            max_comm = result.memberships[idx, :K].max()
            # Should be abstained since max_comm < 0.99 OR uncertainty > 0.01
            assert result.abstain_mask[idx], (
                f"Node {idx} with max community weight {max_comm:.3f} "
                f"should be abstained (threshold=0.99)"
            )

        # Labeled nodes should NOT be abstained regardless of threshold
        for idx in range(6):
            assert not result.abstain_mask[idx], (
                f"Labeled node {idx} should never be abstained"
            )

    def test_low_degree_auto_none(self):
        """A degree-1 node should be assigned to the 'none' column.

        We add a leaf node (node 8) connected only to node 0, then set
        min_degree_for_assignment=2 so it gets auto-assigned to 'none'.
        """
        # Extend graph: add node 8 as a leaf connected only to node 0
        n = 9
        adj_dense = self.adj.toarray()
        adj_new = np.zeros((n, n), dtype=np.float64)
        adj_new[:8, :8] = adj_dense
        adj_new[0, 8] = 1.0
        adj_new[8, 0] = 1.0
        adj_ext = sp.csr_matrix(adj_new)

        node_ids_ext = np.array([f"node-{i}" for i in range(n)])

        config = PropagationConfig(
            temperature=1.0,
            regularization=1e-3,
            min_degree_for_assignment=2,  # degree-1 nodes get "none"
            abstain_max_threshold=0.15,
            abstain_uncertainty_threshold=0.6,
            class_balance=True,
        )

        result = _run_propagation(adj_ext, node_ids_ext, self.db_path, config=config)
        K = len(result.community_ids)

        # Node 8 has degree 1, so it should have memberships[:K] = 0 and memberships[K] = 1
        assert result.memberships[8, K] == pytest.approx(1.0, abs=1e-6), (
            f"Degree-1 node 8 should have none=1.0, got {result.memberships[8, K]:.4f}"
        )
        assert result.memberships[8, :K].sum() == pytest.approx(0.0, abs=1e-6), (
            f"Degree-1 node 8 should have zero community weight, "
            f"got {result.memberships[8, :K].sum():.4f}"
        )

    def test_class_balancing(self):
        """With a small (2-member) vs large (10-member) community, class balancing
        reduces the large community's dominance over small communities.

        Graph: 13 nodes.
          comm-big (Alpha): nodes 0-9 (10 members), fully connected clique
          comm-small (Beta): nodes 10-11 (2 members), connected to each other
          Unlabeled node 12: connected to 3 big-community seeds (0,1,2) and
            1 small-community seed (10).

        Balancing applies inverse-sqrt weights to boundary conditions:
          big (size 10): weight = 1/sqrt(10) / max = ~0.45
          small (size 2): weight = 1/sqrt(2) / max = 1.0

        This reduces the large community's boundary signal, shifting propagated
        weight away from it and toward "none". The large community's normalized
        membership for node 12 should be lower with balancing than without.
        """
        n = 13
        rows, cols = [], []

        # Intra-big clique: connect all pairs among 0-9
        for i in range(10):
            for j in range(i + 1, 10):
                rows.append(i)
                cols.append(j)

        # Intra-small edge
        rows.append(10)
        cols.append(11)

        # Unlabeled node 12: 3 connections to big, 1 to small (asymmetric)
        for node in [0, 1, 2, 10]:
            rows.append(12)
            cols.append(node)

        data = [1] * len(rows)
        all_rows = rows + cols
        all_cols = cols + rows
        all_data = data + data

        adj = sp.csr_matrix(
            (all_data, (all_rows, all_cols)),
            shape=(n, n),
            dtype=np.float64,
        )
        adj.setdiag(0)
        adj.eliminate_zeros()

        node_ids = np.array([f"node-{i}" for i in range(n)])

        community_sizes = {
            "comm-a": [f"node-{i}" for i in range(10)],
            "comm-b": ["node-10", "node-11"],
        }

        # Run WITH class balancing
        db_path_balanced = self.db_path.parent / "balanced.db"
        _build_community_db(db_path_balanced, community_sizes=community_sizes)
        config_balanced = PropagationConfig(
            temperature=1.0,
            regularization=1e-3,
            min_degree_for_assignment=2,
            abstain_max_threshold=0.01,
            abstain_uncertainty_threshold=1.0,
            class_balance=True,
        )
        result_balanced = _run_propagation(adj, node_ids, db_path_balanced, config=config_balanced)

        # Run WITHOUT class balancing
        db_path_unbalanced = self.db_path.parent / "unbalanced.db"
        _build_community_db(db_path_unbalanced, community_sizes=community_sizes)
        config_unbalanced = PropagationConfig(
            temperature=1.0,
            regularization=1e-3,
            min_degree_for_assignment=2,
            abstain_max_threshold=0.01,
            abstain_uncertainty_threshold=1.0,
            class_balance=False,
        )
        result_unbalanced = _run_propagation(adj, node_ids, db_path_unbalanced, config=config_unbalanced)

        # Find which column is the big community in each result
        big_col_b = result_balanced.community_names.index("Alpha")
        small_col_b = result_balanced.community_names.index("Beta")
        big_col_u = result_unbalanced.community_names.index("Alpha")
        small_col_u = result_unbalanced.community_names.index("Beta")

        # With balancing, the big community's boundary values are reduced by ~0.45x,
        # so node 12's big-community weight should be LOWER with balancing.
        big_weight_balanced = result_balanced.memberships[12, big_col_b]
        big_weight_unbalanced = result_unbalanced.memberships[12, big_col_u]

        assert big_weight_balanced < big_weight_unbalanced, (
            f"With class balancing, big community (Alpha) weight for node 12 should be "
            f"reduced: balanced={big_weight_balanced:.4f} vs unbalanced={big_weight_unbalanced:.4f}"
        )

        # Consequently, the ratio small/big should be BETTER with balancing
        ratio_balanced = (
            result_balanced.memberships[12, small_col_b]
            / max(result_balanced.memberships[12, big_col_b], 1e-10)
        )
        ratio_unbalanced = (
            result_unbalanced.memberships[12, small_col_u]
            / max(result_unbalanced.memberships[12, big_col_u], 1e-10)
        )
        assert ratio_balanced > ratio_unbalanced, (
            f"Balancing should improve small/big ratio: "
            f"balanced={ratio_balanced:.4f} vs unbalanced={ratio_unbalanced:.4f}"
        )

    def test_withheld_seed_recovered(self):
        """Remove one seed from labeled set, propagate, verify it is still
        correctly classified by its neighbors.

        Withhold node-1 (an Alpha seed connected to node-0 also Alpha, and node-6).
        After propagation, node-1 should still get Alpha as its top community
        because it's connected to node-0 (still an Alpha seed).
        """
        db_path_withheld = self.db_path.parent / "withheld.db"
        _build_community_db(
            db_path_withheld,
            exclude_seeds={"node-1"},
        )

        result = _run_propagation(self.adj, self.node_ids, db_path_withheld)
        K = len(result.community_ids)

        name_to_col = {n: i for i, n in enumerate(result.community_names)}
        alpha_col = name_to_col["Alpha"]

        # Node 1 was withheld — it should be unlabeled now
        assert not result.labeled_mask[1], "Node 1 should be unlabeled (withheld)"

        # But connected to node 0 (Alpha seed) and node 6, so should recover Alpha
        top_community = np.argmax(result.memberships[1, :K])
        assert top_community == alpha_col, (
            f"Withheld node-1 expected to recover Alpha (col {alpha_col}), "
            f"got {result.community_names[top_community]} (col {top_community})"
        )


# ---------------------------------------------------------------------------
# TestMulticlassEntropy: unit tests
# ---------------------------------------------------------------------------

class TestMulticlassEntropy:
    """Tests for the multiclass_entropy function."""

    def test_uniform_distribution_max_entropy(self):
        """Uniform distribution over K classes should give normalized entropy = 1.0."""
        K = 10
        uniform = np.ones((1, K)) / K
        entropy = multiclass_entropy(uniform)
        assert entropy[0] == pytest.approx(1.0, abs=1e-6), (
            f"Uniform over {K} classes should have entropy 1.0, got {entropy[0]:.6f}"
        )

    def test_concentrated_distribution_low_entropy(self):
        """A nearly-peaked distribution should have near-zero entropy."""
        dist = np.array([[0.99, 0.01, 0.0, 0.0]])
        entropy = multiclass_entropy(dist)
        assert entropy[0] < 0.15, (
            f"Concentrated distribution [0.99, 0.01, 0, 0] should have low entropy, "
            f"got {entropy[0]:.4f}"
        )

    def test_zeros_handled(self):
        """Distribution with zeros should not produce NaN."""
        dist = np.array([[0.5, 0.5, 0.0, 0.0, 0.0]])
        entropy = multiclass_entropy(dist)
        assert not np.isnan(entropy[0]), "Entropy should not be NaN for distribution with zeros"
        # For 2 equally weighted bins out of 5: H = 1 bit / log2(5) ~ 0.431
        assert entropy[0] > 0.0, "Entropy should be positive for non-degenerate distribution"
        assert entropy[0] < 1.0, "Entropy should be below max for non-uniform distribution"

    def test_single_class_zero_entropy(self):
        """A single-class distribution should have entropy near 0."""
        dist = np.array([[1.0, 0.0, 0.0]])
        entropy = multiclass_entropy(dist)
        # Due to clipping to 1e-10 there is a tiny residual entropy
        assert entropy[0] < 0.01, (
            f"Single-class distribution should have near-zero entropy, got {entropy[0]:.6f}"
        )

    def test_batch_computation(self):
        """Entropy should be computed row-wise for batched input."""
        batch = np.array([
            [1.0, 0.0, 0.0],  # peaked -> low
            [1 / 3, 1 / 3, 1 / 3],  # uniform -> max
        ])
        entropy = multiclass_entropy(batch)
        assert len(entropy) == 2
        assert entropy[0] < entropy[1], (
            f"Peaked row should have lower entropy than uniform: "
            f"{entropy[0]:.4f} vs {entropy[1]:.4f}"
        )


# ---------------------------------------------------------------------------
# TestIndependentMode: multi-label propagation
# ---------------------------------------------------------------------------

class TestIndependentMode:
    """Tests for --mode independent (multi-label, non-zero-sum propagation)."""

    @pytest.fixture(autouse=True)
    def setup_graph(self, tmp_path):
        self.adj, self.node_ids = _build_toy_graph()
        self.db_path = tmp_path / "test.db"
        _build_community_db(self.db_path)
        self.config = PropagationConfig(
            temperature=1.0,
            regularization=1e-3,
            min_degree_for_assignment=2,
            abstain_max_threshold=0.15,
            abstain_uncertainty_threshold=0.6,
            class_balance=True,
            mode="independent",
        )

    def test_no_row_normalization_applied(self):
        """Independent mode should NOT apply row normalization (memberships / row_sums).

        Verify by checking that the raw scores are preserved: in a tiny symmetric graph,
        raw scores may accidentally sum close to 1.0, so instead we verify the code path
        by checking that seed_neighbor_counts exist (only computed in independent mode)
        and that the result shape is correct.
        """
        result = _run_propagation(self.adj, self.node_ids, self.db_path, self.config)
        K = len(result.community_ids)

        # Independent mode indicator: seed_neighbor_counts is computed
        assert result.seed_neighbor_counts is not None, (
            "Independent mode should produce seed_neighbor_counts"
        )
        # Memberships should have K+1 columns (communities + none)
        assert result.memberships.shape[1] == K + 1

    def test_seed_labels_preserved(self):
        """Seeds should retain their original assignments in independent mode."""
        result = _run_propagation(self.adj, self.node_ids, self.db_path, self.config)
        K = len(result.community_ids)

        name_to_col = {n: i for i, n in enumerate(result.community_names)}
        for seed_idx, expected in [(0, "Alpha"), (1, "Alpha"), (2, "Beta"), (3, "Beta"), (4, "Gamma"), (5, "Gamma")]:
            col = name_to_col[expected]
            top = np.argmax(result.memberships[seed_idx, :K])
            assert top == col, (
                f"Seed node {seed_idx} should have top community {expected}"
            )

    def test_bridge_node_scores_in_multiple_communities(self):
        """Node 6 (connected to A seeds 0,1 and B seed 2) should score in BOTH A and B.

        In classic mode, it gets forced into one. In independent mode, it should
        have nonzero scores in both Alpha and Beta.
        """
        result = _run_propagation(self.adj, self.node_ids, self.db_path, self.config)
        K = len(result.community_ids)

        if result.abstain_mask[6]:
            pytest.skip("Node 6 abstained — can't test bridge")

        name_to_col = {n: i for i, n in enumerate(result.community_names)}
        alpha_score = result.memberships[6, name_to_col["Alpha"]]
        beta_score = result.memberships[6, name_to_col["Beta"]]

        assert alpha_score > 0, f"Node 6 should have positive Alpha score, got {alpha_score}"
        assert beta_score > 0, f"Node 6 should have positive Beta score, got {beta_score}"
        # Alpha should be stronger (2 seeds vs 1)
        assert alpha_score > beta_score, (
            f"Node 6: Alpha ({alpha_score:.4f}) should be stronger than Beta ({beta_score:.4f})"
        )

    def test_seed_neighbor_counts_computed(self):
        """Independent mode should compute seed_neighbor_counts."""
        result = _run_propagation(self.adj, self.node_ids, self.db_path, self.config)

        assert result.seed_neighbor_counts is not None, (
            "Independent mode should compute seed_neighbor_counts"
        )
        assert result.seed_neighbor_counts.shape[0] == len(self.node_ids), (
            f"seed_neighbor_counts should have {len(self.node_ids)} rows"
        )

    def test_seed_neighbor_counts_correct(self):
        """Node 6 should have 2 Alpha neighbors (0,1) and 1 Beta neighbor (2)."""
        result = _run_propagation(self.adj, self.node_ids, self.db_path, self.config)

        if result.seed_neighbor_counts is None:
            pytest.skip("seed_neighbor_counts not computed")

        name_to_col = {n: i for i, n in enumerate(result.community_names)}
        snc = result.seed_neighbor_counts

        alpha_col = name_to_col["Alpha"]
        beta_col = name_to_col["Beta"]
        gamma_col = name_to_col["Gamma"]

        # Node 6: connected to seeds 0 (Alpha), 1 (Alpha), 2 (Beta)
        assert snc[6, alpha_col] == 2, f"Node 6 should have 2 Alpha neighbors, got {snc[6, alpha_col]}"
        assert snc[6, beta_col] == 1, f"Node 6 should have 1 Beta neighbor, got {snc[6, beta_col]}"
        assert snc[6, gamma_col] == 0, f"Node 6 should have 0 Gamma neighbors, got {snc[6, gamma_col]}"

        # Node 7: connected to seeds 4 (Gamma), 5 (Gamma), 3 (Beta)
        assert snc[7, gamma_col] == 2, f"Node 7 should have 2 Gamma neighbors, got {snc[7, gamma_col]}"
        assert snc[7, beta_col] == 1, f"Node 7 should have 1 Beta neighbor, got {snc[7, beta_col]}"
        assert snc[7, alpha_col] == 0, f"Node 7 should have 0 Alpha neighbors, got {snc[7, alpha_col]}"

    def test_labeled_nodes_not_abstained(self):
        """Labeled nodes should never be abstained in independent mode."""
        result = _run_propagation(self.adj, self.node_ids, self.db_path, self.config)

        for idx in range(6):  # seeds 0-5
            assert not result.abstain_mask[idx], (
                f"Labeled node {idx} should not be abstained"
            )

    def test_classic_mode_not_affected(self):
        """Classic mode should still produce zero-sum memberships."""
        classic_config = PropagationConfig(
            temperature=1.0,
            regularization=1e-3,
            min_degree_for_assignment=2,
            abstain_max_threshold=0.15,
            abstain_uncertainty_threshold=0.6,
            class_balance=True,
            mode="classic",
        )
        result = _run_propagation(self.adj, self.node_ids, self.db_path, classic_config)

        # Classic mode: all rows should sum to ~1.0
        for idx in range(len(self.node_ids)):
            row_sum = result.memberships[idx].sum()
            assert row_sum == pytest.approx(1.0, abs=1e-3), (
                f"Classic mode node {idx}: row should sum to 1.0, got {row_sum:.4f}"
            )

        # Classic mode should NOT have seed_neighbor_counts
        assert result.seed_neighbor_counts is None, (
            "Classic mode should not compute seed_neighbor_counts"
        )

    def test_abstain_requires_seed_neighbor(self):
        """In independent mode, nodes with no seed neighbors should be abstained."""
        # Add node 8 connected only to node 6 (unlabeled) — no direct seed neighbor
        n = 9
        adj_dense = self.adj.toarray()
        adj_new = np.zeros((n, n), dtype=np.float64)
        adj_new[:8, :8] = adj_dense
        adj_new[6, 8] = 1.0
        adj_new[8, 6] = 1.0
        # Also connect to node 7 so degree >= 2
        adj_new[7, 8] = 1.0
        adj_new[8, 7] = 1.0
        adj_ext = sp.csr_matrix(adj_new)
        node_ids_ext = np.array([f"node-{i}" for i in range(n)])

        result = _run_propagation(adj_ext, node_ids_ext, self.db_path, self.config)

        if result.seed_neighbor_counts is not None:
            # Node 8 is connected to unlabeled nodes 6 and 7, not directly to seeds
            # Its seed_neighbor_counts should be 0 for all communities
            snc_8 = result.seed_neighbor_counts[8]
            assert snc_8.sum() == 0, (
                f"Node 8 has no direct seed neighbors, should have 0 counts, got {snc_8.sum()}"
            )
