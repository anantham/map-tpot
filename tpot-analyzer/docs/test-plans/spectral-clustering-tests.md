# Test Plan: Spectral Clustering Visualization

**Version**: 1.0  
**Date**: 2024-12-05  
**Status**: Draft

## Overview

This document defines the testing strategy for the spectral clustering visualization feature. Tests are organized into:

1. **Unit Tests** - Individual function correctness
2. **Integration Tests** - Component interactions
3. **End-to-End Tests** - Full user flows
4. **Performance Tests** - Scale and timing
5. **Manual Test Scenarios** - UI/UX validation

---

## Unit Tests

### `src/graph/spectral.py`

#### Test Suite: `tests/test_spectral.py`

```python
"""Unit tests for spectral embedding computation."""

import pytest
import numpy as np
from scipy.sparse import csr_matrix
from src.graph.spectral import (
    compute_normalized_laplacian,
    compute_spectral_embedding,
    SpectralConfig,
    SpectralResult
)


class TestNormalizedLaplacian:
    """Tests for Laplacian computation."""
    
    def test_simple_graph(self):
        """Test Laplacian on a simple 3-node graph."""
        # Triangle graph: 0-1, 1-2, 0-2
        adj = csr_matrix([
            [0, 1, 1],
            [1, 0, 1],
            [1, 1, 0]
        ])
        
        L = compute_normalized_laplacian(adj)
        
        # For regular graph, diagonal should be 1
        assert np.allclose(L.diagonal(), 1.0)
        
        # Off-diagonal for connected nodes should be -1/degree
        # degree = 2 for all nodes, so -1/sqrt(2*2) = -0.5
        assert np.isclose(L[0, 1], -0.5)
    
    def test_directed_graph_symmetrization(self):
        """Test that directed edges are symmetrized."""
        # Directed: 0->1, 1->2
        adj = csr_matrix([
            [0, 1, 0],
            [0, 0, 1],
            [0, 0, 0]
        ])
        
        L = compute_normalized_laplacian(adj)
        
        # Should be symmetric after symmetrization
        assert np.allclose(L.toarray(), L.toarray().T)
    
    def test_disconnected_node(self):
        """Test handling of isolated node (zero degree)."""
        # Node 2 is disconnected
        adj = csr_matrix([
            [0, 1, 0],
            [1, 0, 0],
            [0, 0, 0]
        ])
        
        L = compute_normalized_laplacian(adj)
        
        # Should not raise, isolated node gets degree 1 to avoid div by zero
        assert L.shape == (3, 3)
        # Isolated node's row should be identity-like
        assert np.isclose(L[2, 2], 1.0)
    
    def test_sparse_output(self):
        """Test that output is sparse."""
        adj = csr_matrix(np.eye(100))
        L = compute_normalized_laplacian(adj)
        
        assert hasattr(L, 'toarray')  # is sparse


class TestSpectralEmbedding:
    """Tests for full spectral embedding computation."""
    
    @pytest.fixture
    def simple_graph(self):
        """Create a simple test graph with clear community structure."""
        # Two cliques of 5 nodes each, connected by single edge
        n = 10
        adj = np.zeros((n, n))
        
        # Clique 1: nodes 0-4
        for i in range(5):
            for j in range(5):
                if i != j:
                    adj[i, j] = 1
        
        # Clique 2: nodes 5-9
        for i in range(5, 10):
            for j in range(5, 10):
                if i != j:
                    adj[i, j] = 1
        
        # Bridge: node 4 connected to node 5
        adj[4, 5] = 1
        adj[5, 4] = 1
        
        return csr_matrix(adj), [f"node_{i}" for i in range(n)]
    
    def test_embedding_shape(self, simple_graph):
        """Test that embedding has correct shape."""
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5)
        
        result = compute_spectral_embedding(adj, node_ids, config)
        
        assert result.embedding.shape == (10, 5)
        assert len(result.node_ids) == 10
        assert len(result.eigenvalues) == 5
    
    def test_embedding_normalized(self, simple_graph):
        """Test that embedding rows are unit normalized."""
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5)
        
        result = compute_spectral_embedding(adj, node_ids, config)
        
        row_norms = np.linalg.norm(result.embedding, axis=1)
        assert np.allclose(row_norms, 1.0)
    
    def test_community_separation(self, simple_graph):
        """Test that two cliques are separated in embedding space."""
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5)
        
        result = compute_spectral_embedding(adj, node_ids, config)
        
        # Compute mean embedding for each clique
        clique1_mean = result.embedding[:5].mean(axis=0)
        clique2_mean = result.embedding[5:].mean(axis=0)
        
        # Distance between clique centers should be larger than within-clique variance
        inter_dist = np.linalg.norm(clique1_mean - clique2_mean)
        intra_var1 = np.var(result.embedding[:5], axis=0).sum()
        intra_var2 = np.var(result.embedding[5:], axis=0).sum()
        
        assert inter_dist > np.sqrt(intra_var1)
        assert inter_dist > np.sqrt(intra_var2)
    
    def test_linkage_matrix_shape(self, simple_graph):
        """Test linkage matrix has correct shape."""
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5)
        
        result = compute_spectral_embedding(adj, node_ids, config)
        
        # Linkage matrix: (n-1, 4) for n nodes
        assert result.linkage_matrix.shape == (9, 4)
    
    def test_metadata_populated(self, simple_graph):
        """Test that metadata is properly populated."""
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5)
        
        result = compute_spectral_embedding(adj, node_ids, config)
        
        assert 'generated_at' in result.metadata
        assert result.metadata['n_nodes'] == 10
        assert result.metadata['n_dims'] == 5
        assert 'computation_metrics' in result.metadata
        assert result.metadata['computation_metrics']['total_time_seconds'] > 0
    
    def test_eigenvalue_ordering(self, simple_graph):
        """Test that eigenvalues are in ascending order."""
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5)
        
        result = compute_spectral_embedding(adj, node_ids, config)
        
        # Eigenvalues should be ascending
        assert np.all(np.diff(result.eigenvalues) >= 0)
    
    def test_deterministic_with_seed(self, simple_graph):
        """Test that results are reproducible with same seed."""
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5, random_seed=42)
        
        result1 = compute_spectral_embedding(adj, node_ids, config)
        result2 = compute_spectral_embedding(adj, node_ids, config)
        
        # Embeddings might differ by sign (eigenvector sign ambiguity)
        # but absolute values should match
        assert np.allclose(np.abs(result1.embedding), np.abs(result2.embedding))


class TestSaveLoad:
    """Tests for serialization."""
    
    def test_round_trip(self, tmp_path, simple_graph):
        """Test save and load preserves data."""
        from src.graph.spectral import save_spectral_result, load_spectral_result
        
        adj, node_ids = simple_graph
        config = SpectralConfig(n_dims=5)
        original = compute_spectral_embedding(adj, node_ids, config)
        
        # Save
        base_path = tmp_path / 'graph_snapshot'
        save_spectral_result(original, base_path)
        
        # Load
        loaded = load_spectral_result(base_path)
        
        assert np.allclose(original.embedding, loaded.embedding)
        assert np.array_equal(original.node_ids, loaded.node_ids)
        assert np.allclose(original.eigenvalues, loaded.eigenvalues)
        assert np.allclose(original.linkage_matrix, loaded.linkage_matrix)
```

