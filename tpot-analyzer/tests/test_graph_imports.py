"""Light graph readers must not initialize unrelated numerical algorithms.

Keep the existing package exports and object identities while allowing the
stdlib-only retrieval modules and CLI help to start without scientific imports.
"""
import importlib
import json
import subprocess
import sys

import pytest


def test_pure_retrieval_import_does_not_load_the_scientific_stack():
    done = subprocess.run([sys.executable, '-B', '-c', '''
import json, sys
from src.graph.cofollow import CoFollowGraph
from src.graph.seed_recovery import RecoveryGraph
print(json.dumps(sorted(set(sys.modules) & {
    'numpy', 'pandas', 'scipy', 'sklearn', 'networkx', 'src.data.shadow_store'
})))
'''], capture_output=True, text=True, timeout=15)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == []


def test_public_package_exports_keep_their_original_objects():
    import src.graph as graph
    groups = {
        'builder': ('GraphBuildResult', 'build_graph', 'build_graph_from_frames'),
        'metrics': ('compute_betweenness', 'compute_composite_score',
            'compute_engagement_scores', 'compute_louvain_communities',
            'compute_personalized_pagerank', 'normalize_scores'),
        'seeds': ('DEFAULT_SEEDS', 'get_seed_state', 'get_graph_settings',
            'update_graph_settings', 'extract_usernames_from_html',
            'load_seed_candidates', 'save_seed_list', 'set_active_seed_list'),
        'spectral': ('SpectralConfig', 'SpectralResult', 'compute_normalized_laplacian',
            'compute_spectral_embedding', 'load_spectral_result', 'save_spectral_result'),
        'observation_model': ('ObservationWeightingConfig', 'compute_observation_completeness',
            'build_binary_adjacency_from_edges', 'build_ipw_adjacency_from_edges',
            'summarize_completeness'),
        'membership_grf': ('GRFMembershipConfig', 'GRFMembershipResult', 'compute_grf_membership'),
    }
    expected = {name for names in groups.values() for name in names}
    assert set(graph.__all__) == expected
    assert expected <= set(dir(graph))
    for module, names in groups.items():
        original = importlib.import_module('src.graph.' + module)
        for name in names:
            assert getattr(graph, name) is getattr(original, name)
    namespace = {}
    exec('from src.graph import *', namespace)
    assert {name for name in namespace if not name.startswith('__')} == expected
    with pytest.raises(AttributeError):
        getattr(graph, 'not_a_graph_export')
