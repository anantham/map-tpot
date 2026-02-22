"""Subgraph discovery API for personalized TPOT recommendations."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import networkx as nx
import pandas as pd

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
COMMUNITY_LABELS = {
    0: "General",
    1: "Tech/Engineering",
    2: "Philosophy",
    3: "Rationalist",
    4: "AI/ML",
    5: "Builder/Indie",
    6: "Politics",
    7: "Art/Creative",
    8: "Science",
    9: "Economics",
    10: "Education",
    11: "Media/Journalism",
    12: "AI Safety",
    # Add more as needed
}


@dataclass
class DiscoveryRequest:
    """Validated discovery request."""
    seeds: List[str]
    weights: Dict[str, float]
    filters: Dict[str, Any]
    limit: int
    offset: int
    use_cache: bool
    debug: bool


class DiscoveryCache:
    """Simple LRU cache for discovery results."""

    def __init__(self, max_size: int = 100, ttl_seconds: int = CACHE_TTL_SECONDS):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.access_order = []  # For LRU

    def make_key(self, request: DiscoveryRequest) -> str:
        """Create deterministic cache key from request."""
        key_data = {
            'seeds': sorted(request.seeds),
            'weights': request.weights,
            'filters': request.filters,
            'limit': request.limit,
            'offset': request.offset,
            'debug': request.debug,
        }

        # Include snapshot version if available
        manifest_path = Path("data/graph_snapshot.meta.json")
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                key_data['snapshot_version'] = manifest.get("generated_at", "unknown")
            except:
                pass

        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_json.encode()).hexdigest()

    def get(self, key: str) -> Optional[Dict]:
        """Get cached result if fresh."""
        if key in self.cache:
            entry = self.cache[key]
            age = time.time() - entry['timestamp']

            if age < self.ttl:
                # Update access order for LRU
                self.access_order.remove(key)
                self.access_order.append(key)
                return entry['data']
            else:
                # Expired
                del self.cache[key]
                self.access_order.remove(key)

        return None

    def set(self, key: str, data: Dict):
        """Store result with timestamp."""
        # LRU eviction if needed
        if len(self.cache) >= self.max_size and key not in self.cache:
            oldest = self.access_order[0]
            del self.cache[oldest]
            self.access_order.pop(0)

        self.cache[key] = {
            'data': data,
            'timestamp': time.time()
        }

        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)


# Global cache instance
discovery_cache = DiscoveryCache()


def validate_request(data: Dict) -> Tuple[Optional[DiscoveryRequest], Optional[List[str]]]:
    """Validate and parse request data.

    Returns:
        (parsed_request, errors) - One will be None
    """
    errors = []

    # Seeds validation
    seeds = data.get('seeds', [])
    if not seeds:
        errors.append("seeds: required field")
    elif not isinstance(seeds, list):
        errors.append("seeds: must be an array")
    elif len(seeds) > MAX_SEEDS:
        errors.append(f"seeds: maximum {MAX_SEEDS} seeds allowed")
    else:
        # Validate each seed
        for seed in seeds:
            if not isinstance(seed, str):
                errors.append(f"seeds: invalid handle type: {type(seed)}")
                break
            if len(seed) > 50:
                errors.append(f"seeds: handle too long: {seed}")
                break

    # Process weights
    raw_weights = data.get('weights', {})
    weights = process_weights(raw_weights)

    # Process filters
    filters = data.get('filters', {})

    # Validate filter values
    if 'max_distance' in filters:
        if not 1 <= filters['max_distance'] <= 4:
            errors.append("filters.max_distance: must be between 1 and 4")

    if 'min_overlap' in filters:
        if filters['min_overlap'] < 0:
            errors.append("filters.min_overlap: must be non-negative")

    if 'max_followers' in filters:
        if filters['max_followers'] < 0:
            errors.append("filters.max_followers: must be non-negative")

    # Limit and offset
    limit = min(data.get('limit', 100), MAX_LIMIT)
    offset = min(data.get('offset', 0), MAX_OFFSET)

    if limit <= 0:
        errors.append("limit: must be positive")
    if offset < 0:
        errors.append("offset: must be non-negative")

    # Other options
    use_cache = data.get('use_cache', True)
    debug = data.get('debug', False)

    if errors:
        return None, errors

    return DiscoveryRequest(
        seeds=seeds,
        weights=weights,
        filters=filters,
        limit=limit,
        offset=offset,
        use_cache=use_cache,
        debug=debug
    ), None


def extract_subgraph(
    graph: nx.DiGraph,
    seeds: List[str],
    depth: int = SUBGRAPH_MAX_DEPTH
) -> Tuple[nx.DiGraph, List[str]]:
    """Extract k-hop neighborhood around seeds.

    Returns:
        (subgraph, candidate_nodes)
    """
    start_time = time.time()

    # Validate seeds exist in graph
    valid_seeds = [s for s in seeds if s in graph]
    invalid_seeds = [s for s in seeds if s not in graph]

    if not valid_seeds:
        return nx.DiGraph(), []

    # BFS to find k-hop neighborhood
    subgraph_nodes = set(valid_seeds)
    current_layer = set(valid_seeds)

    for hop in range(depth):
        next_layer = set()

        for node in current_layer:
            # Get neighbors (both in and out)
            predecessors = list(graph.predecessors(node))[:MAX_NEIGHBORS_PER_NODE]
            successors = list(graph.successors(node))[:MAX_NEIGHBORS_PER_NODE]

            next_layer.update(predecessors)
            next_layer.update(successors)

        # Preserve only unseen neighbors as the next BFS frontier.
        # Computing this before mutating subgraph_nodes prevents frontier collapse.
        next_frontier = next_layer - subgraph_nodes
        if not next_frontier:
            break

        subgraph_nodes.update(next_frontier)

        # Safety check
        if len(subgraph_nodes) > SUBGRAPH_MAX_NODES:
            logger.warning(f"Subgraph exceeded {SUBGRAPH_MAX_NODES} nodes, stopping at hop {hop+1}")
            break

        current_layer = next_frontier

    # Create subgraph
    subgraph = graph.subgraph(list(subgraph_nodes)).copy()

    # Identify candidates (in subgraph but not seeds)
    candidates = list(subgraph_nodes - set(valid_seeds))

    logger.info(f"Extracted {len(subgraph_nodes)} nodes in {time.time() - start_time:.2f}s")

    return subgraph, candidates


def apply_filters(
    candidates: List[Dict],
    filters: Dict[str, Any],
    seeds: List[str],
    graph: nx.DiGraph = None
) -> List[Dict]:
    """Apply filters to candidate list."""
    filtered = []

    # Auto-cap min_overlap
    min_overlap = min(
        filters.get('min_overlap', 0),
        len(seeds)
    )

    # Get list of accounts the ego node already follows (if exclude_following is enabled)
    following_set = set()
    if filters.get('exclude_following', False) and len(seeds) == 1 and graph:
        # Only apply if we have exactly one seed (ego node)
        ego_node = seeds[0]
        if ego_node in graph:
            following_set = set(graph.successors(ego_node))

    for candidate in candidates:
        # Exclude following filter (only for ego-network mode)
        if following_set and candidate['candidate'] in following_set:
            continue

        # Distance filter
        if 'max_distance' in filters:
            min_dist = candidate['details']['distance']['min_distance']
            if min_dist is None or min_dist > filters['max_distance']:
                continue

        # Overlap filter
        overlap_count = candidate['details']['overlap']['raw_count']
        if overlap_count < min_overlap:
            continue

        # Follower filters
        metadata = candidate.get('metadata', {})
        num_followers = metadata.get('num_followers')

        if num_followers is None:
            # Unknown follower count
            if filters.get('min_followers', 0) > 0:
                continue  # Can't verify minimum
        else:
            if 'min_followers' in filters and num_followers < filters['min_followers']:
                continue
            if 'max_followers' in filters and num_followers > filters['max_followers']:
                continue

        # Community filters
        community_id = candidate['details']['community']['community_id']

        if 'include_communities' in filters:
            if community_id not in filters['include_communities']:
                continue

        if 'exclude_communities' in filters:
            if community_id in filters['exclude_communities']:
                continue

        # Shadow filter
        if 'include_shadow' in filters and not filters['include_shadow']:
            if metadata.get('is_shadow', False):
                continue

        filtered.append(candidate)

    return filtered


def build_recommendation(
    scored_candidate: Dict,
    graph: nx.DiGraph,
    seeds: List[str]
) -> Dict:
    """Build recommendation object from scored candidate."""
    handle = scored_candidate['candidate']
    node_data = graph.nodes[handle]

    account_id = handle
    username = node_data.get('username') or account_id

    # Get metadata
    metadata = {
        'num_followers': node_data.get('num_followers'),
        'num_following': node_data.get('num_following'),
        'follower_following_ratio': None,
        'is_shadow': node_data.get('shadow', False),
        'bio': node_data.get('bio', '')[:200] if node_data.get('bio') else None,
        'location': node_data.get('location')
    }
    metadata['username'] = username

    # Calculate ratio safely
    if metadata['num_followers'] and metadata['num_following'] and metadata['num_following'] > 0:
        metadata['follower_following_ratio'] = round(
            metadata['num_followers'] / metadata['num_following'], 1
        )
    else:
        metadata['follower_following_ratio'] = None

    # Build explanation
    overlap_details = scored_candidate['details']['overlap']
    community_details = scored_candidate['details']['community']
    distance_details = scored_candidate['details']['distance']

    # Find which seeds connect to this candidate
    overlapping_seeds = [
        seed for seed, count in overlap_details['seed_details'].items()
        if count > 0
    ]

    explanation = {
        'overlapping_seeds': overlapping_seeds,
        'overlap_count': overlap_details['raw_count'],
        'community_id': community_details['community_id'],
        'community_name': COMMUNITY_LABELS.get(community_details['community_id']),
        'min_distance': distance_details['min_distance']
    }

    # Find edges to seeds
    edges_to_seeds = []
    for seed in seeds:
        if seed in graph and handle in graph:
            # Check if there's an edge
            has_forward = graph.has_edge(seed, handle)
            has_reverse = graph.has_edge(handle, seed)

            if has_forward or has_reverse:
                edges_to_seeds.append({
                    'seed': seed,
                    'mutual': has_forward and has_reverse
                })

    return {
        'account_id': account_id,
        'handle': account_id,  # Back-compat: internal identifier
        'username': username,
        'display_name': node_data.get('display_name', username),
        'composite_score': scored_candidate['composite_score'],
        'scores': scored_candidate['scores'],
        'explanation': explanation,
        'metadata': metadata,
        'edges_to_seeds': edges_to_seeds
    }


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
        cache_key = discovery_cache.make_key(request)
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
            undirected
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
        except:
            pass

    # Cache result
    if request.use_cache and cache_key:
        discovery_cache.set(cache_key, response)
        response['meta']['cache_key'] = cache_key if request.debug else None

    return response