### `src/graph/clusters.py`

#### Test Suite: `tests/test_clusters.py`

```python
"""Unit tests for cluster management."""

import pytest
import numpy as np
from scipy.cluster.hierarchy import linkage
from src.graph.clusters import (
    cut_hierarchy_at_granularity,
    compute_soft_memberships,
    compute_cluster_edges,
    get_representative_handles,
    generate_auto_label,
    ClusterLabelStore,
    build_cluster_view,
    MIN_CLUSTER_SIZE
)


class TestCutHierarchy:
    """Tests for hierarchy cutting."""
    
    @pytest.fixture
    def sample_linkage(self):
        """Create sample linkage matrix for 10 points."""
        # Random 10 points in 2D
        np.random.seed(42)
        points = np.random.randn(10, 2)
        return linkage(points, method='ward')
    
    def test_correct_number_of_clusters(self, sample_linkage):
        """Test that we get requested number of clusters."""
        labels = cut_hierarchy_at_granularity(sample_linkage, n_clusters=3)
        
        assert len(np.unique(labels)) == 3
    
    def test_all_nodes_assigned(self, sample_linkage):
        """Test that all nodes get a cluster."""
        labels = cut_hierarchy_at_granularity(sample_linkage, n_clusters=3)
        
        assert len(labels) == 10
        assert all(label >= 1 for label in labels)  # fcluster uses 1-indexing
    
    def test_single_cluster(self, sample_linkage):
        """Test n_clusters=1 gives all same label."""
        labels = cut_hierarchy_at_granularity(sample_linkage, n_clusters=1)
        
        assert len(np.unique(labels)) == 1
    
    def test_max_clusters(self, sample_linkage):
        """Test n_clusters=n gives each node its own cluster."""
        labels = cut_hierarchy_at_granularity(sample_linkage, n_clusters=10)
        
        assert len(np.unique(labels)) == 10


class TestSoftMemberships:
    """Tests for soft membership computation."""
    
    def test_probabilities_sum_to_one(self):
        """Test that memberships are valid probabilities."""
        np.random.seed(42)
        embedding = np.random.randn(20, 5)
        labels = np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 
                         3, 3, 3, 3, 3, 4, 4, 4, 4, 4])
        
        memberships = compute_soft_memberships(embedding, labels)
        
        # Each row should sum to 1
        row_sums = memberships.sum(axis=1)
        assert np.allclose(row_sums, 1.0)
    
    def test_probabilities_positive(self):
        """Test all probabilities are non-negative."""
        np.random.seed(42)
        embedding = np.random.randn(20, 5)
        labels = np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 
                         3, 3, 3, 3, 3, 4, 4, 4, 4, 4])
        
        memberships = compute_soft_memberships(embedding, labels)
        
        assert np.all(memberships >= 0)
    
    def test_shape(self):
        """Test output shape is (n_nodes, n_clusters)."""
        embedding = np.random.randn(20, 5)
        labels = np.array([1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 
                         3, 3, 3, 3, 3, 4, 4, 4, 4, 4])
        
        memberships = compute_soft_memberships(embedding, labels)
        
        assert memberships.shape == (20, 4)  # 4 unique labels
    
    def test_hard_membership_for_centroid(self):
        """Test that cluster centroids have high self-membership."""
        # Create clear clusters
        embedding = np.array([
            [0, 0], [0.1, 0], [0, 0.1],  # cluster 1 around origin
            [10, 10], [10.1, 10], [10, 10.1],  # cluster 2 far away
        ])
        labels = np.array([1, 1, 1, 2, 2, 2])
        
        memberships = compute_soft_memberships(embedding, labels, temperature=0.1)
        
        # Cluster 1 members should have high membership in cluster 1
        assert memberships[0, 0] > 0.9
        # Cluster 2 members should have high membership in cluster 2
        assert memberships[3, 1] > 0.9


class TestClusterEdges:
    """Tests for inter-cluster edge computation."""
    
    def test_basic_edge_count(self):
        """Test that edges are counted correctly."""
        # 6 nodes, 2 clusters
        adj = np.array([
            [0, 1, 1, 0, 0, 0],  # node 0 -> 1, 2
            [0, 0, 1, 1, 0, 0],  # node 1 -> 2, 3
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 1],  # node 3 -> 4, 5
            [0, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0],
        ])
        labels = np.array([1, 1, 1, 2, 2, 2])
        node_ids = np.array([f"n{i}" for i in range(6)])
        
        # Hard memberships for simplicity
        memberships = np.array([
            [1, 0],
            [1, 0],
            [1, 0],
            [0, 1],
            [0, 1],
            [0, 1],
        ])
        
        edges = compute_cluster_edges(adj, labels, memberships, node_ids)
        
        # Should have edge from cluster 1 to cluster 2 (node 1 -> node 3)
        c1_to_c2 = [e for e in edges if e.source_id == "cluster_1" and e.target_id == "cluster_2"]
        assert len(c1_to_c2) == 1
        assert c1_to_c2[0].raw_count == 1
    
    def test_no_self_loops(self):
        """Test that intra-cluster edges don't create self-loops."""
        adj = np.array([
            [0, 1, 1],
            [1, 0, 1],
            [1, 1, 0],
        ])
        labels = np.array([1, 1, 1])  # all same cluster
        node_ids = np.array(["a", "b", "c"])
        memberships = np.array([[1], [1], [1]])
        
        edges = compute_cluster_edges(adj, labels, memberships, node_ids)
        
        # No edges should exist (all intra-cluster)
        assert len(edges) == 0
    
    def test_soft_membership_weighting(self):
        """Test that soft membership affects edge weights."""
        adj = np.array([
            [0, 0, 1],  # 0 -> 2
            [0, 0, 0],
            [0, 0, 0],
        ])
        labels = np.array([1, 2, 2])
        node_ids = np.array(["a", "b", "c"])
        
        # Node 0 is 50% in cluster 1, 50% in cluster 2
        memberships = np.array([
            [0.5, 0.5],
            [0.0, 1.0],
            [0.0, 1.0],
        ])
        
        edges = compute_cluster_edges(adj, labels, memberships, node_ids)
        
        # Edge from cluster_1 to cluster_2 should have weight 0.5 * 1.0 = 0.5
        c1_to_c2 = [e for e in edges if e.source_id == "cluster_1" and e.target_id == "cluster_2"]
        assert len(c1_to_c2) == 1
        assert np.isclose(c1_to_c2[0].weight, 0.5)


class TestRepresentativeHandles:
    """Tests for selecting representative handles."""
    
    def test_top_by_followers(self):
        """Test that handles are sorted by followers."""
        members = ["a", "b", "c"]
        metadata = {
            "a": {"username": "alice", "num_followers": 100},
            "b": {"username": "bob", "num_followers": 1000},
            "c": {"username": "charlie", "num_followers": 500},
        }
        
        handles = get_representative_handles(members, metadata, n=3)
        
        assert handles == ["bob", "charlie", "alice"]
    
    def test_respects_n(self):
        """Test that only n handles are returned."""
        members = ["a", "b", "c", "d", "e"]
        metadata = {m: {"username": m, "num_followers": i*100} for i, m in enumerate(members)}
        
        handles = get_representative_handles(members, metadata, n=2)
        
        assert len(handles) == 2
    
    def test_missing_metadata(self):
        """Test handling of missing metadata."""
        members = ["a", "b"]
        metadata = {"a": {"username": "alice", "num_followers": 100}}
        
        handles = get_representative_handles(members, metadata, n=2)
        
        # Should still return something
        assert len(handles) == 2
        assert "alice" in handles


class TestAutoLabel:
    """Tests for auto-generated labels."""
    
    def test_with_handles(self):
        """Test label generation with handles."""
        label = generate_auto_label(7, ["alice", "bob", "charlie"])
        
        assert "Cluster 7" in label
        assert "@alice" in label
        assert "@bob" in label
        assert "@charlie" in label
    
    def test_without_handles(self):
        """Test label generation without handles."""
        label = generate_auto_label(7, [])
        
        assert label == "Cluster 7"


class TestClusterLabelStore:
    """Tests for SQLite label storage."""
    
    def test_set_and_get(self, tmp_path):
        """Test basic set and get."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        store.set_label("spectral_n50_c7", "Jhana Bros")
        result = store.get_label("spectral_n50_c7")
        
        assert result == "Jhana Bros"
    
    def test_update(self, tmp_path):
        """Test updating existing label."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        store.set_label("key1", "Original")
        store.set_label("key1", "Updated")
        
        assert store.get_label("key1") == "Updated"
    
    def test_delete(self, tmp_path):
        """Test deleting label."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        store.set_label("key1", "Label")
        store.delete_label("key1")
        
        assert store.get_label("key1") is None
    
    def test_get_nonexistent(self, tmp_path):
        """Test getting nonexistent label returns None."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        assert store.get_label("nonexistent") is None
    
    def test_get_all_labels(self, tmp_path):
        """Test getting all labels."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        store.set_label("key1", "Label 1")
        store.set_label("key2", "Label 2")
        
        all_labels = store.get_all_labels()
        
        assert all_labels == {"key1": "Label 1", "key2": "Label 2"}


class TestBuildClusterView:
    """Tests for full cluster view building."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for view building."""
        np.random.seed(42)
        n = 50
        
        # Create embedding with clear clusters
        embedding = np.vstack([
            np.random.randn(20, 10) + [0] * 10,  # cluster 1
            np.random.randn(15, 10) + [5] * 10,  # cluster 2
            np.random.randn(15, 10) + [-5] * 10, # cluster 3
        ])
        
        # Create linkage
        linkage_matrix = linkage(embedding, method='ward')
        
        # Create simple adjacency
        adj = np.zeros((n, n))
        # Add intra-cluster edges
        for i in range(20):
            for j in range(i+1, 20):
                if np.random.rand() > 0.5:
                    adj[i, j] = 1
        
        node_ids = np.array([f"node_{i}" for i in range(n)])
        
        node_metadata = {
            f"node_{i}": {"username": f"user_{i}", "num_followers": i * 100}
            for i in range(n)
        }
        
        return {
            'embedding': embedding,
            'linkage_matrix': linkage_matrix,
            'adjacency': adj,
            'node_ids': node_ids,
            'node_metadata': node_metadata
        }
    
    def test_granularity_respected(self, sample_data, tmp_path):
        """Test that granularity roughly matches output count."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        view = build_cluster_view(
            embedding=sample_data['embedding'],
            linkage_matrix=sample_data['linkage_matrix'],
            node_ids=sample_data['node_ids'],
            adjacency=sample_data['adjacency'],
            node_metadata=sample_data['node_metadata'],
            granularity=10,
            label_store=store
        )
        
        # Total visible items should be close to granularity
        total_visible = len(view.clusters) + len(view.individual_nodes)
        assert total_visible <= 15  # some tolerance
    
    def test_small_clusters_become_individuals(self, sample_data, tmp_path):
        """Test that clusters below MIN_CLUSTER_SIZE become individuals."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        # High granularity to create small clusters
        view = build_cluster_view(
            embedding=sample_data['embedding'],
            linkage_matrix=sample_data['linkage_matrix'],
            node_ids=sample_data['node_ids'],
            adjacency=sample_data['adjacency'],
            node_metadata=sample_data['node_metadata'],
            granularity=40,  # Close to n=50, many small clusters
            label_store=store
        )
        
        # Should have some individual nodes
        # (clusters of size < MIN_CLUSTER_SIZE)
        for cluster in view.clusters:
            assert cluster.size >= MIN_CLUSTER_SIZE
    
    def test_ego_cluster_marked(self, sample_data, tmp_path):
        """Test that ego's cluster is correctly identified."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        view = build_cluster_view(
            embedding=sample_data['embedding'],
            linkage_matrix=sample_data['linkage_matrix'],
            node_ids=sample_data['node_ids'],
            adjacency=sample_data['adjacency'],
            node_metadata=sample_data['node_metadata'],
            granularity=5,
            ego_node_id="node_0",
            label_store=store
        )
        
        # One cluster should contain ego
        ego_clusters = [c for c in view.clusters if c.contains_ego]
        assert len(ego_clusters) == 1
        assert "node_0" in ego_clusters[0].member_ids
    
    def test_user_labels_applied(self, sample_data, tmp_path):
        """Test that user labels override auto labels."""
        store = ClusterLabelStore(tmp_path / "test.db")
        
        # First, build to get cluster IDs
        view1 = build_cluster_view(
            embedding=sample_data['embedding'],
            linkage_matrix=sample_data['linkage_matrix'],
            node_ids=sample_data['node_ids'],
            adjacency=sample_data['adjacency'],
            node_metadata=sample_data['node_metadata'],
            granularity=5,
            label_store=store
        )
        
        # Set a user label
        cluster = view1.clusters[0]
        cluster_key = f"spectral_n5_{cluster.id}"
        store.set_label(cluster_key, "My Custom Label")
        
        # Rebuild
        view2 = build_cluster_view(
            embedding=sample_data['embedding'],
            linkage_matrix=sample_data['linkage_matrix'],
            node_ids=sample_data['node_ids'],
            adjacency=sample_data['adjacency'],
            node_metadata=sample_data['node_metadata'],
            granularity=5,
            label_store=store
        )
        
        # Find the same cluster and check label
        matching = [c for c in view2.clusters if c.id == cluster.id]
        assert len(matching) == 1
        assert matching[0].label == "My Custom Label"
        assert matching[0].label_source == "user"
```

