"""Community label propagation (ADR 012 Phase 0).

Public API:
    from src.propagation import propagate, PropagationConfig, PropagationResult
    from src.propagation.diagnostics import print_diagnostics
    from src.propagation.io import save_results, build_adjacency_from_archive
    from src.propagation.typed_graph import TypedGraph
"""
from src.propagation.types import PropagationConfig, PropagationResult
from src.propagation.engine import propagate, load_community_labels, multiclass_entropy

__all__ = [
    "PropagationConfig",
    "PropagationResult",
    "propagate",
    "load_community_labels",
    "multiclass_entropy",
]
