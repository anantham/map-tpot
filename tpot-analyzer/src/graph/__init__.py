"""Graph utilities, loading numerical algorithms only when requested.

Importing a stdlib-only retrieval submodule must not initialize the builder,
data stores or spectral stack. Package-level imports keep their original names
and objects; only their import time moves to the first explicit request.
"""
from importlib import import_module

_MODULE_EXPORTS = {
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
_EXPORT_MODULE = {name: module for module, names in _MODULE_EXPORTS.items() for name in names}

__all__ = [
    "GraphBuildResult",
    "build_graph",
    "build_graph_from_frames",
    "compute_betweenness",
    "compute_composite_score",
    "compute_engagement_scores",
    "compute_louvain_communities",
    "compute_personalized_pagerank",
    "normalize_scores",
    "DEFAULT_SEEDS",
    "get_seed_state",
    "get_graph_settings",
    "update_graph_settings",
    "extract_usernames_from_html",
    "load_seed_candidates",
    "save_seed_list",
    "set_active_seed_list",
    "SpectralConfig",
    "SpectralResult",
    "compute_normalized_laplacian",
    "compute_spectral_embedding",
    "load_spectral_result",
    "save_spectral_result",
    "ObservationWeightingConfig",
    "compute_observation_completeness",
    "build_binary_adjacency_from_edges",
    "build_ipw_adjacency_from_edges",
    "summarize_completeness",
    "GRFMembershipConfig",
    "GRFMembershipResult",
    "compute_grf_membership",
]


def __getattr__(name):
    if name not in _EXPORT_MODULE:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module('.' + _EXPORT_MODULE[name], __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
