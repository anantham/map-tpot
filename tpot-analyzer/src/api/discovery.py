"""Subgraph discovery API for personalized TPOT recommendations."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Dict, List, Optional, Tuple, Any

import networkx as nx

from src.api.services.bounded_cache import BoundedCache
from src.api.discovery_request import DiscoveryRequest, validate_request
from src.api.discovery_projection import COMMUNITY_LABELS, apply_filters, build_recommendation
from src.api.discovery_subgraph import extract_subgraph

from src.graph.scoring import (
    score_candidate,
    process_weights,
    DEFAULT_WEIGHTS
)

logger = logging.getLogger(__name__)


# Configuration
SUBGRAPH_MAX_DEPTH = 2
SUBGRAPH_MAX_NODES = 5000
MAX_NEIGHBORS_PER_NODE = 100
MAX_SEEDS = 20
MAX_LIMIT = 500
MAX_OFFSET = 10000
CACHE_TTL_SECONDS = 3600  # 1 hour


# Community names (manually curated)


class DiscoveryCache:
    """Bounded cache retained as a compatibility facade for discovery callers."""

    def __init__(self, max_size=100, ttl_seconds=CACHE_TTL_SECONDS):
        self._cache = BoundedCache(max_size, 16 * 1024 * 1024, ttl_seconds)

    def make_key(self, request, *, graph_identity=None):
        key_data = {"request": asdict(request), "graph_identity": graph_identity}
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, data):
        return self._cache.set(key, data)


# Global cache instance
discovery_cache = DiscoveryCache()








def discover_subgraph(
    graph: nx.DiGraph,
    request: DiscoveryRequest,
    pagerank_scores: Dict[str, float]
) -> Dict:
    """Main discovery logic.

    Returns:
        Complete discovery response
    """
    start_time = time.time()
    timing = {}

    # Check cache
    cache_key = None
    if request.use_cache:
        graph_identity = graph.graph.setdefault("_tpot_discovery_cache_id", uuid4().hex)
        cache_key = discovery_cache.make_key(request, graph_identity=graph_identity)
        cached = discovery_cache.get(cache_key)
        if cached:
            logger.info(f"Cache hit for key {cache_key}")
            return cached

    # Extract subgraph
    t0 = time.time()
    subgraph, candidate_nodes = extract_subgraph(graph, request.seeds)
    timing['subgraph_extraction_ms'] = int((time.time() - t0) * 1000)

    # Handle no valid seeds
    valid_seeds = [s for s in request.seeds if s in graph]
    invalid_seeds = [s for s in request.seeds if s not in graph]

    if not valid_seeds:
        return {
            'error': {
                'code': 'NO_VALID_SEEDS',
                'message': 'None of the provided seeds exist in graph',
                'unknown_handles': invalid_seeds
            }
        }

    # Create undirected version for path computation
    undirected = subgraph.to_undirected()

    # Precompute SSSP from each seed once (O(seeds × BFS)) so that per-candidate
    # distance lookups are O(1) instead of O(candidates × seeds × BFS).
    # cutoff=3 matches the default max_distance in compute_path_distance_score.
    _DISTANCE_CUTOFF = 3
    t0 = time.time()
    precomputed_distances: Dict[str, Dict[str, int]] = {
        seed: dict(nx.single_source_shortest_path_length(undirected, seed, cutoff=_DISTANCE_CUTOFF))
        for seed in valid_seeds
        if seed in undirected
    }
    timing['sssp_precompute_ms'] = int((time.time() - t0) * 1000)
    logger.info(
        "SSSP precomputed for %d seeds in %dms (cutoff=%d)",
        len(precomputed_distances), timing['sssp_precompute_ms'], _DISTANCE_CUTOFF,
    )

    # Score all candidates
    t0 = time.time()
    scored_candidates = []

    for candidate in candidate_nodes:
        if candidate in valid_seeds:
            continue  # Skip seeds themselves

        score_result = score_candidate(
            subgraph,
            candidate,
            valid_seeds,
            pagerank_scores,
            request.weights,
            undirected,
            precomputed_distances=precomputed_distances,
        )

        scored_candidates.append(score_result)

    timing['scoring_ms'] = int((time.time() - t0) * 1000)

    # Apply filters
    t0 = time.time()
    filtered = apply_filters(scored_candidates, request.filters, valid_seeds, graph)
    timing['filtering_ms'] = int((time.time() - t0) * 1000)

    # Sort by composite score
    t0 = time.time()
    filtered.sort(key=lambda x: x['composite_score'], reverse=True)
    timing['sorting_ms'] = int((time.time() - t0) * 1000)

    # Apply pagination
    total_candidates = len(filtered)
    paginated = filtered[request.offset:request.offset + request.limit]

    # Build recommendations
    recommendations = [
        build_recommendation(candidate, graph, valid_seeds)
        for candidate in paginated
    ]

    # Build response
    response = {
        'recommendations': recommendations,
        'meta': {
            'request_id': hashlib.md5(str(time.time()).encode()).hexdigest()[:16],
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'seed_count': len(valid_seeds),
            'recommendation_count': len(recommendations),
            'total_candidates': total_candidates,
            'computation_time_ms': int((time.time() - start_time) * 1000),
            'cache_hit': False,
            'pagination': {
                'limit': request.limit,
                'offset': request.offset,
                'total_candidates': total_candidates,
                'has_more': request.offset + request.limit < total_candidates
            }
        }
    }

    # Add warnings if invalid seeds
    if invalid_seeds:
        response['warnings'] = [
            f"Unknown handles ignored: {', '.join(invalid_seeds)}"
        ]

    # Add debug info
    if request.debug:
        response['debug'] = {
            'subgraph_size': len(subgraph),
            'timing_breakdown': timing,
            'weight_normalization': request.weights,
            'valid_seeds': valid_seeds,
            'invalid_seeds': invalid_seeds
        }

    # Add snapshot info
    manifest_path = Path("data/graph_snapshot.meta.json")
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            generated_at = datetime.fromisoformat(manifest['generated_at'])
            age_hours = (datetime.utcnow() - generated_at).total_seconds() / 3600

            response['meta']['snapshot_version'] = manifest['generated_at']
            response['meta']['snapshot_age_hours'] = round(age_hours, 1)
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            logger.warning("Could not read snapshot manifest for response meta: %s", exc)

    # Cache result
    if request.use_cache and cache_key:
        discovery_cache.set(cache_key, response)
        response['meta']['cache_key'] = cache_key if request.debug else None

    # Always log timing summary to disk so we can profile without debug=true.
    timing['total_ms'] = int((time.time() - start_time) * 1000)
    logger.info(
        "discover timing seeds=%d candidates=%d filtered=%d | "
        "subgraph=%dms sssp=%dms scoring=%dms filter=%dms sort=%dms total=%dms",
        len(valid_seeds),
        len(candidate_nodes),
        total_candidates,
        timing.get('subgraph_extraction_ms', 0),
        timing.get('sssp_precompute_ms', 0),
        timing.get('scoring_ms', 0),
        timing.get('filtering_ms', 0),
        timing.get('sorting_ms', 0),
        timing['total_ms'],
    )

    return response