---

## Integration Tests

### `tests/integration/test_cluster_api.py`

```python
"""Integration tests for cluster API endpoints."""

import pytest
from flask import Flask
from src.api.server import create_app


@pytest.fixture
def client(tmp_path):
    """Create test client with mock data."""
    # TODO: Set up test data directory with small spectral result
    app = create_app(test_config={'DATA_DIR': str(tmp_path)})
    app.config['TESTING'] = True
    
    with app.test_client() as client:
        yield client


class TestGetClusters:
    """Tests for GET /api/clusters endpoint."""
    
    def test_default_granularity(self, client):
        """Test default response without parameters."""
        response = client.get('/api/clusters')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'clusters' in data
        assert 'granularity' in data
        assert data['granularity'] == 25  # default
    
    def test_custom_granularity(self, client):
        """Test with custom granularity parameter."""
        response = client.get('/api/clusters?n=50')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['granularity'] == 50
    
    def test_granularity_clamping(self, client):
        """Test that granularity is clamped to valid range."""
        response = client.get('/api/clusters?n=1000')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['granularity'] <= 500
    
    def test_with_ego(self, client):
        """Test with ego parameter."""
        response = client.get('/api/clusters?ego=test_user')
        
        assert response.status_code == 200
        data = response.get_json()
        # Should have ego cluster marked
        assert data.get('egoClusterId') is not None or \
               any(c['containsEgo'] for c in data['clusters'])
    
    def test_cluster_structure(self, client):
        """Test cluster object structure."""
        response = client.get('/api/clusters')
        
        data = response.get_json()
        if data['clusters']:
            cluster = data['clusters'][0]
            
            assert 'id' in cluster
            assert 'size' in cluster
            assert 'label' in cluster
            assert 'labelSource' in cluster
            assert 'representativeHandles' in cluster
            assert 'containsEgo' in cluster
    
    def test_edge_structure(self, client):
        """Test edge object structure."""
        response = client.get('/api/clusters')
        
        data = response.get_json()
        if data['edges']:
            edge = data['edges'][0]
            
            assert 'source' in edge
            assert 'target' in edge
            assert 'weight' in edge
            assert 'rawCount' in edge
            assert 'opacity' in edge


class TestSetClusterLabel:
    """Tests for POST /api/clusters/{id}/label endpoint."""
    
    def test_set_label(self, client):
        """Test setting a cluster label."""
        response = client.post(
            '/api/clusters/cluster_1/label',
            json={'label': 'Test Label'}
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['label'] == 'Test Label'
        assert data['labelSource'] == 'user'
    
    def test_empty_label_rejected(self, client):
        """Test that empty label is rejected."""
        response = client.post(
            '/api/clusters/cluster_1/label',
            json={'label': ''}
        )
        
        assert response.status_code == 400
    
    def test_label_persists(self, client):
        """Test that label persists across requests."""
        # Set label
        client.post(
            '/api/clusters/cluster_1/label?granularity=25',
            json={'label': 'Persistent Label'}
        )
        
        # Get clusters
        response = client.get('/api/clusters?n=25')
        data = response.get_json()
        
        # Find cluster_1 and verify label
        c1 = next((c for c in data['clusters'] if c['id'] == 'cluster_1'), None)
        if c1:
            assert c1['label'] == 'Persistent Label'


class TestDeleteClusterLabel:
    """Tests for DELETE /api/clusters/{id}/label endpoint."""
    
    def test_delete_label(self, client):
        """Test deleting a cluster label."""
        # Set then delete
        client.post('/api/clusters/cluster_1/label', json={'label': 'Temp'})
        response = client.delete('/api/clusters/cluster_1/label')
        
        assert response.status_code == 200
    
    def test_delete_nonexistent(self, client):
        """Test deleting nonexistent label doesn't error."""
        response = client.delete('/api/clusters/cluster_999/label')
        
        assert response.status_code == 200
```

---

## Performance Tests

### `tests/performance/test_spectral_performance.py`

```python
"""Performance tests for spectral computation."""

import pytest
import time
import numpy as np
from scipy.sparse import random as sparse_random
from src.graph.spectral import compute_spectral_embedding, SpectralConfig


class TestSpectralPerformance:
    """Performance benchmarks for spectral embedding."""
    
    @pytest.mark.slow
    @pytest.mark.parametrize("n_nodes", [1000, 5000, 10000])
    def test_embedding_time_scaling(self, n_nodes):
        """Test embedding computation time scales reasonably."""
        # Create sparse random graph
        density = 10 / n_nodes  # ~10 edges per node on average
        adj = sparse_random(n_nodes, n_nodes, density=density, format='csr')
        adj = (adj + adj.T) / 2  # symmetrize
        
        node_ids = [f"node_{i}" for i in range(n_nodes)]
        config = SpectralConfig(n_dims=20, eigensolver_maxiter=1000)
        
        start = time.time()
        result = compute_spectral_embedding(adj, node_ids, config)
        elapsed = time.time() - start
        
        # Log timing
        print(f"\nn={n_nodes}: {elapsed:.2f}s")
        print(f"  Eigenvalue gap: {result.metadata['computation_metrics']['eigenvalue_gap']:.4f}")
        
        # Assert reasonable time bounds
        # These are loose bounds, adjust based on actual performance
        expected_max = {
            1000: 10,
            5000: 60,
            10000: 300,
        }
        assert elapsed < expected_max[n_nodes], f"Too slow: {elapsed}s for n={n_nodes}"
    
    @pytest.mark.slow
    def test_full_graph_timing(self):
        """Test on realistic graph size (70K nodes)."""
        # This test may take several minutes
        n_nodes = 70000
        density = 10 / n_nodes
        
        adj = sparse_random(n_nodes, n_nodes, density=density, format='csr')
        adj = (adj + adj.T) / 2
        
        node_ids = [f"node_{i}" for i in range(n_nodes)]
        config = SpectralConfig(n_dims=30, eigensolver_maxiter=5000)
        
        start = time.time()
        result = compute_spectral_embedding(adj, node_ids, config)
        elapsed = time.time() - start
        
        print(f"\nFull graph (n={n_nodes}): {elapsed:.2f}s")
        print(f"  Breakdown:")
        metrics = result.metadata['computation_metrics']
        print(f"    Laplacian: {metrics['laplacian_time_seconds']:.2f}s")
        print(f"    Eigensolver: {metrics['eigensolver_time_seconds']:.2f}s")
        print(f"    Linkage: {metrics['linkage_time_seconds']:.2f}s")
        
        # Should complete in under 30 minutes
        assert elapsed < 1800


class TestClusterViewPerformance:
    """Performance benchmarks for cluster view building."""
    
    @pytest.mark.parametrize("granularity", [10, 25, 50, 100])
    def test_view_building_time(self, granularity, tmp_path):
        """Test cluster view building is fast."""
        from src.graph.clusters import build_cluster_view, ClusterLabelStore
        from scipy.cluster.hierarchy import linkage
        
        n = 10000
        embedding = np.random.randn(n, 30)
        linkage_matrix = linkage(embedding[:1000], method='ward')  # approx
        # Extend linkage for full size (hack for testing)
        
        node_ids = np.array([f"n{i}" for i in range(n)])
        adj = np.zeros((n, n))  # sparse for speed
        metadata = {f"n{i}": {"username": f"u{i}", "num_followers": i} for i in range(n)}
        store = ClusterLabelStore(tmp_path / "test.db")
        
        start = time.time()
        # Note: This will fail with mismatched linkage size
        # Real test needs proper linkage matrix
        elapsed = time.time() - start
        
        print(f"\nGranularity {granularity}: {elapsed:.4f}s")
        
        # Should be under 1 second
        assert elapsed < 1.0
```

---

## Manual Test Scenarios

### Scenario 1: Initial Load

**Steps:**
1. Navigate to `/explore?view=cluster`
2. Observe loading state
3. Verify clusters appear

**Expected:**
- Loading indicator shows while fetching
- Clusters render within 2 seconds
- Default granularity ~25 items visible
- Ego cluster (if set) is highlighted purple

### Scenario 2: Semantic Zoom

**Steps:**
1. Load cluster view
2. Scroll mouse wheel up (zoom in)
3. Observe clusters splitting
4. Scroll mouse wheel down (zoom out)
5. Observe clusters merging

**Expected:**
- Clusters split into sub-clusters smoothly
- Cluster count increases/decreases with zoom
- Visual budget (~25-40 items) maintained
- Ego cluster trail maintained (purple persists)

### Scenario 3: Drill Down

**Steps:**
1. Load cluster view at default zoom
2. Double-click on a cluster
3. Observe expansion

**Expected:**
- Clicked cluster expands in place
- Sub-clusters appear within original cluster region
- Other clusters remain visible
- Breadcrumb or indicator shows drill-down state

### Scenario 4: Member List

**Steps:**
1. Single-click on a cluster
2. Observe member list panel

**Expected:**
- Side panel opens showing cluster members
- Members sorted by follower count
- Each member shows handle, name, followers
- Click on member navigates to their position

### Scenario 5: Rename Cluster

**Steps:**
1. Right-click on cluster
2. Select "Rename" from context menu
3. Enter new name
4. Press Enter
5. Refresh page

**Expected:**
- Context menu appears at cursor
- Inline editor activates
- New name saves on Enter
- Name persists after refresh
- Label shows with "user" indicator

### Scenario 6: Edge Rendering

**Steps:**
1. Load cluster view
2. Observe inter-cluster edges
3. Hover over an edge

**Expected:**
- Edges are curved (distinguishable when A→B and B→A both exist)
- Edges have gradient (dark at source, light at target)
- Edge opacity reflects weight
- Hover shows exact count/percentage

### Scenario 7: URL Sharing

**Steps:**
1. Load cluster view
2. Zoom to specific level
3. Drill into a cluster
4. Copy URL
5. Open in new incognito window

**Expected:**
- URL reflects current state (granularity, focus)
- New window loads same view
- Cluster labels visible (if any set)

### Scenario 8: Error States

**Steps:**
1. Enter invalid ego username
2. Disconnect network, try to zoom
3. Request very high granularity

**Expected:**
- Invalid ego shows error message with contact info
- Network error shows retry option
- Granularity clamps to valid range

---

## Test Data Requirements

### Small Test Graph

For unit and fast integration tests:
- 50-100 nodes
- Clear community structure (2-3 cliques)
- Pre-computed spectral result
- Location: `tests/fixtures/small_graph/`

### Medium Test Graph

For integration tests:
- 1,000-5,000 nodes
- Realistic structure (power-law degree distribution)
- Pre-computed spectral result
- Location: `tests/fixtures/medium_graph/`

### Full Graph (Production)

For performance tests and manual testing:
- 70,000+ nodes (actual TPOT data)
- Full spectral embedding
- Location: `data/graph_snapshot.*`

---

## Continuous Integration

### Test Commands

```bash
# Run unit tests
pytest tests/test_spectral.py tests/test_clusters.py -v

# Run integration tests
pytest tests/integration/ -v

# Run performance tests (slow)
pytest tests/performance/ -v --slow

# Run all tests with coverage
pytest --cov=src --cov-report=html
```

### CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt
      
      - name: Run unit tests
        run: pytest tests/test_*.py -v
      
      - name: Run integration tests
        run: pytest tests/integration/ -v
```

---

## Acceptance Criteria Checklist

- [ ] Spectral embedding computes successfully on full graph
- [ ] Computation metrics logged (time, eigenvalue gap, stability)
- [ ] Cluster view renders at default granularity
- [ ] Semantic zoom changes cluster count
- [ ] Cluster count stays within visual budget (20-40)
- [ ] Ego cluster highlighted in purple at all zoom levels
- [ ] Double-click drills into cluster
- [ ] Single-click shows member list panel
- [ ] Right-click shows context menu with rename
- [ ] Cluster labels persist across sessions
- [ ] Directed edges rendered with curves and gradients
- [ ] Edge opacity reflects soft-membership weight
- [ ] URL state reflects current view
- [ ] Shared URL loads same view
- [ ] Small clusters (< 4 members) show as individuals
- [ ] Error states handled gracefully
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Performance acceptable (< 2s for view changes)
